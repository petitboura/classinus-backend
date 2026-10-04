"""Jetons éphémères pour le canal vocal Gemini Live de Classinus.

Le navigateur se connecte directement à Gemini Live pour éviter de faire
transiter l audio temps réel par Classinus. La clé GOOGLE_API_KEY reste
uniquement côté backend.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from api.auth import get_secret, utilisateur_courant
from core.erreurs import erreur_api
from core.gemini_live_config import reglages_gemini_live, version_api_gemini_live
from core.memoire_eleve import obtenir_sommaire, construire_bloc_sommaire
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
        # Le jeton et le WebSocket doivent utiliser la même version d'API.
        client = genai.Client(api_key=api_key)
        maintenant = datetime.now(timezone.utc)
        token = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": maintenant + timedelta(minutes=30),
                "new_session_expire_time": maintenant + timedelta(minutes=1),
                "http_options": {"api_version": version_api_gemini_live(reglages["url"])},
            }
        )
    except Exception as e:
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC") from e
    if not token or not getattr(token, "name", None):
        raise erreur_api(503, "Impossible d initialiser le canal vocal.", "GEMINI_LIVE_TOKEN_ECHEC")
    # Le sommaire de la mémoire de l'étudiant est ajouté aux consignes de la voix à
    # l'ouverture de la session (demande Bourama, 04/10/2026). Il est lu ici, au moment
    # du jeton : il ne change plus jusqu'à la prochaine session vocale. Si la lecture
    # échoue, les consignes partent sans sommaire, la voix reste utilisable.
    bloc_sommaire = construire_bloc_sommaire(obtenir_sommaire(utilisateur.id), pour_voix=True)
    reglages = {**reglages, "consignes": reglages["consignes"] + bloc_sommaire}
    return {"token": token.name, "utilisateur_id": utilisateur.id, **reglages}
