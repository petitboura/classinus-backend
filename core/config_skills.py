"""Réglages des skills autonomes, partagés par l'API, la purge de compte,
l'export des données et le script de migration. Chaque valeur peut être
changée par une variable d'environnement, sans toucher au code."""
import os


def _entier_env(cle: str, defaut: int) -> int:
    try:
        valeur = int(os.environ.get(cle, defaut))
        return valeur if valeur > 0 else defaut
    except (TypeError, ValueError):
        return defaut


BUCKET = os.environ.get("SKILLS_BUCKET") or "skills"
TAILLE_FICHIER_MAX = _entier_env("SKILLS_TAILLE_FICHIER_MAX", 5 * 1024 * 1024)
TAILLE_TOTALE_MAX = _entier_env("SKILLS_TAILLE_TOTALE_MAX", 20 * 1024 * 1024)
NB_FICHIERS_MAX = _entier_env("SKILLS_NB_FICHIERS_MAX", 200)
NB_SKILLS_MAX = _entier_env("SKILLS_NB_PAR_COMPTE_MAX", 200)
TELECHARGEMENTS_PARALLELES = _entier_env("SKILLS_TELECHARGEMENTS_PARALLELES", 8)

# Branchement de l'IA aux skills (lot 1). Réglages modifiables sans toucher au code.
# Nombre maximal de skills annoncés dans le prompt à chaque message (le reste reste
# accessible par l'action "lister" de l'outil gerer_skill).
CATALOGUE_NB_MAX = _entier_env("SKILLS_CATALOGUE_NB_MAX", 100)
# Longueur maximale de chaque description dans le prompt (le texte complet reste lisible
# dans le SKILL.md).
CATALOGUE_DESCRIPTION_MAX = _entier_env("SKILLS_CATALOGUE_DESCRIPTION_MAX", 400)
# Nombre maximal de caractères d'un fichier renvoyé à l'IA en une lecture.
LECTURE_CARACTERES_MAX = _entier_env("SKILLS_LECTURE_CARACTERES_MAX", 60000)
