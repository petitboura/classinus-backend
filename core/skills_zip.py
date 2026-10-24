"""Lecture d'un zip de skill, sans aucune écriture.

Un zip de skill contient un SKILL.md (à sa racine, ou dans son unique dossier
principal) et ses autres fichiers. Les limites viennent de core/config_skills.py,
comme pour l'éditeur : taille par fichier, taille totale, nombre de fichiers.

Protections : les tailles déclarées sont vérifiées avant toute lecture, puis les
tailles réelles pendant la lecture (une taille déclarée peut mentir). Un zip
imbriqué n'est jamais déplié : il est refusé comme fichier non texte.
"""
import zipfile
import io

from core import config_skills
from core.erreurs import erreur_api

# Entrées créées par les systèmes d'exploitation, jamais un vrai fichier du skill.
SEGMENTS_IGNORES = {"__MACOSX", ".DS_Store", "Thumbs.db"}
CHEMIN_PRINCIPAL = "SKILL.md"


def _erreur_taille() -> Exception:
    return erreur_api(
        413, "SKILL_TROP_VOLUMINEUX",
        total_mo=config_skills.TAILLE_TOTALE_MAX // (1024 * 1024),
        fichier_mo=config_skills.TAILLE_FICHIER_MAX // (1024 * 1024),
    )


def _retirer_dossier_principal(chemins: list[str]) -> str:
    """Renvoie le préfixe à retirer ("" si aucun) pour que SKILL.md soit à la racine."""
    if CHEMIN_PRINCIPAL in chemins:
        return ""
    premiers = {c.split("/", 1)[0] for c in chemins}
    if len(premiers) == 1 and all("/" in c for c in chemins):
        dossier = next(iter(premiers))
        if f"{dossier}/{CHEMIN_PRINCIPAL}" in chemins:
            return dossier + "/"
    raise erreur_api(422, "ZIP_SKILL_SANS_SKILL_MD")


def lire_zip_skill(contenu_zip: bytes) -> list[tuple[str, str]]:
    """Renvoie la liste (chemin, texte) des fichiers du zip, SKILL.md à la racine.

    Les chemins sont seulement normalisés (séparateurs, dossier principal retiré) :
    leur validation complète (chemins interdits, doublons) reste faite par l'API
    des skills, comme pour l'éditeur.
    """
    if len(contenu_zip) > config_skills.TAILLE_TOTALE_MAX:
        raise _erreur_taille()
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu_zip))
    except zipfile.BadZipFile:
        raise erreur_api(422, "ZIP_SKILL_ILLISIBLE")

    membres: list[tuple[str, str]] = []
    declare_total = reel_total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        chemin = info.filename.replace("\\", "/")
        if any(seg in SEGMENTS_IGNORES for seg in chemin.split("/")):
            continue
        if info.flag_bits & 0x1:
            raise erreur_api(422, "ZIP_SKILL_CHIFFRE")
        if len(membres) >= config_skills.NB_FICHIERS_MAX:
            raise erreur_api(413, "ZIP_SKILL_TROP_DE_FICHIERS", maximum=config_skills.NB_FICHIERS_MAX)
        declare_total += info.file_size
        if info.file_size > config_skills.TAILLE_FICHIER_MAX or declare_total > config_skills.TAILLE_TOTALE_MAX:
            raise _erreur_taille()
        try:
            with archive.open(info) as flux:
                brut = flux.read(config_skills.TAILLE_FICHIER_MAX + 1)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, OSError):
            raise erreur_api(422, "ZIP_SKILL_ILLISIBLE")
        reel_total += len(brut)
        if len(brut) > config_skills.TAILLE_FICHIER_MAX or reel_total > config_skills.TAILLE_TOTALE_MAX:
            raise _erreur_taille()
        try:
            texte = brut.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise erreur_api(422, "ZIP_SKILL_FICHIER_NON_TEXTE", fichier=chemin)
        if "\x00" in texte:
            raise erreur_api(422, "ZIP_SKILL_FICHIER_NON_TEXTE", fichier=chemin)
        membres.append((chemin, texte))

    if not membres:
        raise erreur_api(422, "ZIP_SKILL_VIDE")
    prefixe = _retirer_dossier_principal([c for c, _ in membres])
    return [(c[len(prefixe):], t) for c, t in membres]
