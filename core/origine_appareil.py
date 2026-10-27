"""
Origine de l'appareil (20/10/2026, demande de Bourama).

L'application annonce elle-même, avec chaque message, d'où il vient. Le serveur ne la devine
jamais d'après la connexion. Quatre origines possibles :
- telephone_appli : l'appli installée sur téléphone
- telephone_navigateur : le site ouvert dans le navigateur d'un téléphone
- pc_navigateur : le site ouvert dans le navigateur d'un PC
- pc_appli : l'appli installée sur PC

Origine absente ou inconnue (ancienne version de l'appli, autre client comme Thonny) : le
comportement reste exactement celui d'avant, rien n'est filtré et rien n'est ajouté.

Règle des outils d'écran :
- Les outils d'écran du PC n'existent que sur pc_appli.
- Les outils d'écran du téléphone n'existent que sur telephone_appli.
- Les navigateurs (PC et téléphone) n'ont aucun outil d'écran.
"""

ORIGINE_TELEPHONE_APPLI = "telephone_appli"
ORIGINE_TELEPHONE_NAVIGATEUR = "telephone_navigateur"
ORIGINE_PC_NAVIGATEUR = "pc_navigateur"
ORIGINE_PC_APPLI = "pc_appli"

ORIGINES_VALIDES = (
    ORIGINE_TELEPHONE_APPLI,
    ORIGINE_TELEPHONE_NAVIGATEUR,
    ORIGINE_PC_NAVIGATEUR,
    ORIGINE_PC_APPLI,
)

# Outils qui agissent sur l'écran du PC (voir core/outils_action_agent_pc.py).
OUTILS_ECRAN_PC = frozenset({
    "pointer_ecran", "marquer_ecran", "cliquer_ecran", "taper_clavier",
    "appuyer_touches", "ouvrir_application", "lire_ecran",
})

# Outils qui agissent sur l'écran du téléphone (voir core/outils_action_agent_telephone.py).
OUTILS_ECRAN_TELEPHONE = frozenset({"lire_ecran_telephone", "marquer_ecran_telephone"})

_DESCRIPTIONS_ORIGINE = {
    ORIGINE_TELEPHONE_APPLI: "l'application Classinus installée sur son téléphone",
    ORIGINE_TELEPHONE_NAVIGATEUR: "le site Classinus ouvert dans le navigateur de son téléphone",
    ORIGINE_PC_NAVIGATEUR: "le site Classinus ouvert dans le navigateur de son PC",
    ORIGINE_PC_APPLI: "l'application Classinus installée sur son PC",
}


def normaliser_origine(valeur):
    """Renvoie l'origine si elle est connue, sinon None (comportement d'avant)."""
    if isinstance(valeur, str) and valeur in ORIGINES_VALIDES:
        return valeur
    return None


def lecture_ecran_pc_autorisee(origine):
    """
    Vrai si le serveur peut lire l'écran du PC tout seul avant le tour.
    Origine inconnue : comportement d'avant (autorisé). Sinon, seulement sur l'appli PC.
    """
    return origine is None or origine == ORIGINE_PC_APPLI


def outils_a_retirer(origine):
    """Noms des outils d'écran qui n'existent pas sur cette origine. Vide si origine inconnue."""
    if origine is None:
        return frozenset()
    retires = set()
    if origine != ORIGINE_PC_APPLI:
        retires |= OUTILS_ECRAN_PC
    if origine != ORIGINE_TELEPHONE_APPLI:
        retires |= OUTILS_ECRAN_TELEPHONE
    return frozenset(retires)


def filtrer_catalogue_par_origine(outils_pour_llm, table_routage, origine):
    """Retire du catalogue les outils d'écran qui n'existent pas sur l'appareil utilisé."""
    retires = outils_a_retirer(origine)
    if not retires:
        return outils_pour_llm, table_routage
    outils = [o for o in outils_pour_llm if o["function"]["name"] not in retires]
    table = {nom: route for nom, route in table_routage.items() if nom not in retires}
    return outils, table


# Nombres de colonnes annoncés au LLM : ce sont ceux de classinus-frontend/lib/lisibilite.ts
# (colonne des noms de lignes comprise). Les changer ici, c'est les changer là-bas aussi.
MAX_COLONNES_TELEPHONE = 3
MAX_COLONNES_PC = 6
MAX_COLONNES_PC_LARGE = 10

_ORIGINES_TELEPHONE = (ORIGINE_TELEPHONE_APPLI, ORIGINE_TELEPHONE_NAVIGATEUR)


def _consigne_mise_en_forme(origine):
    """Consigne courte de mise en forme selon la taille d'écran de l'appareil."""
    if origine in _ORIGINES_TELEPHONE:
        return (
            f"Écran étroit : tableaux de {MAX_COLONNES_TELEPHONE} colonnes au maximum (colonne des noms "
            "comprise), sinon coupe en plusieurs petits tableaux ou fais une liste. Diagrammes et "
            "cartes mentales : peu de nœuds, libellés courts, pour qu'ils tiennent en entier à l'écran."
        )
    return (
        f"Grand écran : tableaux de {MAX_COLONNES_PC} colonnes au maximum (colonne des noms comprise), "
        f"{MAX_COLONNES_PC_LARGE} seulement si c'est vraiment nécessaire. Diagrammes et cartes mentales "
        "lisibles en entier à l'écran, sans les surcharger."
    )


def bloc_prompt_origine(origine):
    """Consigne ajoutée aux instructions de Classinus à chaque message. Chaîne vide si origine inconnue."""
    if origine is None:
        return ""
    texte = (
        "\n\n## Appareil utilisé pour ce message\n"
        f"L'étudiant t'écrit depuis {_DESCRIPTIONS_ORIGINE[origine]}. "
    )
    if origine == ORIGINE_PC_APPLI:
        texte += (
            "Tu peux lire et agir sur l'écran de son PC avec les outils d'écran du PC. "
            "Tu n'as pas la lecture de l'écran d'un téléphone."
        )
    elif origine == ORIGINE_TELEPHONE_APPLI:
        texte += (
            "Tu peux lire l'écran de son téléphone et y montrer quelque chose avec les outils d'écran "
            "du téléphone, si la vision de l'écran y est activée. Tu n'as pas la lecture de l'écran d'un PC."
        )
    else:
        texte += (
            "Dans un navigateur, tu n'as aucun outil pour lire ou montrer l'écran de l'appareil : "
            "ne prétends jamais voir son écran et n'essaie pas de le lire. Si l'étudiant veut que tu "
            "voies ou montres quelque chose à l'écran, dis-lui simplement que cela demande "
            "l'application Classinus installée."
        )
    return texte + "\n" + _consigne_mise_en_forme(origine) + "\n"
