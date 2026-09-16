"""
Chantier agent applicatif (voir plan-agent-applicatif-clovis.md),
chantier C.

Outil expose UNIQUEMENT cote chat eleve (@mcp_generation.tool(), jamais
core/registre_outils_public.py ou equivalent serveur MCP public) --
meme logique que core/outils_verification_code_actif.py.

Renomme de "executer_action_appareil" (nom provisoire propose avant la
decision Bourama) en "executer_action_application" : il n'y a plus de
notion d'appareil cible, voir core/canal_agent_applicatif.py.
"""

from core.canal_agent_applicatif import demander_execution_action as _demander_execution_action
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
async def executer_action_application(action_id: str, ctx: Context) -> str:
    """
    Declenche une action dans l'application Clovis a la place de
    l'etudiant (clic, navigation), pour l'action `action_id`. `action_id`
    DOIT etre un identifiant renvoye par la liste des actions
    actuellement disponibles a l'ecran (mecanisme de poussee d'etat,
    chantier D) -- ne jamais deviner ni inventer un identifiant : une
    action qui n'est plus montee a l'ecran echoue proprement plutot que
    de risquer un effet inattendu.

    Si l'action est sensible (marquee comme telle, ou non qualifiee --
    sensible par defaut), une fenetre de confirmation s'affiche cote
    etudiant AVANT toute execution reelle : l'etudiant doit cliquer
    Autoriser. Un refus renvoie un resultat clair, ne pas re-proposer la
    meme action immediatement sans que l'etudiant l'ait redemande.

    NECESSITE que l'application soit ouverte quelque part pour ce
    compte (peu importe l'onglet ou l'appareil, voir
    core/canal_agent_applicatif.py) -- sinon echoue immediatement avec un
    message clair a relayer a l'etudiant.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not action_id:
        return "Erreur : paramètre 'action_id' manquant."

    resultat = await _demander_execution_action(user_id, action_id)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit l'action n'est plus disponible à l'écran nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    if isinstance(resultat, dict) and resultat.get("refuse"):
        return "L'étudiant a refusé cette action dans la fenêtre de confirmation."
    return "Action exécutée avec succès."
