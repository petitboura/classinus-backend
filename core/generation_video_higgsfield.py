"""Génération vidéo via l'API Higgsfield, indépendante du flux fal.ai existant."""
import os
import re
import requests

BASE_URL = "https://api.higgsfield.ai"
MODEL_PATH = "bytedance/seedance-2.0/text-to-video"


def _headers():
    key = os.environ.get("HIGGSFIELD_API_KEY")
    if key:
        credential = key
    else:
        key_id = os.environ.get("HIGGSFIELD_API_KEY_ID")
        key_secret = os.environ.get("HIGGSFIELD_API_KEY_SECRET")
        if not key_id or not key_secret:
            return None
        credential = f"{key_id}:{key_secret}"
    return {"Authorization": f"Key {credential}", "Content-Type": "application/json"}


def higgsfield_api_disponible() -> bool:
    return _headers() is not None


def lancer_generation_video_higgsfield(prompt: str) -> dict:
    headers = _headers()
    if not headers:
        raise RuntimeError("Clé API Higgsfield non configurée.")
    response = requests.post(
        f"{BASE_URL}/{MODEL_PATH}",
        headers=headers,
        json={"prompt": prompt},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    request_id = data.get("request_id") or data.get("id")
    if not request_id:
        raise RuntimeError("Higgsfield n'a pas renvoyé de request_id.")
    return {"request_id": request_id, "statut": data.get("status", "queued")}


def statut_generation_video_higgsfield(request_id: str) -> dict:
    # L'identifiant est place dans l'adresse appelee : on refuse tout ce qui n'est pas un identifiant simple.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_id or ""):
        raise RuntimeError("Identifiant de génération Higgsfield invalide.")
    headers = _headers()
    if not headers:
        raise RuntimeError("Clé API Higgsfield non configurée.")
    response = requests.get(
        f"{BASE_URL}/requests/{request_id}/status",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    status = str(data.get("status", "unknown")).lower()
    result = data.get("result") or data.get("output") or data
    video = result.get("video") if isinstance(result, dict) else None
    url = video.get("url") if isinstance(video, dict) else None
    if not url and isinstance(result, dict):
        url = result.get("video_url")
    if status in {"completed", "complete", "succeeded", "success"} and not url:
        detail = requests.get(
            f"{BASE_URL}/requests/{request_id}",
            headers=headers,
            timeout=30,
        )
        detail.raise_for_status()
        data = detail.json()
        result = data.get("result") or data.get("output") or data
        video = result.get("video") if isinstance(result, dict) else None
        url = video.get("url") if isinstance(video, dict) else None
        if not url and isinstance(result, dict):
            url = result.get("video_url")
    return {"statut": status, "url": url}
