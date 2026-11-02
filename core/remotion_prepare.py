"""Projets Remotion prêts à l'emploi (demande de Bourama, 03/11/2026).

Sur le serveur de montage, l'image est construite avec un projet Remotion déjà
installé (dossier REMOTION_BASE_DIR, par défaut /opt/remotion-base) : paquets
npm et navigateur de rendu compris. Pour un nouveau projet, on copie ce
node_modules au lieu de relancer npm install, qui prend plusieurs minutes.

Si le dossier de base n'existe pas (serveur principal, développement), ou si le
projet demande des paquets que la base n'a pas, la fonction ne fait rien et
l'installation normale (npm install) prend le relais.
"""
import json
import logging
import os
import subprocess
from pathlib import Path

_DELAI_COPIE_S = 300


def _noms_paquets(package_json: Path) -> set[str]:
    donnees = json.loads(package_json.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for cle in ("dependencies", "devDependencies"):
        bloc = donnees.get(cle)
        if isinstance(bloc, dict):
            noms.update(bloc.keys())
    return noms


def preparer_node_modules(projet: Path) -> bool:
    """Copie le node_modules de la base dans le projet. Renvoie True si c'est fait."""
    base = Path(os.environ.get("REMOTION_BASE_DIR", "/opt/remotion-base"))
    source = base / "node_modules"
    if not (base / "package.json").is_file() or not source.is_dir():
        return False
    try:
        if not _noms_paquets(projet / "package.json") <= _noms_paquets(base / "package.json"):
            return False
        resultat = subprocess.run(
            ["cp", "-a", "--reflink=auto", str(source), str(projet / "node_modules")],
            capture_output=True,
            text=True,
            timeout=_DELAI_COPIE_S,
        )
        if resultat.returncode != 0:
            logging.error("Copie du node_modules Remotion échouée : %s", (resultat.stderr or "")[-300:])
            return False
        return True
    except Exception:
        logging.exception("Préparation du projet Remotion impossible, repli sur npm install.")
        return False
