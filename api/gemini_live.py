"""Jetons éphémères pour le canal vocal Gemini Live de Classinus.

Le navigateur se connecte directement à Gemini Live pour éviter de faire
transiter l audio temps réel par Classinus. La clé GOOGLE_API_KEY reste
uniquement côté backend.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from api.auth import get_secret, utilisateur_courant
from core.erreurs import erreur_api
from core.gemini_live_config import reglages_gemini_live
from google import genai

router = APIRouter(prefix="/api/gemini-live", tags=["gemini-live"])

@router.post("/token")
def creer_token_gemini_live(utilisateur=Depends(utilisateur_courant)):
    """Retourne un token Live à usage unique, valable une minute pour ouvrir la session."""
    reglages = reglages_gemini_live()
    api_key = get_secret("GOOGLE_API_KEY")
    if not api_key:
        raise erreur_api(503, "Le service vocal Gemini n est pas configuré.", "GEMINI_LIVE_NON_CONFIGURE")
    try:
        # Même création de jeton que l'exemple officiel Google pour Gemini 3.8 Live
        # (version v1beta, aucune restriction sur le jeton).
        client = genai.Client(api_key=api_key)
        maintenant = datetime.now(timezone.utc)
        token = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": maintenant + timedelta(minutes=30),
                "new_session_expire_time": maintenant + timedelta(minutes=1),
                "http_options": {"api_version": "v1beta"},
            }
        )
    except Exception as e:
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC") from e
    if not token or not getattr(token, "name", None):
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC")
    return {"token": token.name, "utilisateur_id": utilisateur.id, **reglages}
