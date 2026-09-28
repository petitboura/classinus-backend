"""
Outil MCP "rappeler_echange_conversation" (27/09/2026, demande explicite
Bourama). Meme chantier que core/outils_rappel_resultats.py, applique au
texte des MESSAGES (questions et reponses). Voir
core/historique_conversation.py pour la partie qui remplace les vieux
messages d'un sujet clos par un simple rappel avant l'envoi au modele.

Meme choix de conception : recherche par DESCRIPTION (le frontend n'envoie
aucun identifiant de message), conversation_id lu depuis ctx, relecture dans
historique_conversations (deja sauvegardee pour l'affichage, voir
core/persistance_echanges.py). Aucune nouvelle table.

Expose cote CHAT SEULEMENT, jamais sur le serveur MCP public.
"""

import logging

from core.outils_generation_commun import mcp_generation, Context, _supabase_memoire as supabase
from core.texte_recherche_simple import mots_significatifs

# Nombre de lignes les plus recentes relues pour la recherche (limite le
# volume lu dans Supabase).
_LIMITE_LIGNES_RELUES = 200

# Un echange est la question ET sa reponse : renvoyer les deux donne au
# modele le contexte complet du moment.
_LIMITE_ECHANGES_RENVOYES = 3


def _rechercher(conversation_id, requete):
    lignes = (
        supabase.table("historique_conversations")
        .select("role, content, created_at")
        .eq("conversation_id", str(conversation_id))
        .order("created_at", desc=True)
        .limit(_LIMITE_LIGNES_RELUES)
        .execute()
    ).data or []
    lignes.reverse()  # ordre chronologique

    mots_requete = mots_significatifs(requete)
    if not mots_requete:
        return []
    scores = []
    for i, ligne in enumerate(lignes):
        s = len(mots_requete & mots_significatifs(ligne.get("content")))
        if s > 0:
            scores.append((s, i))
    scores.sort(key=lambda c: c[0], reverse=True)

    # Pour chaque message trouve, renvoie l'ECHANGE complet (question et
    # reponse), pas seulement la ligne qui correspond.
    paires = []
    for _, i in scores:
        paire = (i, i + 1) if lignes[i]["role"] == "user" else (i - 1, i)
        if paire not in paires:
            paires.append(paire)
        if len(paires) >= _LIMITE_ECHANGES_RENVOYES:
            break

    resultat = []
    deja_vus = set()
    for debut, fin in sorted(paires):
        for i in (debut, fin):
            if 0 <= i < len(lignes) and i not in deja_vus:
                deja_vus.add(i)
                resultat.append(lignes[i])
    return resultat


@mcp_generation.tool()
def rappeler_echange_conversation(requete: str, ctx: Context) -> str:
    """
    Rappelle le texte COMPLET d'un échange (question et réponse) déjà eu plus
    tôt dans cette même conversation, sans demander à l'utilisateur de le
    répéter.

    À utiliser quand l'historique indique qu'un message plus ancien a été
    allégé ("[Message plus tôt dans cette conversation : ...]") et que son
    contenu complet redevient utile pour répondre à la question actuelle.

    RÈGLE IMPORTANTE : si l'utilisateur fait référence à quelque chose évoqué
    plus tôt ("comme je disais", "reprends ce qu'on a vu avant", ou une
    question qui suppose un contexte déjà donné), appelle cet outil AVANT de
    répondre plutôt que de deviner ou de demander à l'utilisateur de se
    répéter.

    `requete` : décris en quelques mots le sujet de l'échange recherché, par
    exemple "ce qu'on avait dit sur son projet de voyage" ou "la liste
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
