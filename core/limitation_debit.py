"""
Limitation de débit (rate limiting) centralisée pour l'API Classinus.

Objectif : empêcher qu'un utilisateur (ou un bot/spam anonyme) puisse
envoyer un nombre illimité de requêtes par minute sur les endpoints
coûteux (chat, génération de contenu), ce qui pourrait faire exploser la
facture des APIs externes (Groq, Gemini, etc.) ou saturer le serveur.

Clé de comptage :
- Token Supabase valide : limite par utilisateur.
- Sinon : limite par IP.

En production multi-instance, définir RATE_LIMIT_STORAGE_URI vers un
stockage partagé (par exemple Redis) afin que les compteurs soient
cohérents entre les instances. Sans cette variable, le stockage mémoire
reste le mode de repli pour préserver les déploiements existants.
"""

import logging
import os

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address


def _cle_limitation(request: Request) -> str:
    """
    Détermine la clé de comptage. Réutilise l'identité déjà authentifiée
    par une dépendance FastAPI sur cette requête, sinon vérifie le token.
    """
    if hasattr(request.state, "_cle_limitation_cache"):
        return request.state._cle_limitation_cache

    cle = None
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            utilisateur_cache = (
                getattr(request.state, "_utilisateur_supabase_verifie", None)
                if getattr(request.state, "_token_supabase_verifie", None) == token
                else None
            )
            if utilisateur_cache is not None:
                cle = f"user:{utilisateur_cache.id}"
            else:
                try:
                    from api.auth import supabase  # import tardif : évite un cycle avec api.auth

                    reponse = supabase.auth.get_user(token)
                    if reponse and reponse.user:
                        cle = f"user:{reponse.user.id}"
                        request.state._token_supabase_verifie = token
                        request.state._utilisateur_supabase_verifie = reponse.user
                except Exception:
                    # Token invalide/expire : repli sur l'IP ; la route protegee
                    # renverra ensuite une 401.
                    pass

    if cle is None:
        cle = f"ip:{get_remote_address(request)}"

    request.state._cle_limitation_cache = cle
    return cle


_storage_uri = os.environ.get("RATE_LIMIT_STORAGE_URI")
if not _storage_uri and (os.environ.get("RAILWAY_SERVICE_ID") or os.environ.get("RAILWAY_ENVIRONMENT_NAME")):
    logging.warning(
        "RATE_LIMIT_STORAGE_URI absent en production : le limiteur utilise "
        "un stockage memoire propre a chaque processus. Configurez un stockage "
        "partage (ex. Redis) pour une limitation coherente entre instances."
    )

limiteur = Limiter(
    key_func=_cle_limitation,
    storage_uri=_storage_uri or "memory://",
)


def gestionnaire_limite_depassee(request: Request, exc):
    """
    Journalise les depassements puis renvoie la reponse 429 standard.
    """
    logging.warning(
        f"RATE LIMIT depasse -- cle={_cle_limitation(request)} "
        f"chemin={request.url.path}"
    )
    return _rate_limit_exceeded_handler(request, exc)
