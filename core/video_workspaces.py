"""Espaces de travail isolés pour le montage vidéo Clovis.

Les sources restent dans uploads/ et ne sont jamais utilisées comme sortie.
Les transformations sont écrites dans outputs/ (ou projects/ pour Remotion).
Les identifiants utilisateur/conversation sont hachés avant de devenir des chemins.

Conservation (décision de Bourama, 22/10/2026) : les vidéos importées et les
fichiers produits sont gardés sans limite de durée dans le compte de
l'utilisateur, dans R2. Le disque du serveur n'est qu'un cache, restauré depuis
R2 au besoin : aucun nettoyage automatique n'existe ni ne doit être ajouté.
Seule la suppression du compte les efface (supprimer_videos_utilisateur,
appelée par core/purge_compte.py), et l'export de compte les liste
(lister_videos_utilisateur).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import os
import shutil
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
    # Audios et images importés depuis les fichiers joints du chat (26/10/2026,
    # demande Bourama) : mêmes dossier, mêmes règles de propriété et même
    # stockage durable que les vidéos. La route /video-workspace, elle, ne
    # laisse toujours passer que des vidéos.
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Variantes de type MIME rencontrées sur les fichiers joints -> type canonique ci-dessus.
ALIAS_MIME = {
    "audio/mp3": "audio/mpeg",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/aac": "audio/mp4",
    "audio/x-flac": "audio/flac",
    "audio/opus": "audio/ogg",
    "image/jpg": "image/jpeg",
}

EXTENSIONS_SOURCES = {extension for extension in EXTENSIONS_MIME.values()}


def mime_canonique(mime: str) -> str:
    """'audio/webm;codecs=opus' -> 'audio/webm', 'audio/x-m4a' -> 'audio/mp4'."""
    base = (mime or "").split(";")[0].strip().lower()
    return ALIAS_MIME.get(base, base)


def _segment(value: str) -> str:
    if not value or len(value) > 256:
        raise ValueError("Identifiant utilisateur ou conversation invalide.")
    # Les URLs de fichiers R2 sont servies par le relais backend. Un simple
    # SHA d'un user_id/conversation_id connu rendrait les chemins privés
    # calculables. HMAC avec le secret serveur rend les préfixes non devinables.
    secret = os.environ.get("CLASSINUS_VIDEO_WORKSPACE_SECRET") or os.environ.get("SUPABASE_SECRET")
    if not secret:
        raise RuntimeError("Le secret serveur est requis pour isoler les espaces vidéo.")
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


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
        raise FileNotFoundError("Cette vidéo n'existe pas dans cette conversation.")
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
            "Cette vidéo n'existe pas dans cette conversation."
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
        # Un outil tiers peut utiliser FFmpeg avec -y : si le modèle demande
        # le nom d'une sortie qui existe déjà, crée une nouvelle version au
        # lieu de laisser l'outil écraser le résultat précédent.
        if candidat.exists():
            original = candidat
            version = 2
            while True:
                candidat = original.with_name(f"{original.stem}_v{version}{original.suffix}")
                if not candidat.exists():
                    break
                version += 1
        candidat.parent.mkdir(parents=True, exist_ok=True)
    elif not candidat.exists():
        raise FileNotFoundError(f"Fichier introuvable dans l'espace de travail : {candidat.name}")
    return str(candidat)


# Seuls les résultats et les sources de projet sont synchronisés. Les caches
# installés par npm/Remotion ne sont ni utiles ni adaptés au stockage objet.
_REPERTOIRES_PERSISTANTS = ("outputs", "projects")
_REPERTOIRES_IGNORES = {
    "node_modules", ".git", ".next", ".venv", "venv", "__pycache__",
    ".cache", ".remotion", "dist", "build", "coverage",
}
_MAX_FICHIERS_WORKSPACE = 2000


def _prefix_workspace(user_id: str, conversation_id: str) -> str:
    return (
        f"montages-video/workspaces/{_segment(user_id)}/"
        f"{_segment(conversation_id)}"
    )


def _cle_workspace(user_id: str, conversation_id: str, relative: str) -> str:
    chemin = Path(relative)
    if chemin.is_absolute() or any(part in ("", ".", "..") for part in chemin.parts):
        raise ValueError("Chemin de workspace invalide.")
    if not chemin.parts or chemin.parts[0] not in _REPERTOIRES_PERSISTANTS:
        raise ValueError("Seuls outputs/ et projects/ sont persistés.")
    return f"{_prefix_workspace(user_id, conversation_id)}/{chemin.as_posix()}"


def _lire_manifest_workspace(stockage, user_id: str, conversation_id: str) -> dict:
    try:
        donnees = stockage.download(
            f"{_prefix_workspace(user_id, conversation_id)}/manifest.json"
        )
        manifest = json.loads(donnees.decode("utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files", []), list):
            raise ValueError("Manifest workspace invalide.")
        return manifest
    except FileNotFoundError:
        return {"version": 1, "files": []}
    except Exception as exc:
        # Ne jamais remplacer un manifeste valide par une liste vide si R2
        # est temporairement indisponible : cela ferait perdre la référence
        # vers des versions antérieures du montage.
        try:
            from botocore.exceptions import ClientError
            if isinstance(exc, ClientError):
                code = str((exc.response or {}).get("Error", {}).get("Code", ""))
                if code in {"NoSuchKey", "NotFound", "404"}:
                    return {"version": 1, "files": []}
        except ImportError:
            pass
        raise RuntimeError("Impossible de lire le manifeste du workspace vidéo dans R2.") from exc


def restaurer_workspace(user_id: str, conversation_id: str, *, root: Path | None = None) -> dict:
    """Restaure les sorties/projets d'une conversation depuis R2, instance indépendante."""
    root = (root or workspace_dir(user_id, conversation_id)).resolve()
    for repertoire in _REPERTOIRES_PERSISTANTS:
        (root / repertoire).mkdir(parents=True, exist_ok=True)

    from core import stockage_r2

    stockage = stockage_r2.from_("images-publiques")
    manifest = _lire_manifest_workspace(stockage, user_id, conversation_id)
    restaure = 0

    for entree in manifest.get("files", []):
        if not isinstance(entree, dict):
            continue
        relative = entree.get("path")
        digest_attendu = entree.get("sha256")
        try:
            cle = _cle_workspace(user_id, conversation_id, relative)
            destination = (root / relative).resolve()
            if root not in destination.parents or not isinstance(digest_attendu, str):
                continue
            if destination.is_file() and _sha256_fichier(destination) == digest_attendu:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporaire = destination.with_suffix(destination.suffix + ".part")
            try:
                stockage.download_to_file(cle, temporaire)
            except AttributeError:
                contenu = stockage.download(cle)
                temporaire.write_bytes(contenu)
            temporaire.replace(destination)
            if _sha256_fichier(destination) == digest_attendu:
                restaure += 1
            else:
                destination.unlink(missing_ok=True)
                raise ValueError(f"Empreinte invalide pour le fichier restauré : {Path(relative).name}")
        except FileNotFoundError:
            continue
    return {"restaure": restaure, "fichiers_manifest": len(manifest.get("files", []))}


def _sha256_fichier(chemin: Path) -> str:
    digest = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for morceau in iter(lambda: fichier.read(1024 * 1024), b""):
            digest.update(morceau)
    return digest.hexdigest()


def synchroniser_workspace(user_id: str, conversation_id: str, *, root: Path | None = None) -> dict:
    """Persiste par delta les résultats et sources Remotion, en excluant les caches lourds."""
    root = (root or workspace_dir(user_id, conversation_id)).resolve()
    from core import stockage_r2

    stockage = stockage_r2.from_("images-publiques")
    manifest_ancien = _lire_manifest_workspace(stockage, user_id, conversation_id)
    anciens = {
        entree.get("path"): entree
        for entree in manifest_ancien.get("files", [])
        if isinstance(entree, dict) and isinstance(entree.get("path"), str)
    }
    nouveaux: list[dict] = []

    for repertoire in _REPERTOIRES_PERSISTANTS:
        base = (root / repertoire).resolve()
        if root not in base.parents or not base.is_dir():
            continue
        for dossier, sous_dossiers, noms_fichiers in os.walk(base, followlinks=False):
            sous_dossiers[:] = [
                nom for nom in sous_dossiers
                if nom not in _REPERTOIRES_IGNORES
                and not (Path(dossier) / nom).is_symlink()
            ]
            for nom in noms_fichiers:
                fichier = (Path(dossier) / nom).resolve()
                if fichier.is_symlink() or not fichier.is_file() or fichier.name.endswith(".part"):
                    continue
                relative = fichier.relative_to(root).as_posix()
                cle = _cle_workspace(user_id, conversation_id, relative)
                taille = fichier.stat().st_size
                digest = _sha256_fichier(fichier)
                entree = {
                    "path": relative,
                    "sha256": digest,
                    "size": taille,
                    "type_mime": mimetypes.guess_type(fichier.name)[0] or "application/octet-stream",
                }
                ancien = anciens.get(relative)
                if ancien and ancien.get("sha256") == digest and ancien.get("size") == taille:
                    nouveaux.append(entree)
                    continue
                with fichier.open("rb") as contenu:
                    stockage.upload(cle, contenu, {"content-type": entree["type_mime"]})
                nouveaux.append(entree)
                if len(nouveaux) > _MAX_FICHIERS_WORKSPACE:
                    raise ValueError(
                        f"Le workspace dépasse la limite de {_MAX_FICHIERS_WORKSPACE} fichiers persistants."
                    )

    manifeste = {"version": 1, "files": sorted(nouveaux, key=lambda item: item["path"])}
    stockage.upload(
        f"{_prefix_workspace(user_id, conversation_id)}/manifest.json",
        json.dumps(manifeste, ensure_ascii=False).encode("utf-8"),
        {"content-type": "application/json"},
    )
    return {"persistes": len(nouveaux), "nouveaux_ou_modifies": sum(
        1 for entree in nouveaux
        if entree.get("sha256") != anciens.get(entree["path"], {}).get("sha256")
    )}


# --- Compte : export et suppression -------------------------------------

_PREFIXE_ORIGINAUX = "montages-video/originaux"
_PREFIXE_WORKSPACES = "montages-video/workspaces"
_CHAMPS_EXPORT_VIDEO = ("video_id", "nom_fichier", "taille_octets", "type_mime", "duree_secondes")
_LOT_SUPPRESSION_R2 = 1000  # limite d'une requête de suppression groupée


def lister_videos_utilisateur(user_id: str) -> dict:
    """Résumé des vidéos du compte, pour « Exporter mes données ».

    Les vidéos importées sont décrites une par une (nom, taille, type, durée) ;
    les fichiers produits par le montage sont comptés. Les contenus eux-mêmes
    ne sont pas inclus dans le fichier JSON de l'export.
    """
    from core import stockage_r2

    segment = _segment(user_id)
    stockage = stockage_r2.from_("images-publiques")

    importees = []
    for chemin in stockage.lister(f"{_PREFIXE_ORIGINAUX}/{segment}/"):
        if not chemin.endswith(".json"):
            continue
        try:
            donnees = json.loads(stockage.download(chemin).decode("utf-8"))
        except Exception as e:
            logging.error(f"ERREUR export vidéos ({chemin} pour {user_id}) : {e}")
            continue
        if isinstance(donnees, dict):
            importees.append({cle: donnees.get(cle) for cle in _CHAMPS_EXPORT_VIDEO})

    produits = [
        chemin
        for chemin in stockage.lister(f"{_PREFIXE_WORKSPACES}/{segment}/")
        if not chemin.endswith("/manifest.json")
    ]
    return {"videos_importees": importees, "fichiers_produits": len(produits)}


def supprimer_videos_utilisateur(user_id: str) -> dict:
    """Supprime toutes les vidéos d'un compte : R2 puis cache local.

    Appelée à la suppression du compte. Va jusqu'au bout même si un lot échoue
    (chaque erreur est loguée avec l'utilisateur, pour reprise à la main) et
    renvoie le nombre d'objets supprimés et d'objets en échec.
    """
    from core import stockage_r2

    segment = _segment(user_id)
    stockage = stockage_r2.from_("images-publiques")
    supprimes = 0
    en_echec = 0

    for prefixe in (_PREFIXE_ORIGINAUX, _PREFIXE_WORKSPACES):
        try:
            chemins = stockage.lister(f"{prefixe}/{segment}/")
        except Exception as e:
            logging.error(f"ERREUR purge vidéos (liste {prefixe} pour {user_id}) : {e}")
            en_echec += 1
            continue
        for debut in range(0, len(chemins), _LOT_SUPPRESSION_R2):
            lot = chemins[debut:debut + _LOT_SUPPRESSION_R2]
            try:
                stockage.remove(lot)
                supprimes += len(lot)
            except Exception as e:
                logging.error(f"ERREUR purge vidéos ({len(lot)} objets {prefixe} pour {user_id}) : {e}")
                en_echec += len(lot)

    racine_utilisateur = (ROOT / segment).resolve()
    if ROOT in racine_utilisateur.parents:
        shutil.rmtree(racine_utilisateur, ignore_errors=True)

    return {"supprimes": supprimes, "en_echec": en_echec}
