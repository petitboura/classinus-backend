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
    Chantier D, revise le 17/09/2026 (scan generique, voir
    plan-scan-generique-agent-applicatif.md) puis le 19/09/2026 (retrait
    de la confirmation, voir plan-canal-agent-applicatif-v1.md) : renvoie
    la liste, a jour a l'instant present, des elements cliquables
    (bouton, lien, champ) reellement visibles et actifs a l'ecran de
    l'etudiant en ce moment meme (id, description, continuerEnArrierePlan)
    -- plus aucun element n'est declare a la main, tout est detecte
    automatiquement par un scan du DOM cote frontend.

    La description de chaque element est generee automatiquement (texte
    visible du bouton/lien, ou a defaut son libelle d'accessibilite) --
    elle peut donc etre generique, courte, ou ambigue (ex. deux boutons
    "Modifier" sur le meme ecran). Se fier au contexte de la conversation
    pour choisir le bon element, et consulter la base de connaissance de
    Clovis en cas de doute reel plutot que de deviner.

    A appeler avant executer_action_application des que la liste
    connue pourrait etre perimee (nouvelle demande de l'etudiant,
    changement d'ecran probable) -- ne jamais reutiliser un action_id
    obtenu il y a plusieurs tours sans revalider qu'il est toujours
    dans cette liste.

    Renvoie une liste vide (pas une erreur) si l'application n'est
    ouverte nulle part pour ce compte, ou si l'ecran actuel ne contient
    aucun element cliquable detecte par le scan.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    actions = _obtenir_actions_disponibles(user_id)
    return json.dumps(actions, ensure_ascii=False)


@mcp_generation.tool()
async def executer_action_application(action_id: str, ctx: Context) -> str:
    """
    Declenche un clic dans l'application Clovis a la place de
    l'etudiant, sur l'element `action_id`. `action_id` DOIT etre un
    identifiant renvoye par lister_actions_disponibles (mecanisme de
    poussee d'etat, chantier D) -- ne jamais deviner ni inventer un
    identifiant : un element qui n'est plus a l'ecran echoue proprement
    plutot que de risquer un effet inattendu.

    Revise le 19/09/2026 (decision Bourama) : plus aucune confirmation
    cote etudiant, l'execution est immediate des l'appel de cet outil.
    A utiliser en consequence uniquement quand l'etudiant a reellement
    demande cette action (ou l'a clairement acceptee dans la
    conversation), jamais de facon spontanee.

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
    return "Action exécutée avec succès."


@mcp_generation.tool()
async def executer_clic_generique(selecteur: str, description: str, ctx: Context) -> str:
    """
    Chantier F, revise le 17/09/2026 (scan generique -- voir
    plan-scan-generique-agent-applicatif.md, etape 4 : decision produit
    a confirmer avec Bourama sur l'utilite de conserver cet outil
    maintenant que lister_actions_disponibles detecte deja
    automatiquement bouton/lien/champ). Filet de securite UNIQUEMENT
    pour un element cliquable qui n'apparait PAS dans
    lister_actions_disponibles (ex. un element sans semantique standard,
    hors des types couverts par le scan). Vérifie TOUJOURS
    lister_actions_disponibles en premier, et n'utilise cet outil que si
    rien dans cette liste ne correspond à ce que l'étudiant a demandé --
    ne jamais l'utiliser en doublon d'un élément déjà détecté par le
    scan.

    `selecteur` est un sélecteur CSS visant un unique élément cliquable
    (bouton, lien...) actuellement affiché. `description` est une
    phrase courte et claire décrivant l'action, affichée à l'étudiant
    dans la bulle de dialogue du canal en direct pendant l'exécution.

    Revise le 19/09/2026 (decision Bourama) : plus aucune confirmation
    cote etudiant, l'execution est immediate des l'appel de cet outil.

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
    return "Action exécutée avec succès."


@mcp_generation.tool()
async def montrer_element_application(action_id: str, ctx: Context) -> str:
    """
    Chantier G : mode guidage / visite guidée. Déplace UNIQUEMENT le
    curseur virtuel vers l'élément `action_id` (identifiant issu de
    lister_actions_disponibles, détecté automatiquement par le scan
    générique), SANS jamais l'exécuter -- pour montrer une nouveauté ou
    un endroit précis de l'application à l'étudiant.
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
