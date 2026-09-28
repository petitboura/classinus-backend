"""
Gestion de la taille de l'historique d'une conversation (27 et 28/09/2026,
demande explicite Bourama : reduire les couts sans jamais perdre de contexte).
Voir aussi core/outils_rappel_historique.py (relire un vieux message),
core/outils_gestion_historique.py (marquer un sujet comme clos) et
core/texte_recherche_simple.py (comparaison de mots).

Principe : le frontend renvoie a chaque message TOUT l'historique. Plutot que
de le repayer en entier a chaque tour, les messages d'un sujet que le modele
lui-meme a juge termine (outil marquer_sujet_clos) sont remplaces par un
simple rappel gratuit (role + debut du message). Le texte complet reste
recuperable a la demande via rappeler_echange_conversation. Rien n'est perdu.

Deux seuils (constantes_agent.py) :
- SEUIL_CARACTERES_HISTORIQUE_CONVERSATION (doux, 5000) : objectif affiche au
  modele quand la taille approche. Rien n'est force a ce niveau, c'est une
  consigne donnee au modele.
- SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX (dur, 8000) : filet de securite.
  Si le modele n'a pas allege assez, les plus vieux messages sont alleges
  automatiquement, en evitant d'abord ceux dont le sujet reste present dans
  les echanges recents.

Si le modele oublie de clore des sujets, un second appel dedie tourne en
arriere-plan APRES l'envoi de la reponse (forcer_cloture_sujets_en_arriere_plan),
avec le meme modele et son contexte complet, pour que le message suivant
parte deja allege.
"""

import json
import logging
import threading

from openai import OpenAI
from constantes_agent import (
    supabase,
    get_secret,
    DEEPSEEK_PRIMARY,
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION,
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX,
)
from texte_recherche_simple import mots_significatifs, sujet_correspond, chevauchement_fort

_LONGUEUR_APERCU = 80
_LIBELLE_ROLE = {"user": "question de l'utilisateur", "assistant": "réponse de l'IA"}
_PREFIXE_RAPPEL = "[Message plus tôt"

# Les tout derniers messages ne sont JAMAIS alleges : l'echange en cours doit
# toujours rester lisible tel quel.
_MESSAGES_RECENTS_PROTEGES = 4

# Un message n'est remplace par un rappel que s'il est nettement plus long que
# le rappel, sinon le contexte grossirait au lieu de diminuer.
_MARGE_MIN_REMPLACEMENT = 100

# Le suivi de taille n'est montre au modele qu'a partir de cette part du seuil
# doux : inutile de lui en parler dans une conversation courte.
_PART_SEUIL_AFFICHAGE_NOTE = 0.6

# Nombre maximum de sujets clos gardes par conversation (les plus anciens
# sont oublies au-dela).
_MAX_SUJETS_CLOS = 60

# Le rattrapage en arriere-plan ne se relance pas avant que la conversation
# ait grandi d'au moins ce nombre de messages depuis la derniere tentative.
_ECART_MIN_TENTATIVES = 6
_DELAI_RATTRAPAGE_SECONDES = 30
_tentatives_rattrapage = {}
_verrou_tentatives = threading.Lock()


def _apercu(texte):
    texte = (texte or "").strip().replace("\n", " ")
    if len(texte) <= _LONGUEUR_APERCU:
        return texte
    return texte[:_LONGUEUR_APERCU].rstrip() + "…"


def _pointeur_message(role, contenu):
    # Formulation volontairement souple (28/09/2026) : certains chemins de
    # reponse (modele premium, filet de secours Gemini sans outils, voir
    # core/main.py) n'ont JAMAIS aucun outil disponible, meme quand
    # historique_allege a ete calcule en pensant que rappeler_echange_
    # conversation le serait. Le modele doit pouvoir continuer normalement
    # meme si cet outil s'avere absent de sa liste ce tour-ci.
    libelle = _LIBELLE_ROLE.get(role, role)
    return (
        f"{_PREFIXE_RAPPEL} dans cette conversation : {libelle}, sujet : "
        f"\"{_apercu(contenu)}\". Texte complet non affiché ici pour ne pas "
        f"surcharger le contexte. Si l'outil rappeler_echange_conversation "
        f"est disponible et que ce détail redevient utile, utilise-le. "
        f"Sinon, continue normalement sans ce détail.]"
    )


def _est_rappel(contenu):
    return (contenu or "").startswith(_PREFIXE_RAPPEL)


def _peut_alleger(contenu, rappel):
    return len(contenu) > len(rappel) + _MARGE_MIN_REMPLACEMENT


def calculer_taille_historique(historique):
    return sum(len(m.get("content") or "") for m in (historique or []))


def seuil_affichage_note():
    return int(SEUIL_CARACTERES_HISTORIQUE_CONVERSATION * _PART_SEUIL_AFFICHAGE_NOTE)


def a_des_messages_allegers(historique):
    """Vrai si au moins un message de cet historique est deja un rappel."""
    return any(_est_rappel(m.get("content")) for m in (historique or []))


def lire_sujets_clos(conversation_id):
    """
    Sujets que le modele a lui-meme marques comme clos pour cette
    conversation. La liste s'accumule (jamais ecrasee) : un sujet clos le
    reste. Liste vide si rien n'est marque, si conversation_id est absent ou
    si Supabase repond mal : ne doit jamais bloquer la reponse normale.
    """
    if not conversation_id:
        return []
    try:
        res = (
            supabase.table("sujets_clos_conversation")
            .select("sujets")
            .eq("conversation_id", str(conversation_id))
            .maybe_single()
            .execute()
        )
        sujets = ((res.data if res else None) or {}).get("sujets") or []
        return [s for s in sujets if isinstance(s, str) and s.strip()]
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture sujets_clos_conversation) : {e}")
        return []


def ajouter_sujet_clos(conversation_id, description):
    """Ajoute un sujet a la liste sans jamais ecraser les precedents (pas de
    doublon, plafonnee a _MAX_SUJETS_CLOS)."""
    description = (description or "").strip()
    if not conversation_id or not description:
        return
    try:
        sujets = lire_sujets_clos(conversation_id)
        if description not in sujets:
            sujets.append(description)
        supabase.table("sujets_clos_conversation").upsert({
            "conversation_id": str(conversation_id),
            "sujets": sujets[-_MAX_SUJETS_CLOS:],
        }).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (ecriture sujets_clos_conversation) : {e}")


def alleger_historique_ancien(historique, conversation_id=None):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes par
    le frontend. Renvoie une NOUVELLE liste, meme longueur, memes roles et
    memes `outils`. Seul `content` change, pour les messages alleges.

    Mecanisme principal : tout message qui parle d'un sujet marque clos par le
    modele est allege, quelle que soit sa position (un vieux sujet clos peut
    etre allege meme entoure de sujets encore actifs).

    Filet de securite : si le volume reste au-dessus du seuil dur, les plus
    vieux messages restants sont alleges, en epargnant d'abord ceux dont le
    sujet reste present dans les echanges recents.

    Ne fait rien (et ne lit pas la base) tant que la conversation reste courte.
    """
    if not historique:
        return historique
    if calculer_taille_historique(historique) < seuil_affichage_note():
        return historique

    n = len(historique)
    limite_protegee = max(0, n - _MESSAGES_RECENTS_PROTEGES)
    resultat = list(historique)

    # Etape 1 : allegement par sujet clos, decide par le modele.
    sujets_mots = [m for m in (mots_significatifs(s) for s in lire_sujets_clos(conversation_id)) if len(m) >= 2]
    if sujets_mots:
        for i in range(limite_protegee):
            contenu = resultat[i].get("content") or ""
            if _est_rappel(contenu):
                continue
            rappel = _pointeur_message(resultat[i].get("role"), contenu)
            if not _peut_alleger(contenu, rappel):
                continue
            mots_message = mots_significatifs(contenu)
            if any(sujet_correspond(mots_sujet, mots_message) for mots_sujet in sujets_mots):
                resultat[i] = {**resultat[i], "content": rappel}

    # Etape 2 : filet de securite, seulement si le volume reste excessif.
    taille_restante = calculer_taille_historique(resultat)
    if taille_restante > SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
        mots_zone_recente = set()
        for i in range(limite_protegee, n):
            mots_zone_recente |= mots_significatifs(resultat[i].get("content") or "")

        candidats = [i for i in range(limite_protegee) if not _est_rappel(resultat[i].get("content"))]
        for proteger_sujets_actifs in (True, False):
            for i in candidats:
                if taille_restante <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
                    break
                contenu = resultat[i].get("content") or ""
                if _est_rappel(contenu):
                    continue
                rappel = _pointeur_message(resultat[i].get("role"), contenu)
                if not _peut_alleger(contenu, rappel):
                    continue
                if proteger_sujets_actifs and chevauchement_fort(mots_significatifs(contenu), mots_zone_recente):
                    continue
                resultat[i] = {**resultat[i], "content": rappel}
                taille_restante -= len(contenu) - len(rappel)
            if taille_restante <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
                break

    return resultat


def note_avancement_historique(historique_allege):
    """
    Ligne ajoutee au prompt systeme quand la taille de ce qui est envoye au
    modele approche du seuil doux. Se base sur l'historique DEJA allege (ce
    qui part reellement), pas sur le texte brut du frontend qui, lui, ne
    diminue jamais. Chaine vide tant que la taille reste confortable.
    """
    taille = calculer_taille_historique(historique_allege)
    if taille < seuil_affichage_note():
        return ""
    return (
        f"[Suivi interne, n'en parle jamais à l'utilisateur. Taille de l'historique envoyé à chaque "
        f"message : {taille} caractères sur {SEUIL_CARACTERES_HISTORIQUE_CONVERSATION} de limite. "
        f"Quand ce chiffre approche ou dépasse la limite, appelle marquer_sujet_clos pour chaque "
        f"sujet de la conversation qui est réellement terminé. Ne clos jamais un sujet encore en "
        f"cours ou sur lequel l'utilisateur peut revenir bientôt.]"
    )


def _demander_cloture_sujets(system_prompt, historique_allege, conversation_id):
    """
    Redemande AU MEME MODELE (DeepSeek, celui de la conversation normale), avec
    son contexte reel (prompt systeme et historique deja allege), de relire la
    conversation et de cloturer lui-meme, via marquer_sujet_clos, les sujets
    qu'il juge reellement termines. Personne d'autre ne devine a sa place :
    seul le modele qui a mene l'echange peut juger de ce qui est termine.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages += [
        {"role": m.get("role"), "content": m.get("content") or ""}
        for m in historique_allege
        if m.get("role") in ("user", "assistant")
    ]
    messages.append({
        "role": "user",
        "content": (
            "[Vérification automatique, ce n'est pas une nouvelle question de l'utilisateur, "
            "ne réponds pas à la conversation.] Relis l'échange ci-dessus : y a-t-il un ou "
            "plusieurs sujets clairement terminés que tu n'as pas encore marqués avec "
            "marquer_sujet_clos ? Si oui, appelle cet outil maintenant, une fois par sujet "
            "concerné. S'il n'y a rien de clairement terminé, n'appelle rien."
        ),
    })

    schema_marquer_sujet_clos = {
        "type": "function",
        "function": {
            "name": "marquer_sujet_clos",
            "description": "Marque un sujet de cette conversation comme terminé, pour l'alléger dans les prochains messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Quelques mots identifiant le sujet clos, avec un vocabulaire proche des messages concernés.",
                    }
                },
                "required": ["description"],
            },
        },
    }

    client_deepseek = OpenAI(api_key=get_secret("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    completion = client_deepseek.chat.completions.create(
        model=DEEPSEEK_PRIMARY,
        messages=messages,
        tools=[schema_marquer_sujet_clos],
        tool_choice="auto",
        timeout=_DELAI_RATTRAPAGE_SECONDES,
    )
    for appel in (completion.choices[0].message.tool_calls or []):
        try:
            description = (json.loads(appel.function.arguments).get("description") or "").strip()
            if description:
                ajouter_sujet_clos(conversation_id, description)
        except Exception as e:
            logging.error(f"ERREUR lecture d'un appel marquer_sujet_clos (rattrapage) : {e}")


def forcer_cloture_sujets_en_arriere_plan(system_prompt, historique, conversation_id):
    """
    Rattrapage (demande Bourama du 27/09/2026) : si le modele n'a pas assez
    cloture de sujets lui-meme et que la taille reste au-dessus du seuil doux,
    un second appel dedie tourne en arriere-plan, APRES l'envoi de la reponse.
    A appeler aux memes endroits que _finaliser_memoire_en_arriere_plan
    (persistance_echanges.py). Ne retarde jamais la reponse, toute erreur est
    loguee ici. Ne fait rien, et ne coute rien, si l'allegement deja connu
    suffit ou si une tentative recente a deja eu lieu pour cette conversation.
    """
    if not conversation_id or not historique:
        return

    def _tache():
        try:
            deja_allege = alleger_historique_ancien(historique, conversation_id)
            if calculer_taille_historique(deja_allege) <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION:
                return

            n = len(historique)
            cle = str(conversation_id)
            with _verrou_tentatives:
                derniere = _tentatives_rattrapage.get(cle)
                if derniere is not None and 0 <= n - derniere < _ECART_MIN_TENTATIVES:
                    return
                if len(_tentatives_rattrapage) > 2000:
                    _tentatives_rattrapage.clear()
                _tentatives_rattrapage[cle] = n

            _demander_cloture_sujets(system_prompt, deja_allege, conversation_id)
        except Exception as e:
            logging.error(f"ERREUR tache de fond (cloture sujets historique) : {e}")

    threading.Thread(target=_tache, daemon=True).start()
