"""Connexion Render par clé personnelle, isolée par utilisateur.

Le serveur MCP hébergé de Render n'accepte pas l'enregistrement OAuth
automatique : il n'ouvre l'OAuth qu'à quelques outils précis. Classinus utilise
donc la clé personnelle (API key) que Render prévoit pour les autres
applications. La clé est vérifiée auprès de Render, puis conservée uniquement
côté serveur, derrière RLS sans policies, séparément pour chaque compte.
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
        raise ValueError("Saisis une clé personnelle Render valide.")
    token = token.strip()
    try:
        response = requests.get(
            "https://api.render.com/v1/owners?limit=1",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logging.warning("Validation de la clé Render impossible (réseau): %s", type(exc).__name__)
        raise RuntimeError("Render ne répond pas. Réessaie dans quelques instants.") from exc
    if response.status_code in (401, 403):
        raise ValueError("Render a refusé cette clé. Vérifie qu'elle est correcte et qu'elle n'a pas été supprimée.")
    if response.status_code >= 400:
        logging.warning("Validation de la clé Render: HTTP %s", response.status_code)
        raise RuntimeError("Render n'a pas pu valider la clé maintenant. Réessaie plus tard.")
    try:
        _supabase.table("render_mcp_tokens").upsert({
            "user_id": user_id,
            "access_token": token,
        }, on_conflict="user_id").execute()
    except Exception as exc:
        logging.error("Stockage de la clé Render échoué: %s", type(exc).__name__)
        raise RuntimeError("La clé a été validée, mais Classinus n'a pas pu l'enregistrer.") from exc


def obtenir_token_valide(user_id: str):
    if not user_id:
        return None
    try:
        result = (_supabase.table("render_mcp_tokens")
            .select("access_token")
            .eq("user_id", user_id)
            .limit(1)
            .execute())
        return result.data[0]["access_token"] if result.data else None
    except Exception as exc:
        logging.error("Lecture de la clé Render échouée: %s", type(exc).__name__)
        return None


def est_connecte(user_id: str) -> bool:
    return obtenir_token_valide(user_id) is not None


def deconnecter(user_id: str) -> None:
    if not user_id:
        return
    _supabase.table("render_mcp_tokens").delete().eq("user_id", user_id).execute()
