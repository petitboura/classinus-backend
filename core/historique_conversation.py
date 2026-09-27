"""
Ajoute le 27/09/2026 (demande explicite Bourama, "reduire les couts sans
jamais perdre de contexte") -- voir aussi core/outils_rappel_historique.py
(recuperation d'un vieux message) et core/outils_gestion_historique.py
(marquage d'un sujet comme clos par le modele lui-meme).

Historique de ce fichier : la toute premiere version (v1) coupait a une
position fixe (les N derniers caracteres intacts, le reste allege). Defaut
signale par Bourama : une coupure a position fixe peut tomber en plein
milieu d'un sujet encore actif (ex. sujet1/sujet2/sujet3/sujet1/sujet1/
sujet3 -- une coupure aveugle casse un sujet qui revient plus tard). v2
(celle-ci) : c'est le modele LUI-MEME qui decide quel sujet est clos et
peut etre allege, via l'outil marquer_sujet_clos -- ce qui coute quasiment
rien puisque le morceau concerne est de toute facon deja envoye et paye ce
tour-ci (voir discussion complete, pas de nouvel appel separe). La
position fixe ne sert plus que de FILET DE SECURITE, si le modele n'a
jamais rien marque et que le volume devient vraiment excessif.

Deux seuils (constantes_agent.py) :
- SEUIL_CARACTERES_HISTORIQUE_CONVERSATION (le "doux", ex. 5000) : objectif
  affiche au modele a chaque tour ("ne laisse pas l'historique depasser
  ca"). Rien n'est force automatiquement a ce niveau -- c'est une
  EXIGENCE posee au modele, pas une coupe de notre cote.
- SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX (le "dur", ex. 8000) :
  au-dela, si le modele n'a pas suffisamment allege lui-meme, on force
  une coupe a position fixe sur ce qui reste -- uniquement comme garde-fou
  de derniere ligne, jamais le mecanisme principal.
"""

import json
import logging
import threading

from openai import OpenAI
from constantes_agent import (
    supabase,
    get_secret,
    DEEPSEEK_PRIMARY,
    DELAI_MAX_PAR_APPEL,
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION,
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX,
)

_LONGUEUR_APERCU = 80
_LIBELLE_ROLE = {"user": "question de l'utilisateur", "assistant": "réponse de l'IA"}

# Les tout derniers messages ne sont JAMAIS allegees, meme si un sujet
# clos les recouvre par erreur -- l'echange en cours doit toujours rester
# lisible tel quel pour le modele.
_MESSAGES_RECENTS_PROTEGES = 4


def _mots(texte):
    return set((texte or "").lower().split())


def _apercu(texte):
    texte = (texte or "").strip().replace("\n", " ")
    if len(texte) <= _LONGUEUR_APERCU:
        return texte
    return texte[:_LONGUEUR_APERCU].rstrip() + "…"


def _pointeur_message(role, contenu):
    libelle = _LIBELLE_ROLE.get(role, role)
    return (
        f"[Message plus tôt dans cette conversation -- {libelle}, sujet : "
        f"\"{_apercu(contenu)}\". Texte complet non affiché ici -- utilise "
        f"rappeler_echange_conversation si tu as besoin de le relire.]"
    )


def calculer_taille_historique(historique):
    return sum(len(m.get("content") or "") for m in (historique or []))


def lire_sujets_clos(conversation_id):
    """
    Sujets que le modele a lui-meme marques comme clos (voir
    core/outils_gestion_historique.py:marquer_sujet_clos) pour cette
    conversation -- s'accumule au fil du temps (jamais ecrase), contrairement
    a outils_retenus_conversation qui repart de zero chaque tour : une fois
    un sujet clos, il le reste pour le reste de la conversation. Liste
    vide si rien n'est marque, si conversation_id est absent, ou en cas
    d'erreur Supabase -- fail-safe strict, ne doit jamais bloquer la
    reponse normale.
    """
    if not conversation_id:
        return []
    try:
        res = (
            supabase.table("sujets_clos_conversation")
            .select("sujets")
            .eq("conversation_id", conversation_id)
            .maybe_single()
            .execute()
        )
        return ((res.data if res else None) or {}).get("sujets") or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture sujets_clos_conversation) : {e}")
        return []


def ajouter_sujet_clos(conversation_id, description):
    """
    Ajoute un sujet a la liste (sans jamais ecraser les precedents) --
    appele par l'outil marquer_sujet_clos. Deduplique simplement (pas
    deux fois la meme description).
    """
    if not conversation_id or not (description or "").strip():
        return
    try:
        sujets = lire_sujets_clos(conversation_id)
        if description not in sujets:
            sujets.append(description)
        supabase.table("sujets_clos_conversation").upsert({
            "conversation_id": conversation_id,
            "sujets": sujets,
        }).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (ecriture sujets_clos_conversation) : {e}")


def _correspond_a_un_sujet_clos(contenu, sujets_clos_mots):
    mots_message = _mots(contenu)
    return any(mots_message & mots_sujet for mots_sujet in sujets_clos_mots)


def alleger_historique_ancien(historique, conversation_id=None):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes
    par le frontend. Renvoie une NOUVELLE liste, meme longueur, memes
    roles et memes `outils` -- seul `content` change pour les messages
    concernes par un sujet clos ou (en dernier recours) trop anciens.

    Mecanisme PRINCIPAL : tout message dont le contenu recoupe un sujet
    marque clos par le modele (lire_sujets_clos) est allege, QUELLE QUE
    SOIT SA POSITION -- un vieux sujet clos peut etre allege meme s'il est
    entoure de sujets encore actifs plus recents (voir docstring du
    fichier, cas sujet1/sujet2/sujet3/sujet1/sujet1/sujet3).

    FILET DE SECURITE, seulement si necessaire : si apres ca le volume
    total depasse encore SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX, on
    force l'allegement des messages les plus anciens restants (position
    fixe, en partant du debut) jusqu'a repasser sous ce seuil dur -- pour
    ne jamais laisser une conversation grossir sans fin si le modele
    n'a pas assez allege lui-meme.
    """
    if not historique:
        return historique

    n = len(historique)
    limite_protegee = max(0, n - _MESSAGES_RECENTS_PROTEGES)

    sujets_clos_mots = [_mots(s) for s in lire_sujets_clos(conversation_id)]

    resultat = list(historique)

    # 1) Mecanisme principal : allegement par sujet clos, decide par le
    # modele -- sur toute la conversation SAUF les tout derniers messages.
    if sujets_clos_mots:
        for i in range(limite_protegee):
            m = resultat[i]
            contenu = m.get("content") or ""
            if not contenu.startswith("[Message plus tôt") and _correspond_a_un_sujet_clos(contenu, sujets_clos_mots):
                resultat[i] = {**m, "content": _pointeur_message(m.get("role"), contenu)}

    # 2) Filet de securite : seulement si le volume reste excessif malgre
    # l'etape 1 (ou si le modele n'a rien marque du tout). Pas une coupe
    # aveugle : on evite d'abord de couper un message dont des mots se
    # retrouvent dans la zone recente (signe que ce sujet est probablement
    # encore actif, cf. le cas sujet1/sujet2/sujet3/sujet1/sujet1/sujet3
    # signale par Bourama) -- on ne force la coupe dessus qu'en tout
    # dernier recours, si rien d'autre ne suffit a repasser sous le seuil.
    taille_restante = calculer_taille_historique(resultat)
    if taille_restante > SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
        mots_zone_recente = set()
        for i in range(limite_protegee, n):
            mots_zone_recente |= _mots(resultat[i].get("content") or "")

        candidats = [
            i for i in range(limite_protegee)
            if not (resultat[i].get("content") or "").startswith("[Message plus tôt")
        ]
        for proteger_sujets_actifs in (True, False):
            if taille_restante <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
                break
            for i in list(candidats):
                if taille_restante <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION_MAX:
                    break
                contenu = resultat[i].get("content") or ""
                if proteger_sujets_actifs and (_mots(contenu) & mots_zone_recente):
                    continue  # sujet probablement encore actif, protege pour l'instant
                resultat[i] = {**resultat[i], "content": _pointeur_message(resultat[i].get("role"), contenu)}
                taille_restante -= len(contenu)
                candidats.remove(i)

    return resultat


def note_avancement_historique(historique):
    """
    Ligne a afficher au modele a chaque tour (ajoutee au prompt systeme,
    voir core/main.py) pour qu'il puisse suivre lui-meme s'il approche de
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION et doive marquer des sujets
    clos. Se base sur le volume BRUT (avant tout allegement de notre
    cote) : c'est la vraie taille de la conversation que le modele doit
    surveiller, pas notre representation interne deja compressee.
    """
    taille = calculer_taille_historique(historique)
    return (
        f"[Suivi de la taille de l'historique : {taille}/"
        f"{SEUIL_CARACTERES_HISTORIQUE_CONVERSATION} caractères. Si ce "
        f"nombre approche ou dépasse la limite, utilise dès maintenant "
        f"marquer_sujet_clos pour chaque sujet de cette conversation qui "
        f"est réellement terminé -- ne laisse jamais ce chiffre dépasser "
        f"la limite sans avoir clos au moins un sujet.]"
    )


def _demander_cloture_sujets(system_prompt, historique, conversation_id):
    """
    CORRECTIF (27/09/2026, Bourama : "comment nous on peut savoir que
    c'est clos, ça n'a pas de sens, nous on ne peut pas repérer les
    sujets terminés"). Version precedente (fautive) : un petit modele
    separe (MODELE_RESUME) recevait un extrait tronque de la conversation
    et devait DEVINER quels sujets etaient "clairement termines" -- sans
    le contexte complet ni la comprehension que seul le modele ayant
    reellement mene la conversation peut avoir. Ca n'a pas de sens : ni
    nous ni un petit modele hors contexte ne pouvons juger a la place du
    modele qui a suivi l'echange.

    Version correcte : on redemande directement AU MEME MODELE (DeepSeek,
    la meme cascade que la conversation normale, pas un modele au rabais)
    de relire SA PROPRE conversation, avec son plein contexte (system
    prompt + historique complet), et de cloturer lui-meme -- via le meme
    outil marquer_sujet_clos qu'il a deja -- les sujets qu'il juge
    reellement termines. On ne fait que le relancer une fois de plus sur
    ce qu'il connait deja, on ne demande a personne d'autre de deviner.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m.get("role"), "content": m.get("content") or ""} for m in historique]
    messages.append({
        "role": "user",
        "content": (
            "[Vérification automatique -- pas une nouvelle question de "
            "l'utilisateur, ne réponds pas à la conversation] Relis "
            "l'échange ci-dessus : y a-t-il un ou plusieurs sujets "
            "clairement terminés que tu n'as pas encore marqués avec "
            "marquer_sujet_clos ? Si oui, appelle cet outil maintenant, "
            "une fois par sujet concerné. S'il n'y a rien de clairement "
            "terminé, n'appelle rien."
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
        timeout=DELAI_MAX_PAR_APPEL,
    )
    for appel in (completion.choices[0].message.tool_calls or []):
        try:
            description = (json.loads(appel.function.arguments).get("description") or "").strip()
            if description:
                ajouter_sujet_clos(conversation_id, description)
        except Exception as e:
            logging.error(f"ERREUR parsing appel marquer_sujet_clos (rattrapage) : {e}")


def forcer_cloture_sujets_en_arriere_plan(system_prompt, historique, conversation_id):
    """
    Filet de securite (27/09/2026, demande explicite Bourama : "un
    deuxieme appel en parallele, apres que l'utilisateur ait vu sa
    reponse, qui ne sert qu'a demander de tronquer"). A appeler aux memes
    endroits que _finaliser_memoire_en_arriere_plan (persistance_echanges.py),
    APRES que la reponse a deja ete envoyee -- fire-and-forget, ne retarde
    jamais la reponse a la personne, toute erreur reste loguee ici.

    Ne se declenche QUE si le modele n'a pas suffisamment cloture de
    sujets lui-meme ce tour-ci (marquer_sujet_clos, mecanisme principal,
    gratuit) : si l'allegement deja connu suffit a repasser sous
    SEUIL_CARACTERES_HISTORIQUE_CONVERSATION, cette fonction ne fait rien
    et ne coute rien. Objectif : au prochain tour, le modele voit deja le
    sujet cloture (via note_avancement_historique) AVANT meme de
    commencer sa reponse -- il n'a donc plus besoin de s'en souvenir lui
    meme si le tour precedent l'a rate.
    """
    if not conversation_id or not historique:
        return

    def _tache():
        try:
            taille = calculer_taille_historique(historique)
            if taille <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION:
                return  # sous le seuil doux, rien a faire

            deja_allege = alleger_historique_ancien(historique, conversation_id)
            if calculer_taille_historique(deja_allege) <= SEUIL_CARACTERES_HISTORIQUE_CONVERSATION:
                return  # les sujets deja connus suffisent, le modele a bien fait son travail

            _demander_cloture_sujets(system_prompt, historique, conversation_id)
        except Exception as e:
            logging.error(f"ERREUR tache de fond (clôture sujets historique) : {e}")

    threading.Thread(target=_tache, daemon=True).start()
