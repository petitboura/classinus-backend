"""Connexion Vercel par jeton personnel, isolée par utilisateur.

Même principe que render_mcp : la personne colle un jeton créé dans les réglages
de son compte Vercel (Account Settings, Tokens). Classinus le vérifie auprès de
Vercel, puis le conserve uniquement côté serveur, derrière RLS sans policies,
séparément pour chaque compte. Aucun jeton n'est partagé entre utilisateurs.
"""
import logging
import os
import requests
from supabase import create_client, ClientOptions
from core.client_http_supabase import nouveau_client_http_supabase

_supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SECRET"),
    options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
)


def enregistrer_token(user_id: str, token: str) -> None:
    if not user_id or not token or not token.strip():
        raise ValueError("Saisis un jeton Vercel valide.")
    token = token.strip()
    try:
        response = requests.get(
            "https://api.vercel.com/v2/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logging.warning("Validation du jeton Vercel impossible (réseau): %s", type(exc).__name__)
        raise RuntimeError("Vercel ne répond pas. Réessaie dans quelques instants.") from exc
    if response.status_code in (401, 403):
        raise ValueError("Vercel a refusé ce jeton. Vérifie qu'il est correct et qu'il n'a pas expiré.")
    if response.status_code >= 400:
        logging.warning("Validation du jeton Vercel: HTTP %s", response.status_code)
        raise RuntimeError("Vercel n'a pas pu valider le jeton maintenant. Réessaie plus tard.")
    try:
        _supabase.table("vercel_mcp_tokens").upsert({
            "user_id": user_id,
            "access_token": token,
        }, on_conflict="user_id").execute()
    except Exception as exc:
        logging.error("Stockage du jeton Vercel échoué: %s", type(exc).__name__)
        raise RuntimeError("Le jeton a été validé, mais Classinus n'a pas pu l'enregistrer.") from exc


def obtenir_token_valide(user_id: str):
    if not user_id:
        return None
    try:
        result = (_supabase.table("vercel_mcp_tokens")
            .select("access_token")
            .eq("user_id", user_id)
            .limit(1)
            .execute())
        return result.data[0]["access_token"] if result.data else None
    except Exception as exc:
        logging.error("Lecture du jeton Vercel échouée: %s", type(exc).__name__)
        return None


def est_connecte(user_id: str) -> bool:
    return obtenir_token_valide(user_id) is not None


def deconnecter(user_id: str) -> None:
    if not user_id:
        return
    _supabase.table("vercel_mcp_tokens").delete().eq("user_id", user_id).execute()
