"""
Repérage de PLUSIEURS skills dans un même zip (26/10/2026, demande de
Bourama : les utilisateurs apportent leurs skills de Claude dans
Classinus, parfois dans un seul zip qui contient un ou plusieurs
dossiers de skill, voire des zips de skill à l'intérieur).

Ne duplique aucune règle de validation : chaque skill trouvé est
reconstruit en mini zip, puis relu par core/skills_zip.lire_zip_skill,
qui applique tous les plafonds (taille, nombre de fichiers, texte
seulement). Ce module ne fait que repérer et découper.

Règles de repérage :
- un skill = un dossier qui contient un SKILL.md (n'importe quelle casse) ;
- un SKILL.md situé dans un dossier déjà retenu appartient à ce skill
  (pas de skill dans un skill) ;
- un zip rangé dans le zip est ouvert aussi, sur 2 niveaux maximum.
"""
import io
import zipfile

from core import config_skills
from core.skills_zip import CHEMIN_PRINCIPAL, SEGMENTS_IGNORES

PROFONDEUR_MAX = 2
TAILLE_DECLAREE_MAX = 5 * config_skills.TAILLE_TOTALE_MAX


def _normaliser(chemin: str) -> str:
    chemin = chemin.replace("\\", "/")
    while chemin.startswith("./"):
        chemin = chemin[2:]
    return chemin


def _noms_utiles(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    utiles = []
    for info in archive.infolist():
        if info.is_dir() or info.flag_bits & 0x1:
            continue
        if any(seg in SEGMENTS_IGNORES for seg in _normaliser(info.filename).split("/")):
            continue
        utiles.append(info)
    return utiles


def _nom_depuis_dossier(dossier: str, nom_zip: str) -> str:
    base = dossier.rstrip("/").rsplit("/", 1)[-1] if dossier else ""
    if base:
        return base
    return nom_zip[:-4] if nom_zip.lower().endswith(".zip") else nom_zip


def trouver_skills(contenu: bytes, nom_zip: str, profondeur: int = 0) -> list[dict]:
    """
    Renvoie une liste de {"nom_par_defaut", "contenu_zip", "origine"}, un élément
    par skill trouvé. Liste vide si aucun SKILL.md. Lève zipfile.BadZipFile si
    le zip de premier niveau est illisible (les zips rangés illisibles sont ignorés).
    """
    archive = zipfile.ZipFile(io.BytesIO(contenu))
    infos = _noms_utiles(archive)
    if sum(i.file_size for i in infos) > TAILLE_DECLAREE_MAX:
        return []

    par_nom = {_normaliser(i.filename): i for i in infos}
    dossiers: list[str] = []
    for chemin in sorted(par_nom, key=lambda c: c.count("/")):
        if chemin.rsplit("/", 1)[-1].lower() != CHEMIN_PRINCIPAL.lower():
            continue
        dossier = chemin[: -len(chemin.rsplit("/", 1)[-1])]
        if not any(dossier.startswith(d) for d in dossiers):
            dossiers.append(dossier)

    trouves: list[dict] = []
    for dossier in dossiers:
        sortie = io.BytesIO()
        with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as mini:
            for chemin, info in par_nom.items():
                if chemin.startswith(dossier):
                    mini.writestr(chemin, archive.read(info))
        trouves.append({
            "nom_par_defaut": _nom_depuis_dossier(dossier, nom_zip),
            "contenu_zip": sortie.getvalue(),
            "origine": f"{nom_zip}/{dossier}".rstrip("/"),
        })

    if profondeur < PROFONDEUR_MAX:
        for chemin, info in par_nom.items():
            if not chemin.lower().endswith(".zip"):
                continue
            if any(chemin.startswith(d) for d in dossiers):
                continue
            if info.file_size > config_skills.TAILLE_TOTALE_MAX:
                continue
            try:
                trouves += trouver_skills(archive.read(info), chemin.rsplit("/", 1)[-1], profondeur + 1)
            except zipfile.BadZipFile:
                continue
    return trouves
