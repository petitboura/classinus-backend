"""
Verifie le token Supabase envoye par le frontend Next.js (en-tete
`Authorization: Bearer <access_token>`), sans jamais gerer de mot de
passe cote API : l'inscription/connexion se font entierement dans
Next.js via le SDK JS Supabase.
"""

import os
import logging
from fastapi import Header, HTTPException, Request
from supabase import create_client, ClientOptions
from core.client_http_supabase import nouveau_client_http_supabase
from core.erreurs import erreur_api

logging.basicConfig(level=logging.INFO)


def get_secret(key):
    """
    Variables d'environnement uniquement (Railway/uvicorn).
    """
    return os.environ.get(key)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_SECRET = get_secret("SUPABASE_SECRET")

if not SUPABASE_URL or not SUPABASE_SECRET:
    logging.error("SUPABASE_URL ou SUPABASE_SECRET manquant : l'auth API sera toujours en echec.")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET, options=ClientOptions(httpx_client=nouveau_client_http_supabase()))


def _utilisateur_deja_verifie(request: Request, token: str):
    """
    Reutilise uniquement la verification du token faite pendant CETTE
    requete HTTP. Aucun resultat n'est conserve entre deux requetes.
    """
    if getattr(request.state, "_token_supabase_verifie", None) != token:
        return None
    return getattr(request.state, "_utilisateur_supabase_verifie", None)


def _memoriser_utilisateur_requete(request: Request, token: str, utilisateur):
    request.state._token_supabase_verifie = token
    request.state._utilisateur_supabase_verifie = utilisateur


def utilisateur_courant(request: Request, authorization: str = Header(default=None)):
    """
    Dependance FastAPI a utiliser sur toute route protegee. Leve une 401
    si le token est absent, mal forme, ou invalide/expire. Ne verifie PAS
    les permissions metier, qui restent a la charge de chaque route.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise erreur_api(401, "TOKEN_MANQUANT")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise erreur_api(401, "TOKEN_MANQUANT")

    utilisateur_cache = _utilisateur_deja_verifie(request, token)
    if utilisateur_cache is not None:
        return utilisateur_cache

    try:
        reponse = supabase.auth.get_user(token)
    except Exception as e:
        logging.error(f"ERREUR verification token Supabase : {e}")
        raise erreur_api(401, "TOKEN_INVALIDE")

    if not reponse or not reponse.user:
        raise erreur_api(401, "TOKEN_INVALIDE")

    _memoriser_utilisateur_requete(request, token, reponse.user)
    return reponse.user


def utilisateur_optionnel(request: Request, authorization: str = Header(default=None)):
    """
    Variante de utilisateur_courant pour les routes publiques mais
    personnalisables. Renvoie None si le token est absent, mal forme,
    invalide ou expire, plutot qu'une 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None

    utilisateur_cache = _utilisateur_deja_verifie(request, token)
    if utilisateur_cache is not None:
        return utilisateur_cache

    try:
        reponse = supabase.auth.get_user(token)
    except Exception:
        return None

    if not reponse or not reponse.user:
        return None

    _memoriser_utilisateur_requete(request, token, reponse.user)
    return reponse.user
