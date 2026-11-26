"""
Outil de question à l'utilisateur pendant que Classinus travaille (chat normal).

Chantier "messages et questions pendant que Classinus travaille" (25/11/2026,
demande de Bourama). Voir core/questions_utilisateur.py pour le principe.

Outil exposé UNIQUEMENT côté chat (@mcp_generation.tool()), comme
core/outils_action_agent.py. L'affichage de la carte ne passe pas par cet outil :
core/execution_outils.py émet l'événement "question_en_direct" avant l'appel,
puis donne à l'outil l'identifiant de l'appel (paramètre id_question).
"""

from core.canal_agent_applicatif import attendre_reponse_question as _attendre_reponse_question
from core.outils_generation_commun import mcp_generation, Context
from core.questions_utilisateur import delai_question_secondes, est_bloquante, lire_question


def _duree_lisible(secondes: int) -> str:
    if secondes >= 120 and secondes % 60 == 0:
        return f"{secondes // 60} minutes"
    if secondes == 60:
        return "1 minute"
    return f"{secondes} secondes"


@mcp_generation.tool()
async def poser_question(
    question: str,
    ctx: Context,
    bloquante: bool = False,
    id_question: str = "",
) -> str:
    """
    Pose une question a l'utilisateur dans une carte interactive du chat,
    PENDANT que tu travailles, sans interrompre ton tour.

    `question` : le JSON d'une question, le meme que celui d'un bloc question
    de ton message (champs type et question, plus choix, autre, etc. selon le
    type), envoye comme texte.

    `bloquante` : decide ce que fait l'appel.
    - faux (par defaut) : ta tache peut continuer sans la reponse. L'appel
      rend la main tout de suite. Continue ton travail avec l'hypothese la
      plus raisonnable. La reponse de l'utilisateur t'arrivera comme un
      message pendant que tu agis, ou au tour suivant s'il repond plus tard.
    - vrai : tu ne peux vraiment pas avancer sans la reponse. L'appel reste en
      attente de la reponse dans ce meme tour. Ne t'arrete pas pour ecrire ta
      question dans un message que l'utilisateur lirait ensuite : appelle cet
      outil, c'est la difference.

    Si l'utilisateur ne repond pas dans le delai, l'outil te le dit. Termine
    alors ton tour normalement : explique que tu ne peux pas continuer sans
    cette reponse, puis repose la meme question dans ton message.

    `id_question` : ne le renseigne jamais, il est rempli par le serveur.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if lire_question(question) is None:
        return (
            "Erreur : paramètre 'question' invalide. Envoie le JSON d'une question "
            "(champ type et champ question), ou pose-la dans un bloc question de ton message."
        )

    if not est_bloquante(bloquante):
        return (
            "Question affichée à l'utilisateur. Continue ton travail sans attendre : sa réponse "
            "t'arrivera comme un message pendant que tu agis, ou au tour suivant s'il répond plus tard."
        )

    if not id_question:
        return (
            "Erreur : cette question ne peut pas rester en attente ici. Écris-la dans un bloc "
            "question de ton message."
        )

    delai = delai_question_secondes()
    reponse = await _attendre_reponse_question(user_id, id_question, delai)

    if reponse is None:
        return (
            f"Pas de réponse de l'utilisateur après {_duree_lisible(delai)}. Termine ton tour "
            "normalement : explique que tu ne peux pas continuer sans cette réponse, puis repose "
            "la même question dans ton message."
        )
    if isinstance(reponse, dict):
        if reponse.get("erreur"):
            return f"Question interrompue : {reponse['erreur']}"
        reponse = reponse.get("reponse")
    texte = str(reponse).strip() if reponse is not None else ""
    if not texte:
        return "Question fermée sans réponse. Continue sans elle ou repose-la dans ton message."
    return f"Réponse de l'utilisateur : {texte}"
