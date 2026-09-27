"""
Outil MCP "rappeler_echange_conversation" (27/09/2026, demande explicite
Bourama, meme chantier que core/outils_rappel_resultats.py mais applique
au texte des MESSAGES (questions/reponses) plutot qu'aux resultats
d'outils -- voir core/historique_conversation.py pour la partie qui
remplace les vieux messages par un simple rappel avant l'envoi au modele.

Meme choix de conception que outils_rappel_resultats.py, pour les memes
raisons (voir sa docstring) : recherche par DESCRIPTION plutot que par
identifiant (le frontend n'envoie aucun id de message), via conversation_id
lu directement depuis ctx, requete directement contre historique_
conversations (deja sauvegarde pour l'affichage, voir
core/persistance_echanges.py) -- aucune nouvelle table, aucune migration.

Expose cote CHAT SEULEMENT, jamais sur le serveur MCP public.
"""

import logging

from constantes_agent import supabase
from core.outils_generation_commun import mcp_generation, Context

# Meme esprit que core/outils_rappel_resultats.py : au-dela, trop vieux
# pour valoir la peine d'etre refouille automatiquement.
_LIMITE_LIGNES_RELUES = 300

# Un echange = la question ET sa reponse -- renvoyer les deux donne au
# modele le contexte complet du moment, pas juste une moitie.
_LIMITE_ECHANGES_RENVOYES = 3


def _mots(texte):
    return set((texte or "").lower().split())


def _rechercher(conversation_id, requete):
    lignes = (
        supabase.table("historique_conversations")
        .select("role, content, parent_id, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(_LIMITE_LIGNES_RELUES)
        .execute()
    ).data or []

    requete_mots = _mots(requete)
    scores = [
        (len(requete_mots & _mots(ligne.get("content"))), i)
        for i, ligne in enumerate(lignes)
    ]
    scores = [(s, i) for s, i in scores if s > 0]
    scores.sort(key=lambda c: c[0], reverse=True)

    # Pour chaque message trouve, renvoie l'ECHANGE complet (question +
    # reponse) plutot que la seule ligne qui a matche -- une question
    # utilisateur trouvee sans sa reponse (ou l'inverse) serait a moitie
    # inutile au modele.
    indices_echanges = []
    for _, i in scores:
        paire = (i, i + 1) if lignes[i]["role"] == "user" else (i - 1, i)
        if paire not in indices_echanges:
            indices_echanges.append(paire)
        if len(indices_echanges) >= _LIMITE_ECHANGES_RENVOYES:
            break

    resultat = []
    for debut, fin in indices_echanges:
        for i in (debut, fin):
            if 0 <= i < len(lignes):
                resultat.append(lignes[i])
    return resultat


@mcp_generation.tool()
def rappeler_echange_conversation(requete: str, ctx: Context) -> str:
    """
    Rappelle le texte COMPLET d'un échange (question + réponse) déjà eu
    plus tôt dans cette même conversation, sans redemander à
    l'utilisateur de le répéter.

    À utiliser quand l'historique mentionne qu'un message plus ancien a
    été allégé ("[Message plus tôt dans cette conversation -- ...]") et
    que son contenu complet redevient utile pour répondre à la question
    actuelle.

    RÈGLE IMPORTANTE : si l'utilisateur fait référence à quelque chose
    évoqué plus tôt ("comme je disais", "reprends ce qu'on a vu avant",
    ou simplement une question qui suppose un contexte déjà donné),
    appelle cet outil AVANT de répondre plutôt que de deviner ou de
    demander à l'utilisateur de se répéter.

    `requete` : décris en quelques mots le sujet de l'échange recherché
    -- ex. "ce qu'on avait dit sur son projet de voyage", "la liste
    qu'elle avait donnée plus tôt".
    """
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")
    if not conversation_id:
        return "Erreur : impossible d'identifier la conversation."
    if not (requete or "").strip():
        return "Erreur : décris le sujet de l'échange que tu cherches."

    try:
        lignes = _rechercher(conversation_id, requete)
    except Exception as e:
        logging.error(f"ERREUR rappeler_echange_conversation : {e}")
        return "Erreur technique pour rappeler cet échange, demande une reformulation à l'utilisateur si besoin."

    if not lignes:
        return "Aucun échange archivé ne correspond à cette description."

    libelle = {"user": "Utilisateur", "assistant": "Assistant"}
    return "\n\n".join(f"{libelle.get(l['role'], l['role'])} : {l.get('content') or ''}" for l in lignes)
