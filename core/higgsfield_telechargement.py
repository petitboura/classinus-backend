"""Téléchargement d'une image Higgsfield, débloqué après un partage terminé.

Règle : une image générée ne se télécharge qu'une fois que l'appli a signalé un
partage terminé (bouton Partager, ou copie du lien en secours). La vidéo n'est
jamais verrouillée. Le signal vient de l'appli : il sert à pousser le partage,
pas à protéger un secret.
"""
import logging
from datetime import datetime, timezone

import requests

from api.auth import supabase

TABLE = "higgsfield_generations"
_EXTENSIONS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "mp4": "video/mp4"}
TAILLE_MAX_OCTETS = 100 * 1024 * 1024


def est_debloque(ligne: dict) -> bool:
    """Vrai si la génération peut être téléchargée (vidéo, ou image déjà partagée)."""
    if ligne.get("genre") != "image":
        return True
    return bool(ligne.get("partage_termine_a"))


def marquer_partage_termine(user_id: str, request_id: str) -> bool:
    """Enregistre le partage terminé d'une image de l'utilisateur. Renvoie True si la ligne existe
    et est une image terminée (déjà partagée ou non, l'appel est sans risque à répéter)."""
    res = (
        supabase.table(TABLE)
        .select("genre,etat,partage_termine_a")
        .eq("user_id", user_id)
        .eq("request_id", request_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return False
    ligne = res.data[0]
    if ligne["genre"] != "image" or ligne["etat"] != "terminee":
        return False
    if not ligne.get("partage_termine_a"):
        supabase.table(TABLE).update({"partage_termine_a": datetime.now(timezone.utc).isoformat()}).eq(
            "user_id", user_id
        ).eq("request_id", request_id).is_("partage_termine_a", "null").execute()
    return True


def lire_fichier(ligne: dict) -> tuple[bytes, str, str]:
    """Télécharge le résultat chez Higgsfield. Renvoie (contenu, type MIME, nom de fichier)."""
    url = ligne["url"]
    extension = url.split("?")[0].rsplit(".", 1)[-1].lower()
    if extension not in _EXTENSIONS:
        extension = "png" if ligne["genre"] == "image" else "mp4"
    reponse = requests.get(url, timeout=60, stream=True)
    reponse.raise_for_status()
    contenu = b""
    for morceau in reponse.iter_content(chunk_size=1024 * 256):
        contenu += morceau
        if len(contenu) > TAILLE_MAX_OCTETS:
            logging.error(f"Téléchargement Higgsfield {ligne['request_id']} : fichier trop gros")
            raise ValueError("fichier trop gros")
    nom = "".join(c for c in ligne["titre"] if c.isalnum() or c in " _-").strip() or "classinus"
    return contenu, _EXTENSIONS[extension], f"{nom}.{extension}"
