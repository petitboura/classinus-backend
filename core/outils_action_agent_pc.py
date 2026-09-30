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


# Lot V (28/09/2026, decision Bourama : aucune image envoyee au modele,
# seulement du texte, et seulement la fenetre au premier plan). Toutes les
# limites de lecture sont gardees ICI, a un seul endroit : elles sont
# envoyees avec chaque demande, le processus Electron n'a pas de valeurs a
# lui (voir electron/src/lectureFenetreWindows.mts). Valeurs de depart, pas
# des limites produit tranchees avec Bourama : a valider.
NB_MAX_ELEMENTS_LECTURE_ECRAN = 120
NB_MAX_FENETRES_LECTURE_ECRAN = 15
LONGUEUR_MAX_NOM_LECTURE_ECRAN = 80
LONGUEUR_MAX_VALEUR_LECTURE_ECRAN = 400
PROFONDEUR_MAX_LECTURE_ECRAN = 25
DELAI_MAX_LECTURE_ECRAN_MS = 6000
# Taille maximale du texte final rendu au modele (environ 1500 tokens).
LONGUEUR_MAX_TEXTE_LECTURE_ECRAN = 6000


def _formater_element_lu(element: dict) -> str:
    """Une ligne de texte pour un element lu (voir LectureFenetre cote Electron)."""
    genre = element.get("type") or "élément"
    nom = element.get("nom") or ""
    details = []
    if element.get("valeur_masquee"):
        details.append("valeur masquée")
    elif element.get("valeur"):
        details.append(f"valeur : « {element['valeur']} »")
    etats = element.get("etats")
    if isinstance(etats, list):
        details.extend(e for e in etats if isinstance(e, str) and e)
    suite = f" ({', '.join(details)})" if details else ""
    nom_txt = f" « {nom} »" if nom else ""
    return f"[{genre}{nom_txt}{suite}, clic possible en ({element.get('x')}, {element.get('y')})]"


def _formater_lecture_ecran(resultat: dict) -> str:
    """
    Transforme le resultat structure du processus Electron en texte court
    pour le modele. Fonction pure (testable sans connexion), plafonnee par
    LONGUEUR_MAX_TEXTE_LECTURE_ECRAN.
    """
    titre = resultat.get("titre_fenetre_active")
    application = resultat.get("application")
    fenetres = [f for f in (resultat.get("fenetres_ouvertes") or []) if isinstance(f, str) and f]

    lignes = []
    if titre:
        appli_txt = f" ({application})" if application else ""
        lignes.append(f"Fenêtre au premier plan : « {titre} »{appli_txt}")
    else:
        lignes.append("Aucune fenêtre au premier plan n'a été trouvée.")
    if fenetres:
        lignes.append("Autres fenêtres ouvertes : " + ", ".join(f"« {f} »" for f in fenetres))

    if resultat.get("fenetre_classinus"):
        lignes.append(
            "La fenêtre au premier plan est Classinus lui-même : pour lire ce qui y est affiché, "
            "utilise lire_page."
        )
        return "\n".join(lignes)

    elements = [e for e in (resultat.get("elements") or []) if isinstance(e, dict)]
    if resultat.get("mode") != "uia" or not elements:
        lignes.append(
            "Le contenu de cette fenêtre n'a pas pu être lu (l'application ne le rend pas lisible). "
            "Tu peux seulement t'appuyer sur son titre. Ne devine jamais ce qu'elle contient ni "
            "l'endroit où cliquer."
        )
        return "\n".join(lignes)

    lignes.append("Contenu visible (les coordonnées sont en pixels d'écran, utilisables avec cliquer_ecran) :")
    total = sum(len(l) + 1 for l in lignes)
    coupe = bool(resultat.get("coupe"))
    for element in elements:
        ligne = _formater_element_lu(element)
        if total + len(ligne) + 1 > LONGUEUR_MAX_TEXTE_LECTURE_ECRAN:
            coupe = True
            break
        lignes.append(ligne)
        total += len(ligne) + 1
    if coupe:
        lignes.append(
            "[Lecture coupée : la limite de taille est atteinte, la suite de ce qui est affiché "
            "n'est pas incluse. Ne devine pas la suite.]"
        )
    return "\n".join(lignes)


@mcp_generation.tool()
async def lire_ecran(ctx: Context) -> str:
    """
    Lot S (27/09/2026), reecrit au Lot V (28/09/2026, decision Bourama :
    aucune image, seulement du texte). Lit ce qu'il y a dans la fenetre
    au premier plan du PC de l'etudiant : son titre, les titres des autres
    fenetres ouvertes, et le contenu visible de la fenetre (textes,
    boutons, champs avec leur valeur, cases, onglets...), chacun avec ses
    coordonnees d'ecran pour cliquer_ecran. La valeur d'un champ mot de
    passe n'est jamais lue.

    Appelle cet outil avant cliquer_ecran ou taper_clavier chaque fois que
    tu n'es pas certain de ce qui est affiche ou de l'endroit exact ou
    agir : ne devine jamais des coordonnees. Pas a chaque message : seulement
    quand ce contenu t'est necessaire.

    Si Classinus ou sa barre flottante a le focus, lit la première fenêtre
    externe derrière Classinus, sans la mettre au premier plan. Pour agir
    dessus, le pont restaure son focus avant le clic ou la frappe.

    Ne lit QUE cette fenetre (pas toutes les autres, pas tout
    l'ecran). Certaines applications (jeux, bureau a distance) ne rendent
    presque rien lisible : l'outil le dit, dans ce cas ne devine pas. Pour
    ce qui est affiche dans Classinus lui meme, utilise lire_page.
    """
    user_id, erreur = _user_id_ou_erreur(ctx)
    if erreur:
        return erreur

    resultat = await _demander_action_systeme(
        user_id,
        "lire_ecran",
        {
            "nb_max_elements": NB_MAX_ELEMENTS_LECTURE_ECRAN,
            "nb_max_fenetres": NB_MAX_FENETRES_LECTURE_ECRAN,
            "longueur_max_nom": LONGUEUR_MAX_NOM_LECTURE_ECRAN,
            "longueur_max_valeur": LONGUEUR_MAX_VALEUR_LECTURE_ECRAN,
            "profondeur_max": PROFONDEUR_MAX_LECTURE_ECRAN,
            "delai_max_ms": DELAI_MAX_LECTURE_ECRAN_MS,
        },
    )
    if resultat is None:
        return MESSAGE_ECHEC_SYSTEME
    if not isinstance(resultat, dict):
        return "La lecture de l'écran n'a pas donné de résultat exploitable."
    if resultat.get("erreur"):
        return f"Erreur : {resultat['erreur']}"

    return _formater_lecture_ecran(resultat)
