"""
Outil MCP "marquer_sujet_clos" (27/09/2026, demande explicite Bourama).

Plutot qu'une coupure automatique a position fixe (qui risque de couper un
sujet encore actif), c'est le modele LUI-MEME qui decide quel sujet est
termine et peut etre allege. Cout quasi nul : le morceau concerne est de
toute facon deja envoye a ce tour-ci, on ajoute seulement un petit appel
d'outil a une reponse deja en cours. Contexte complet : voir
core/historique_conversation.py.

Le sujet marque est stocke pour la conversation (voir
historique_conversation.py:ajouter_sujet_clos) et reste actif pour tout le
reste de la conversation.

Expose cote CHAT SEULEMENT, jamais sur le serveur MCP public.
"""

import logging

from core.outils_generation_commun import mcp_generation, Context
from core.historique_conversation import ajouter_sujet_clos


@mcp_generation.tool()
def marquer_sujet_clos(description: str, ctx: Context) -> str:
    """
    Marque un sujet de la conversation actuelle comme terminé, pour alléger
    les messages qui le concernent et réduire ce qui est renvoyé à chaque tour
    suivant. Rien n'est perdu : le contenu reste récupérable via
    rappeler_echange_conversation si le sujet revenait.

    QUAND L'UTILISER : quand un sujet abordé plus tôt est clairement résolu
    (la question a eu sa réponse, le besoin est satisfait, il est très peu
    probable qu'on y revienne), surtout si le suivi de taille indiqué dans tes
    instructions approche ou dépasse la limite. Un même tour peut appeler cet
    outil plusieurs fois pour plusieurs sujets différents.

    NE PAS l'utiliser pour un sujet encore actif, même ancien dans la
    conversation, ou sur lequel l'utilisateur pourrait raisonnablement revenir
    bientôt.

    `description` : quelques mots qui identifient le sujet, avec un
    vocabulaire proche de celui des messages concernés (par exemple
    "réservation de l'hôtel à Sousse" ou "correction du bug de connexion").
    Elle sert ensuite à repérer les messages à alléger.
    """
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")
    if not conversation_id:
        return "Erreur : impossible d'identifier la conversation."
    if not (description or "").strip():
        return "Erreur : décris le sujet à clore en quelques mots."

    try:
        ajouter_sujet_clos(conversation_id, description.strip())
    except Exception as e:
        logging.error(f"ERREUR marquer_sujet_clos : {e}")
        return "Erreur technique, le sujet n'a pas pu être marqué comme clos."

    return f"Sujet marqué comme clos : {description.strip()}"
