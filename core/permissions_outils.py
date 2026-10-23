"""Persistance des permissions personnelles d'outils MCP."""

import os
from datetime import datetime, timezone
from typing import Literal

from supabase import ClientOptions, create_client
from core.client_http_supabase import nouveau_client_http_supabase

ModePermission = Literal["autoriser", "demander", "refuser"]
_TABLE = "permissions_outils_utilisateur"

_URL = os.environ.get("SUPABASE_URL")
_SECRET = os.environ.get("SUPABASE_SECRET")
if not _URL or not _SECRET:
    raise RuntimeError("SUPABASE_URL et SUPABASE_SECRET sont requis pour les permissions MCP.")

_supabase = create_client(
    _URL,
    _SECRET,
    options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
)

def charger_permissions_outils(user_id: str | None) -> dict[str, ModePermission]:
    """Charge uniquement les règles du compte ciblé; les erreurs remontent à l'appelant."""
    if not user_id:
        return {}
    reponse = _supabase.table(_TABLE).select("nom_outil,mode").eq("user_id", user_id).execute()
    permissions: dict[str, ModePermission] = {}
    for ligne in reponse.data or []:
        nom = ligne.get("nom_outil")
        mode = ligne.get("mode")
        if nom and mode in {"autoriser", "demander", "refuser"}:
            permissions[nom] = mode
    return permissions

def enregistrer_permission_outil(user_id: str, nom_outil: str, mode: ModePermission) -> None:
    """Écrit la décision personnelle sur la clé composée utilisateur + outil."""
    if mode not in {"autoriser", "demander", "refuser"}:
        raise ValueError("Mode d'autorisation inconnu.")
    _supabase.table(_TABLE).upsert(
        {
            "user_id": user_id,
            "nom_outil": nom_outil,
            "mode": mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,nom_outil",
    ).execute()
