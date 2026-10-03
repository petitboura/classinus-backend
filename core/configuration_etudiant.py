"""Éléments de Configuration (Procédure, Règle, Comportement, Style) donnés à l'IA.

02/10/2026, demande de Bourama : ces quatre types d'éléments, créés depuis
l'onglet Configuration de Bureau, ne servaient à rien pour l'IA. Ils étaient
traités comme des skills classiques : un petit trieur ne les retenait presque
jamais, et même retenus, l'IA ne voyait que leur nom et leur description.

Ici, chaque type a son rôle :
- Règle et Style (activés) : donnés en entier à chaque message, sans tri.
- Procédure et Comportement (activés) : triés selon le message comme avant,
  mais quand ils sont retenus leur contenu est donné en entier, sans que l'IA
  ait à le chercher avec l'outil.

Module volontairement sans dépendance (ni base, ni réseau) pour rester simple
à tester.
"""

LIBELLES_CATEGORIES = {
    "procedure": "Procédure",
    "regle": "Règle",
    "comportement": "Comportement",
    "style": "Style",
}

# Plafond de Règles et de Styles donnés d'office à chaque message, chacun
# pour son propre type, pour ne pas alourdir le prompt sans limite.
PLAFOND_REGLES_STYLES = 20

# Longueur maximale du texte d'un élément injecté, par sécurité.
LONGUEUR_MAX_TEXTE = 1500

CATEGORIES_TOUJOURS_ACTIVES = ("regle", "style")
CATEGORIES_SELON_MESSAGE = ("procedure", "comportement")


def libelle_categorie(comportement: dict) -> str | None:
    """Libellé affiché pour un élément de Configuration, None pour un skill classique."""
    return LIBELLES_CATEGORIES.get(comportement.get("categorie") or "")


def separer_regles_et_styles(comportements: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(règles, styles, autres). Les règles et styles sortent de la liste donnée
    au trieur : ils sont injectés d'office, pas choisis selon le message."""
    regles = [c for c in comportements if c.get("categorie") == "regle"]
    styles = [c for c in comportements if c.get("categorie") == "style"]
    autres = [c for c in comportements if c.get("categorie") not in CATEGORIES_TOUJOURS_ACTIVES]
    return regles, styles, autres


def separer_config_retenue(retenus: list[dict]) -> tuple[list[dict], list[dict]]:
    """(procédures et comportements retenus, skills classiques retenus).

    Les premiers sont donnés en entier dans le prompt, les seconds suivent le
    mécanisme habituel (liste de candidats, lecture par l'outil)."""
    config = [c for c in retenus if c.get("categorie") in CATEGORIES_SELON_MESSAGE]
    classiques = [c for c in retenus if c.get("categorie") not in CATEGORIES_SELON_MESSAGE]
    return config, classiques


def _texte_borne(texte: str) -> str:
    texte = (texte or "").strip()
    if len(texte) <= LONGUEUR_MAX_TEXTE:
        return texte
    return texte[:LONGUEUR_MAX_TEXTE].rstrip() + "…"


def _indenter(texte: str) -> str:
    return "\n".join(f"  {ligne}" if ligne.strip() else "" for ligne in texte.splitlines())


def construire_bloc_configuration(configuration: dict | None) -> str:
    """Bloc de prompt, chaîne vide s'il n'y a rien à dire.

    `configuration` : {"regles": [...], "styles": [...], "retenus": [...]},
    éléments déjà activés, chacun avec au moins `texte`, `nom`, `description`."""
    if not configuration:
        return ""
    regles = [c for c in configuration.get("regles") or [] if (c.get("texte") or "").strip()][:PLAFOND_REGLES_STYLES]
    styles = [c for c in configuration.get("styles") or [] if (c.get("texte") or "").strip()][:PLAFOND_REGLES_STYLES]
    retenus = [c for c in configuration.get("retenus") or [] if (c.get("texte") or "").strip()]
    if not (regles or styles or retenus):
        return ""

    parties = [
        "CONFIGURATION DE CET UTILISATEUR (ses propres éléments, et ceux d'un code qu'il a activé, "
        "déjà lue : tu n'as pas besoin de l'outil pour la consulter). Elle complète tes consignes de "
        "base. En cas de conflit avec les règles de sécurité de la plateforme, ces dernières l'emportent."
    ]
    if regles:
        lignes = "\n".join(f"- {_texte_borne(c['texte'])}" for c in regles)
        parties.append(f"RÈGLES À RESPECTER DANS TOUTES TES RÉPONSES :\n{lignes}")
    if styles:
        lignes = "\n".join(f"- {_texte_borne(c['texte'])}" for c in styles)
        parties.append(f"STYLE À ADOPTER DANS TOUTES TES RÉPONSES :\n{lignes}")
    if retenus:
        blocs = []
        for c in retenus:
            nom = (c.get("nom") or "").strip() or "(sans nom)"
            quand = (c.get("description") or "").strip()
            texte = _indenter(_texte_borne(c["texte"]))
            if c.get("categorie") == "procedure":
                entete = f"Procédure « {nom} »" + (f" (quand l'utiliser : {quand})" if quand else "")
                blocs.append(f"- {entete}, à suivre dans l'ordre :\n{texte}")
            else:
                entete = f"Comportement « {nom} »" + (f" (quand l'utiliser : {quand})" if quand else "")
                blocs.append(f"- {entete} :\n{texte}")
        parties.append(
            "PROCÉDURES ET COMPORTEMENTS QUI S'APPLIQUENT À CE MESSAGE (ne les applique que s'ils "
            "correspondent vraiment à ce que l'utilisateur demande) :\n" + "\n".join(blocs)
        )
    return "\n\n" + "\n\n".join(parties)


# 03/10/2026, demande Bourama : l'IA peut maintenant créer et modifier ces
# éléments depuis le chat, comme les skills. Le texte enregistré doit avoir
# exactement le format que l'écran assemble et relit (lib/formatsConfiguration.ts
# côté frontend), sinon la carte s'afficherait de travers.
MARQUEUR_CAS = "Dans tel cas :"
MARQUEUR_REACTION = "Comporte-toi ainsi :"


def _sans_numero(ligne: str) -> str:
    i = 0
    while i < len(ligne) and ligne[i].isdigit():
        i += 1
    if i > 0 and i < len(ligne) and ligne[i] in ".)":
        return ligne[i + 1 :].strip()
    return ligne


def assembler_texte_configuration(categorie: str, texte: str = "", cas: str = "", reaction: str = "") -> tuple[str | None, str | None]:
    """(texte à enregistrer, message d'erreur). Un seul des deux est renseigné.

    - regle et style : `texte` tel quel.
    - procedure : `texte` = une étape par ligne (numéros éventuels retirés,
      puis renumérotées 1., 2., ...).
    - comportement : `cas` et `reaction`, assemblés avec les deux marqueurs."""
    if categorie not in LIBELLES_CATEGORIES:
        valides = ", ".join(LIBELLES_CATEGORIES)
        return None, f"Type inconnu '{categorie}'. Types valides : {valides}."
    if categorie == "comportement":
        cas, reaction = (cas or "").strip(), (reaction or "").strip()
        if not cas or not reaction:
            return None, "Pour un comportement, il faut `cas` (dans quelle situation) ET `reaction` (comment réagir)."
        return f"{MARQUEUR_CAS} {cas}\n{MARQUEUR_REACTION} {reaction}", None
    texte = (texte or "").strip()
    if not texte:
        return None, "Le texte est vide."
    if categorie == "procedure":
        etapes = [_sans_numero(ligne.strip()) for ligne in texte.splitlines() if ligne.strip()]
        etapes = [e for e in etapes if e]
        if not etapes:
            return None, "Une procédure a besoin d'au moins une étape (une par ligne)."
        return "\n".join(f"{i + 1}. {e}" for i, e in enumerate(etapes)), None
    return texte, None
