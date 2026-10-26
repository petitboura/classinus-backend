"""
Export de skills en zip (26/10/2026, demande de Bourama : les
utilisateurs repartent avec leurs skills, ou les échangent avec Claude).
Disposition identique à celle d'un skill de Claude : un dossier par
skill, nommé d'après le skill, avec son SKILL.md et ses autres fichiers.
Les fichiers non texte sont listés dans la réponse mais pas inclus
(Classinus ne les lit pas), jamais ignorés en silence.
"""
import io
import re
import unicodedata
import uuid
import zipfile
from types import SimpleNamespace

from api import skills as _api
from core import stockage_r2
from core.generation_archives import BUCKET


def _dossier(nom: str, deja: set[str]) -> str:
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-") or "skill"
    choisi, i = base, 2
    while choisi in deja:
        choisi, i = f"{base}-{i}", i + 1
    deja.add(choisi)
    return choisi


def exporter_skills_en_zip(user_id: str, skill_id: str = "") -> tuple[str, list[str]]:
    """Renvoie (url du zip, notes). `skill_id` vide : tous les skills de l'utilisateur."""
    if (skill_id or "").strip():
        lignes = [_api._owned(skill_id.strip(), user_id)]
    else:
        lignes = _api.lister(SimpleNamespace(id=user_id))
        if not lignes:
            raise ValueError("aucun_skill")
    tampon, notes, dossiers = io.BytesIO(), [], set()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for ligne in lignes:
            dossier = _dossier(ligne["nom"], dossiers)
            for item in _api._files(ligne["id"], True):
                if item.get("binaire"):
                    notes.append(f"{ligne['nom']} : {item['chemin']} (pas du texte, non inclus)")
                    continue
                archive.writestr(f"{dossier}/{item['chemin']}", item["contenu"])
    chemin = f"bundles/{uuid.uuid4()}-skills.zip"
    stockage_r2.from_(BUCKET).upload(chemin, tampon.getvalue(), {"content-type": "application/zip"})
    return stockage_r2.from_(BUCKET).get_public_url(chemin), notes
