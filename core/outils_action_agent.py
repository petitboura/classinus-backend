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

import json

from core.canal_agent_applicatif import (
    demander_execution_action as _demander_execution_action,
    demander_clic_generique as _demander_clic_generique,
    demander_pointage_action as _demander_pointage_action,
    obtenir_actions_disponibles as _obtenir_actions_disponibles,
)
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
async def lister_actions_disponibles(ctx: Context) -> str:
    """
    Chantier D. Renvoie la liste, a jour a l'instant present, des
    actions que Clovis peut declencher dans l'application pour cet
    etudiant (id, description, sensible, continuerEnArrierePlan) --
    UNIQUEMENT celles reellement montees et actives a l'ecran en ce
    moment meme, jamais une liste apprise ou memorisee d'un tour
    precedent.

    A appeler avant executer_action_application des que la liste
    connue pourrait etre perimee (nouvelle demande de l'etudiant,
    changement d'ecran probable) -- ne jamais reutiliser un action_id
    obtenu il y a plusieurs tours sans revalider qu'il est toujours
    dans cette liste.

    Renvoie une liste vide (pas une erreur) si l'application n'est
    ouverte nulle part pour ce compte, ou si aucune action declaree
    n'est actuellement montee.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    actions = _obtenir_actions_disponibles(user_id)
    return json.dumps(actions, ensure_ascii=False)


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


@mcp_generation.tool()
async def executer_clic_generique(selecteur: str, description: str, ctx: Context) -> str:
    """
    Chantier F : filet de sécurité UNIQUEMENT pour un élément qui n'a
    PAS encore d'action déclarée (voir lister_actions_disponibles).
    Vérifie TOUJOURS lister_actions_disponibles en premier, et n'utilise
    cet outil que si rien dans cette liste ne correspond à ce que
    l'étudiant a demandé -- ne jamais l'utiliser en doublon d'une action
    déjà déclarée.

    `selecteur` est un sélecteur CSS visant un unique élément cliquable
    (bouton, lien...) actuellement affiché. `description` est une
    phrase courte et claire décrivant l'action pour l'étudiant (montrée
    dans la fenêtre de confirmation).

    Contrairement à executer_action_application, ce mode n'a aucune
    métadonnée de sensibilité déclarée : la confirmation est donc
    TOUJOURS demandée à l'étudiant, sans exception, jamais d'exécution
    silencieuse.

    Si l'élément n'est pas trouvé, ou trouvé mais désactivé/invisible,
    l'application le traite comme indisponible plutôt que de risquer un
    clic sur autre chose -- relayer clairement à l'étudiant que l'action
    demandée n'a pas pu être localisée à l'écran.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not selecteur:
        return "Erreur : paramètre 'selecteur' manquant."
    if not description:
        return "Erreur : paramètre 'description' manquant."

    resultat = await _demander_clic_generique(user_id, selecteur, description)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit l'élément visé n'a été trouvé (visible et actif) nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    if isinstance(resultat, dict) and resultat.get("refuse"):
        return "L'étudiant a refusé cette action dans la fenêtre de confirmation."
    return "Action exécutée avec succès."


@mcp_generation.tool()
async def montrer_element_application(action_id: str, ctx: Context) -> str:
    """
    Chantier G : mode guidage / visite guidée. Déplace UNIQUEMENT le
    curseur virtuel vers l'élément de l'action `action_id` (issu de
    lister_actions_disponibles), SANS jamais l'exécuter -- pour montrer
    une nouveauté ou un endroit précis de l'application à l'étudiant.
    Décrire ce que fait cet élément dans le message envoyé à l'étudiant
    au même moment, cet outil ne fait qu'un pointage visuel silencieux.

    Pour une visite en plusieurs étapes, appeler cet outil une fois par
    étape, en laissant l'étudiant lire l'explication entre deux (pause
    à chaque étape, décision Bourama) -- ne jamais enchaîner plusieurs
    pointages sans texte explicatif entre eux.

    Si l'étudiant doit ensuite cliquer lui même, ne pas appeler
    executer_action_application à sa place : laisser l'étudiant agir.
    Si Clovis doit agir à sa place, utiliser executer_action_application
    séparément après (ou à la place de) ce pointage.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if not action_id:
        return "Erreur : paramètre 'action_id' manquant."

    resultat = await _demander_pointage_action(user_id, action_id)

    if resultat is None:
        return (
            "Aucune réponse de l'application : soit elle n'est ouverte nulle part pour ce compte, "
            "soit cette action n'est plus disponible à l'écran nulle part où elle est ouverte."
        )
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Curseur déplacé vers l'élément avec succès."
