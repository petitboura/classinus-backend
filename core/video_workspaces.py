"""Espaces de travail temporaires et isolés pour le montage vidéo Clovis.

Les sources restent dans uploads/ et ne sont jamais utilisées comme sortie.
Les transformations sont écrites dans outputs/ (ou projects/ pour Remotion).
Les identifiants utilisateur/conversation sont hachés avant de devenir des chemins.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path

ROOT = Path(os.environ.get(
    "CLASSINUS_VIDEO_WORKSPACE_ROOT",
    str(Path(tempfile.gettempdir()) / "classinus-video-workspaces"),
)).resolve()

EXTENSIONS_MIME = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}


def _segment(value: str) -> str:
    if not value or len(value) > 256:
        raise ValueError("Identifiant utilisateur ou conversation invalide.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def workspace_dir(user_id: str, conversation_id: str, *, create: bool = True) -> Path:
    """Retourne le dossier propre à un utilisateur et une conversation."""
    if not user_id or not conversation_id:
        raise ValueError("Un utilisateur connecté et une conversation sont requis.")
    root = (ROOT / _segment(user_id) / _segment(conversation_id)).resolve()
    if ROOT not in root.parents:
        raise ValueError("Espace de travail invalide.")
    if create:
        for name in ("uploads", "outputs", "projects"):
            (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _cle_stockage(user_id: str, conversation_id: str, video_id: str, extension: str) -> str:
    """Chemin interne de stockage R2. La source originale n'est jamais publiée par URL."""
    identifiant = uuid.UUID(hex=video_id).hex
    return (
        f"montages-video/originaux/{_segment(user_id)}/"
        f"{_segment(conversation_id)}/{identifiant}{extension}"
    )


def enregistrer_video(
    user_id: str,
    conversation_id: str,
    nom: str,
    mime: str,
    contenu: bytes,
    duree_secondes: float | None = None,
) -> dict:
    """Stocke une source originale durablement dans R2 et en cache temporaire local."""
    extension = EXTENSIONS_MIME.get(mime)
    if not extension:
        raise ValueError("Format vidéo non pris en charge.")
    if not contenu:
        raise ValueError("Fichier vidéo vide.")

    root = workspace_dir(user_id, conversation_id)
    video_id = uuid.uuid4().hex
    metadonnees = {
        "video_id": video_id,
        "nom_fichier": Path(nom or f"video{extension}").name,
        "taille_octets": len(contenu),
        "type_mime": mime,
        "duree_secondes": round(float(duree_secondes), 3) if duree_secondes is not None else None,
    }
    cle_source = _cle_stockage(user_id, conversation_id, video_id, extension)
    cle_meta = _cle_stockage(user_id, conversation_id, video_id, ".json")

    # L'upload ne réussit que si la source et ses métadonnées sont durables.
    # Cela évite que la sélection disparaisse si Railway réattribue la
    # requête SSE à une autre instance ou redémarre après l'upload.
    from core import stockage_r2

    stockage = stockage_r2.from_("images-publiques")
    try:
        stockage.upload(cle_source, contenu, {"content-type": mime})
        stockage.upload(
            cle_meta,
            json.dumps(metadonnees, ensure_ascii=False).encode("utf-8"),
            {"content-type": "application/json"},
        )
    except Exception as exc:
        try:
            stockage.remove([cle_source, cle_meta])
        except Exception:
            pass
        raise RuntimeError("Le stockage sécurisé de la vidéo est indisponible. Réessaie dans un instant.") from exc

    # Cache temporaire optimisé : en cas d'échec local, la source reste
    # restaurable depuis R2 par video_id et les identifiants validés.
    destination = root / "uploads" / f"{video_id}{extension}"
    temporaire = destination.with_suffix(destination.suffix + ".part")
    try:
        temporaire.write_bytes(contenu)
        temporaire.replace(destination)
        (root / "uploads" / f"{video_id}.json").write_text(
            json.dumps(metadonnees, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass

    return metadonnees


def lire_metadonnees_video(user_id: str, conversation_id: str, video_id: str) -> dict:
    """Lit les métadonnées de R2, avec cache local uniquement en mode dégradé."""
    try:
        identifiant = uuid.UUID(hex=video_id).hex
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Identifiant de vidéo invalide.") from None

    root = workspace_dir(user_id, conversation_id, create=False)
    meta_path = (root / "uploads" / f"{identifiant}.json").resolve()
    if root not in meta_path.parents:
        raise ValueError("Chemin de métadonnées invalide.")

    data = None
    try:
        from core import stockage_r2

        contenu = stockage_r2.from_("images-publiques").download(
            _cle_stockage(user_id, conversation_id, identifiant, ".json")
        )
        data = json.loads(contenu.decode("utf-8"))
    except Exception:
        # Un cache local est utile en développement et pendant une panne
        # passagère de stockage, mais une source absente ne sera pas autorisée.
        if meta_path.is_file():
            data = json.loads(meta_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict) or data.get("video_id") != identifiant:
        raise FileNotFoundError("Cette vidéo n'existe pas dans cette conversation ou a expiré.")
    if data.get("type_mime") not in EXTENSIONS_MIME:
        raise ValueError("Type MIME des métadonnées vidéo invalide.")
    return data


def chemin_video(user_id: str, conversation_id: str, video_id: str) -> Path:
    """Résout ou restaure la source originale autorisée pour cette conversation."""
    try:
        identifiant = uuid.UUID(hex=video_id).hex
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Identifiant de vidéo invalide.") from None

    root = workspace_dir(user_id, conversation_id, create=False)
    for extension in EXTENSIONS_MIME.values():
        chemin = (root / "uploads" / f"{identifiant}{extension}").resolve()
        if root in chemin.parents and chemin.is_file():
            return chemin

    metadonnees = lire_metadonnees_video(user_id, conversation_id, identifiant)
    extension = EXTENSIONS_MIME[metadonnees["type_mime"]]
    cle_source = _cle_stockage(user_id, conversation_id, identifiant, extension)
    chemin = (root / "uploads" / f"{identifiant}{extension}").resolve()
    if root not in chemin.parents:
        raise ValueError("Chemin de source vidéo invalide.")
    try:
        from core import stockage_r2

        contenu = stockage_r2.from_("images-publiques").download(cle_source)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire = chemin.with_suffix(chemin.suffix + ".part")
        temporaire.write_bytes(contenu)
        temporaire.replace(chemin)
        return chemin
    except Exception as exc:
        raise FileNotFoundError(
            "Cette vidéo n'existe pas dans cette conversation ou a expiré."
        ) from exc


def chemin_interne(root: Path, valeur: str, *, sortie: bool = False, projet: bool = False) -> str:
    """Valide et normalise un chemin fourni à un outil mcp-video."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError("Chemin de fichier vide ou invalide.")
    if valeur.startswith(("http://", "https://", "file://")):
        raise ValueError("Les outils vidéo ne peuvent utiliser que des fichiers de l'espace de travail.")
    candidat = Path(valeur)
    if not candidat.is_absolute():
        candidat = root / candidat
    candidat = candidat.resolve()
    if root.resolve() not in candidat.parents:
        raise ValueError("Chemin refusé : hors de l'espace de travail de cette conversation.")
    if sortie:
        bases = [root / "outputs"]
        if projet:
            bases.append(root / "projects")
        if not any(base.resolve() == candidat or base.resolve() in candidat.parents for base in bases):
            raise ValueError("Les fichiers produits doivent rester dans outputs/ ou projects/.")
        candidat.parent.mkdir(parents=True, exist_ok=True)
    elif not candidat.exists():
        raise FileNotFoundError(f"Fichier introuvable dans l'espace de travail : {candidat.name}")
    return str(candidat)
