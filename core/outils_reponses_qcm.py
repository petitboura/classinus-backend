"""Outil MCP de secours pour lire les réponses QCM d'un étudiant
(23/09/2026, demande Bourama).

Contexte : l'IA n'avait jusqu'ici aucun moyen de savoir ce que l'étudiant
avait répondu à un QCM généré (format ```qcm) -- la réponse était bien
enregistrée (core/historique_reponses_qcm.py, branché le 14/09/2026) mais
jamais relue nulle part. Double sécurité, même principe que
verifier_consignes_code_actif : injection automatique en priorité
(core/main.py, les 2 messages qui suivent un QCM donné par le modèle),
et cet outil pour le reste -- toute réponse plus ancienne que cette
fenêtre, ou si l'injection automatique semble incomplète/absente.

Une fois lu, le résultat reste visible dans l'historique de la
conversation comme n'importe quel outil (voir core/historique_outils.py,
marqué "[Résultat de l'outil déjà exécuté]") -- pas besoin de rappeler
cet outil tant que rien de nouveau n'a été répondu.
"""
import logging

from core.historique_reponses_qcm import lister_reponses_qcm as _lister_reponses_qcm
from core.historique_reponses_qcm import formater_reponses_qcm as _formater_reponses_qcm
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def lire_reponses_qcm(ctx: Context) -> str:
    """
    Renvoie les réponses données par cet étudiant aux QCM (format ```qcm)
    de la conversation en cours : question, réponse choisie, correcte ou
    non, et bonne réponse si l'étudiant s'est trompé.

    Les réponses aux QCM des 2 derniers messages sont déjà injectées
    automatiquement dans ton prompt système juste après qu'un QCM a été
    donné -- n'appelle cet outil que pour un QCM plus ancien dans la
    conversation (l'étudiant y revient plus tard), ou si tu penses que
    l'injection automatique est vide ou incomplète alors qu'un QCM a
    manifestement eu lieu. Si ce même historique a déjà été lu plus tôt
    dans cette conversation (résultat toujours visible, marqué "[Résultat
    de l'outil déjà exécuté]") et qu'aucun nouveau QCM n'a été répondu
    depuis, ne le relis pas -- réponds directement à partir de ce
    résultat. Aucun paramètre.
    """
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")
    if not conversation_id:
        return "Erreur : impossible d'identifier la conversation."
    try:
        reponses = _lister_reponses_qcm(conversation_id)
    except Exception as e:
        logging.error(f"ERREUR lire_reponses_qcm (conversation {conversation_id}) : {e}")
        return "Erreur : impossible de relire les réponses QCM, réessaie."
    if not reponses:
        return "Aucun QCM répondu par cet étudiant dans cette conversation."
    return "Réponses de l'étudiant aux QCM de cette conversation :\n" + _formater_reponses_qcm(reponses)
