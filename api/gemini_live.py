"""Jetons éphémères pour le canal vocal Gemini Live de Classinus.

Le navigateur se connecte directement à Gemini Live pour éviter de faire
transiter l audio temps réel par Classinus. La clé GOOGLE_API_KEY reste
uniquement côté backend.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from api.auth import get_secret, utilisateur_courant
from core.erreurs import erreur_api
from google import genai

router = APIRouter(prefix="/api/gemini-live", tags=["gemini-live"])
MODEL_GEMINI_LIVE = "gemini-3.8-live"

@router.post("/token")
def creer_token_gemini_live(utilisateur=Depends(utilisateur_courant)):
    """Retourne un token Live à usage unique, lié au modèle et à l audio."""
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        raise erreur_api(503, "Le service vocal Gemini n est pas configuré.", "GEMINI_LIVE_NON_CONFIGURE")
    try:
        # Les jetons éphémères ne sont acceptés que par la version v1alpha
        # de l'API Gemini Live (documentation Google).
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        maintenant = datetime.now(timezone.utc)
        token = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": maintenant + timedelta(minutes=30),
                "new_session_expire_time": maintenant + timedelta(minutes=1),
                "live_connect_constraints": {
                    "model": MODEL_GEMINI_LIVE,
                    "config": {"response_modalities": ["AUDIO"]},
                },
            }
        )
    except Exception as e:
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC") from e
    if not token or not getattr(token, "name", None):
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC")
    return {"token": token.name, "model": MODEL_GEMINI_LIVE, "utilisateur_id": utilisateur.id}
