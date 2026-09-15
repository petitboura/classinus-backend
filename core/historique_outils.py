"""
Ajoute le 15/09/2026 (demande Bourama) : jusqu'ici, l'historique renvoye
par le frontend a chaque nouveau message ne contenait que le texte final
(role/content) -- tout resultat d'outil obtenu a un tour precedent
(lecture de bibliotheque, skill, recherche web, code recu...) etait donc
invisible pour le modele au tour suivant, qui devait rappeler l'outil pour
le "redecouvrir". Ce module reinjecte ces resultats dans ce qui part au
modele (voir core/main.py, construction de messages_base).

Format choisi : le resultat de chaque outil est prefixe DANS le contenu du
message assistant concerne (pas un message separe) -- garde une stricte
alternance user/assistant, identique a la structure d'origine de
l'historique, donc aucune adaptation par fournisseur necessaire (Groq,
DeepSeek, Gemini, premium) contrairement au format natif tool_calls/
tool_call_id (propre a Groq/OpenAI) : un outil deja execute a un tour
PASSE n'est plus un appel en attente de reponse protocolaire, juste un
fait de contexte.

Budget : voir SEUIL_CARACTERES_OUTILS_HISTORIQUE (constantes_agent.py) et
_resumer_outils_anciens ci-dessous -- meme principe que le resume memoire
long terme existant (_mettre_a_jour_resume_si_besoin,
persistance_echanges.py) : au-dela du seuil, les resultats les plus
ANCIENS sont condenses en un seul resume via MODELE_RESUME, les plus
RECENTS restent intacts.
"""

import logging
from groq import Groq
from constantes_agent import get_secret, MODELE_RESUME, DELAI_MAX_PAR_APPEL, SEUIL_CARACTERES_OUTILS_HISTORIQUE


def _bloc_outil(o):
    """Un seul resultat d'outil (voir api/chat.py:OutilHistorique), mis en
    forme pour le modele."""
    nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
    resultat = o.get("resultat") or ""
    return f"[Résultat de l'outil déjà exécuté -- {nom}]\n{resultat}"


def _resumer_outils_anciens(blocs_texte):
    """
    Condense une liste de blocs de resultats d'outils devenus trop
    volumineux en UN SEUL resume factuel, via le meme modele rapide que
    _mettre_a_jour_resume_si_besoin (persistance_echanges.py). Toute
    erreur ici est geree par l'appelant (repli sur une troncature simple)
    -- ne doit jamais faire echouer tout le message.
    """
    transcription = "\n\n".join(blocs_texte)
    instruction = (
        "Condense les résultats d'outils suivants (recherches, lectures de "
        "documents, code reçu, etc., obtenus plus tôt dans cette même "
        "conversation) en un résumé factuel et concis qui garde toutes les "
        "informations concrètes utiles (chiffres, noms, faits, extraits de "
        "code pertinents), sans reformuler en réponse ni ajouter de "
        "commentaire. Ne réponds à rien, résume seulement."
    )
    client_groq = Groq(api_key=get_secret("GROQ_API_KEY"), max_retries=0)
    completion = client_groq.chat.completions.create(
        model=MODELE_RESUME,
        messages=[
            {"role": "system", "content": instruction},
            {"role": "user", "content": transcription},
        ],
        max_completion_tokens=None,
        timeout=DELAI_MAX_PAR_APPEL,
    )
    return completion.choices[0].message.content.strip()


def enrichir_historique_avec_outils(historique):
    """
    `historique` : liste de dicts {role, content, outils?} tels qu'envoyes
    par le frontend (voir api/chat.py:MessageHistorique -- `outils`
    provient de meta.outils, deja sauvegarde pour l'affichage, voir
    core/persistance_echanges.py). Renvoie une NOUVELLE liste (n'altere
    jamais l'original), meme longueur, memes roles -- seul le `content`
    des messages assistant concernes est enrichi.

    Ignore silencieusement (renvoie l'historique tel quel) si aucun
    message n'a d'outils, ou si le resume de secours echoue ET que la
    troncature de secours suffit -- ce module ne doit jamais faire
    planter un message pour cette seule raison.
    """
    blocs = []  # [(index_message, texte_du_bloc)], ordre chronologique
    for i, m in enumerate(historique):
        if m.get("role") != "assistant":
            continue
        for o in (m.get("outils") or []):
            blocs.append((i, _bloc_outil(o)))

    if not blocs:
        return historique

    taille_totale = sum(len(t) for _, t in blocs)

    if taille_totale > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
        # Garde les plus RECENTS intacts (en partant de la fin), condense
        # le reste (les plus ANCIENS) en un seul resume.
        taille_cumulee_recente = 0
        coupure = len(blocs)
        for k in range(len(blocs) - 1, -1, -1):
            taille_cumulee_recente += len(blocs[k][1])
            if taille_cumulee_recente > SEUIL_CARACTERES_OUTILS_HISTORIQUE:
                coupure = k + 1
                break
        anciens, recents = blocs[:coupure], blocs[coupure:]
        if anciens:
            try:
                resume = _resumer_outils_anciens([t for _, t in anciens])
            except Exception as e:
                logging.error(f"ERREUR résumé outils historique (repli sur troncature) : {e}")
                resume = "\n\n".join(t[:500] for _, t in anciens)
            # Rattache au tour le plus ancien concerne, pour rester au
            # plus pres de sa place chronologique d'origine.
            blocs = [(anciens[0][0], f"[Résumé des outils exécutés plus tôt dans cette conversation]\n{resume}")] + recents

    par_index = {}
    for idx, texte in blocs:
        par_index.setdefault(idx, []).append(texte)

    resultat = []
    for i, m in enumerate(historique):
        if i in par_index:
            contexte = "\n\n".join(par_index[i])
            contenu = f"{contexte}\n\n[Réponse donnée à ce moment-là]\n{m['content']}"
            resultat.append({"role": m["role"], "content": contenu})
        else:
            resultat.append({"role": m["role"], "content": m["content"]})
    return resultat
