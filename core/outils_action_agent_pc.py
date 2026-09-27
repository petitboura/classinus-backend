"""
Chantier "canal en direct sort de l'appli" (voir plan-canal-en-direct-pc.md
a la racine de clovis-frontend), Lot S, ajoute le 27/09/2026.

Meme regle que core/outils_action_agent.py : outils exposes UNIQUEMENT
cote chat eleve (@mcp_generation.tool()), jamais cote serveur MCP public.

Difference avec core/outils_action_agent.py : ces outils-ci n'agissent
plus dans le DOM de la page Classinus (executer_action_application etc.),
mais directement sur le systeme du PC de l'etudiant (clic a des
coordonnees d'ecran, clavier, ouverture d'application, lecture d'ecran),
via la connexion Electron dediee ouverte cote clovis-frontend (voir
capacitor-electron/... et canal-systeme-electron, package
capacitor-canal-systeme-electron). Ces outils ne sont donc disponibles
QUE si l'etudiant utilise l'appli Electron -- si aucune connexion
systeme n'est ouverte, demander_action_systeme renvoie simplement None
(memes _diffuser_et_attendre/_connexions que le reste du canal, rien de
special a gerer ici).

Pas d'appel a _photographier_ecran/_observer_changement_ecran ici (ces
deux helpers suivent l'etat DOM de la page Classinus, sans rapport avec
une fenetre externe comme le Bloc-notes) : c'est lire_ecran, plus bas,
qui joue ce role pour les actions systeme.
"""

from core.canal_agent_applicatif import demander_action_systeme as _demander_action_systeme
from core.outils_generation_commun import mcp_generation, Context


def _user_id_ou_erreur(ctx: Context) -> tuple[str | None, str | None]:
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return None, "Erreur : impossible d'identifier l'utilisateur."
    return user_id, None


MESSAGE_ECHEC_SYSTEME = (
    "Cette action n'a pas pu être exécutée pour le moment. Cela peut vouloir dire que "
    "l'étudiant n'utilise pas l'application PC (elle seule permet d'agir sur le système). "
    "Ne mentionne jamais de détail technique : dis simplement que ça n'a pas abouti pour "
    "le moment, et si le contexte s'y prête, propose de vérifier que l'application PC est "
    "bien ouverte."
)


@mcp_generation.tool()
async def cliquer_ecran(x: int, y: int, ctx: Context) -> str:
    """
    Lot S (27/09/2026). Clique a des coordonnees precises de l'ECRAN
    ENTIER du PC de l'etudiant (pas dans la page Classinus : pour ca,
    utilise plutot executer_action_application ou executer_clic_generique,
    core/outils_action_agent.py). x et y sont des pixels depuis le coin
    superieur gauche de l'ecran principal.

    N'utilise cet outil que pour agir en dehors de Classinus (une autre
    fenetre, un autre site, le bureau). Avant de cliquer a un endroit
    precis, appelle lire_ecran pour savoir ou se trouve reellement ce
    que tu cherches : ne devine jamais des coordonnees.

    Aucune confirmation etudiant pour ce lot (meme regle que le reste du
    canal en direct depuis le 19/09/2026).
    """
    user_id, erreur = _user_id_ou_erreur(ctx)
    if erreur:
        return erreur

    resultat = await _demander_action_systeme(user_id, "cliquer_ecran", {"x": x, "y": y})
    if resultat is None:
        return MESSAGE_ECHEC_SYSTEME
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return f"Clic effectué à l'écran, position ({x}, {y})."


@mcp_generation.tool()
async def taper_clavier(texte: str, ctx: Context) -> str:
    """
    Lot S (27/09/2026). Tape `texte` au clavier, a l'endroit ou se
    trouve le curseur de saisie ACTUEL sur le PC de l'etudiant (la
    fenetre/le champ deja au premier plan) -- pas dans un champ de la
    page Classinus (pour ca, utilise plutot remplir_champ_application,
    core/outils_action_agent.py).

    Si un champ precis doit d'abord recevoir le focus, clique dessus
    avec cliquer_ecran avant d'appeler cet outil.

    Aucune confirmation etudiant pour ce lot (meme regle que le reste du
    canal en direct depuis le 19/09/2026).
    """
    user_id, erreur = _user_id_ou_erreur(ctx)
    if erreur:
        return erreur
    if not texte:
        return "Erreur : paramètre 'texte' manquant."

    resultat = await _demander_action_systeme(user_id, "taper_clavier", {"texte": texte})
    if resultat is None:
        return MESSAGE_ECHEC_SYSTEME
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return "Texte tapé au clavier avec succès."


@mcp_generation.tool()
async def ouvrir_application(nom: str, ctx: Context) -> str:
    """
    Lot S (27/09/2026). Lance une application installée sur le PC de
    l'étudiant (par exemple "notepad", "calc", ou le nom d'un
    exécutable). Ne fonctionne que pour des applications déjà
    installées : n'invente jamais un nom au hasard, demande à
    l'étudiant si tu n'es pas sûr du nom exact.

    Aucune confirmation etudiant pour ce lot (meme regle que le reste du
    canal en direct depuis le 19/09/2026).
    """
    user_id, erreur = _user_id_ou_erreur(ctx)
    if erreur:
        return erreur
    if not nom:
        return "Erreur : paramètre 'nom' manquant."

    resultat = await _demander_action_systeme(user_id, "ouvrir_application", {"nom": nom})
    if resultat is None:
        return MESSAGE_ECHEC_SYSTEME
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"
    return f"Application « {nom} » lancée."


@mcp_generation.tool()
async def lire_ecran(ctx: Context) -> str:
    """
    Lot S (27/09/2026). Prend une capture de l'écran entier du PC de
    l'étudiant et renvoie ce qui a pu en être extrait (pour l'instant :
    le titre de la fenêtre au premier plan, quand disponible -- la
    lecture fine du contenu affiché n'est pas encore faite, voir
    plan-canal-en-direct-pc.md, Lot S : "à trancher selon la difficulté
    réelle").

    Appelle cet outil avant cliquer_ecran/taper_clavier chaque fois que
    tu n'es pas certain de ce qui est affiché ou de l'endroit exact où
    agir : ne devine jamais.
    """
    user_id, erreur = _user_id_ou_erreur(ctx)
    if erreur:
        return erreur

    resultat = await _demander_action_systeme(user_id, "lire_ecran", {})
    if resultat is None:
        return MESSAGE_ECHEC_SYSTEME
    if isinstance(resultat, dict) and resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"

    titre = resultat.get("titre_fenetre_active") if isinstance(resultat, dict) else None
    if titre:
        return f"Capture d'écran prise. Fenêtre au premier plan : « {titre} »."
    return "Capture d'écran prise, mais aucune information supplémentaire n'a pu être extraite."
