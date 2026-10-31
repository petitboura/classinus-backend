"""OAuth DCR pour le serveur MCP officiel Higgsfield, par utilisateur."""
import base64
import hashlib
import logging
import os
import secrets
import string
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from supabase import create_client, ClientOptions
from core.client_http_supabase import nouveau_client_http_supabase

MCP_URL = "https://mcp.higgsfield.ai/mcp"
RESOURCE_METADATA_URL = "https://mcp.higgsfield.ai/.well-known/oauth-protected-resource"
MARGE_RAFRAICHISSEMENT = timedelta(minutes=5)
CACHE_TTL = 120
# Un etat de connexion non finalise au bout de ce delai est refuse puis purge.
DUREE_VIE_ETAT = timedelta(minutes=15)

_supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SECRET"),
    options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
)
_cache = {}


def _pkce():
    verifier = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(96))
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _oauth_metadata():
    """Découvre les endpoints à partir des métadonnées annoncées par Higgsfield."""
    r = httpx.get(RESOURCE_METADATA_URL, timeout=10)
    r.raise_for_status()
    resource = r.json()
    issuers = resource.get("authorization_servers") or []
    hints = resource.get("higgsfield_auth_hints") or {}
    options = hints.get("options") or []
    # Higgsfield annonce son serveur d'autorisation (clerk.higgsfield.ai) dans
    # authorization_servers. Si une option du flux navigateur nomme un
    # serveur amont explicite, on l'utilise en priorite pour eviter un
    # decalage d'issuer.
    upstream = next(
        (option.get("upstream_authorization_server") for option in options
         if option.get("flow") == "authorization_code_pkce"
         and option.get("upstream_authorization_server")),
        None,
    )
    issuer = (upstream or (issuers[0] if issuers else "")).rstrip("/")
    if not issuer:
        raise RuntimeError("Higgsfield n'annonce aucun authorization server.")
    candidates = [
        f"{issuer}/.well-known/oauth-authorization-server",
        f"{issuer}/.well-known/openid-configuration",
    ]
    last_error = None
    for url in candidates:
        try:
            response = httpx.get(url, timeout=10)
            response.raise_for_status()
            metadata = response.json()
            if metadata.get("authorization_endpoint") and metadata.get("token_endpoint"):
                metadata["_issuer"] = issuer
                # Droits demandes : ceux que le serveur MCP annonce pour lui-meme
                # (openid, email, offline_access), jamais la liste complete du
                # serveur d'autorisation (elle inclut des droits inutiles ici,
                # comme private_metadata et user:org:read).
                metadata["_scopes"] = resource.get("scopes_supported") or []
                return metadata
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Métadonnées OAuth Higgsfield incomplètes: {last_error}")


def _limite_etat():
    return (datetime.now(timezone.utc) - DUREE_VIE_ETAT).isoformat()


def _purger_etats_expires():
    """Supprime les connexions abandonnees (code_verifier et client_secret compris)."""
    try:
        _supabase.table("higgsfield_oauth_temp").delete().lt("created_at", _limite_etat()).execute()
    except Exception as exc:
        logging.warning("Purge des etats Higgsfield expires impossible: %s", exc)


def demarrer_connexion(user_id, agent_id=None):
    if not user_id:
        return None
    _purger_etats_expires()
    try:
        metadata = _oauth_metadata()
        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise RuntimeError("Higgsfield ne publie pas de registration_endpoint DCR.")
        redirect_uri = os.environ.get("URL_RETOUR_APP")
        if not redirect_uri:
            raise RuntimeError("URL_RETOUR_APP absente.")
        registration = httpx.post(
            registration_endpoint,
            json={
                "client_name": "Classinus",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
            timeout=10,
        )
        registration.raise_for_status()
        client = registration.json()
        client_id = client.get("client_id")
        if not client_id:
            raise RuntimeError("Enregistrement OAuth sans client_id.")
        state = secrets.token_urlsafe(32)
        verifier, challenge = _pkce()
        _supabase.table("higgsfield_oauth_temp").insert({
            "state": state,
            "user_id": user_id,
            "agent_id": agent_id,
            "code_verifier": verifier,
            "client_id": client_id,
            "client_secret": client.get("client_secret"),
            "redirect_uri": redirect_uri,
            "issuer": metadata["_issuer"],
            "token_endpoint": metadata["token_endpoint"],
        }).execute()
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": MCP_URL,
        }
        scopes = metadata.get("_scopes") or ["openid", "email", "offline_access"]
        params["scope"] = " ".join(scopes)
        return f'{metadata["authorization_endpoint"]}?{urlencode(params)}'
    except Exception as exc:
        logging.error("Démarrage OAuth Higgsfield échoué: %s", exc)
        return None


def etat_en_attente(state):
    # Appelee pour TOUTE finalisation OAuth (Notion, Google Drive, GitHub aussi).
    # Une erreur ici (table absente, base injoignable) ne doit jamais bloquer
    # ces autres services : on repond simplement "pas un etat Higgsfield".
    try:
        result = (
            _supabase.table("higgsfield_oauth_temp").select("state")
            .eq("state", state).gte("created_at", _limite_etat()).execute()
        )
        return bool(result.data)
    except Exception as exc:
        logging.warning("Verification de l'etat OAuth Higgsfield impossible: %s", exc)
        return False


def finaliser_connexion(code, state):
    result = (
        _supabase.table("higgsfield_oauth_temp").select("*")
        .eq("state", state).gte("created_at", _limite_etat()).execute()
    )
    if not result.data:
        return False, "Session Higgsfield expirée ou déjà utilisée."
    pending = result.data[0]
    # Consommer le state avant l'échange évite sa réutilisation.
    _supabase.table("higgsfield_oauth_temp").delete().eq("state", state).execute()
    try:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "client_id": pending["client_id"],
            "code_verifier": pending["code_verifier"],
            "resource": MCP_URL,
        }
        if pending.get("client_secret"):
            payload["client_secret"] = pending["client_secret"]
        response = httpx.post(pending["token_endpoint"], data=payload, timeout=15)
        response.raise_for_status()
        tokens = response.json()
        if not tokens.get("access_token"):
            raise RuntimeError("Réponse OAuth sans access_token.")
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        _supabase.table("higgsfield_oauth_connections").upsert({
            "user_id": pending["user_id"],
            "client_id": pending["client_id"],
            "client_secret": pending.get("client_secret"),
            "issuer": pending["issuer"],
            "token_endpoint": pending["token_endpoint"],
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": expiry.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id").execute()
        _cache.pop(pending["user_id"], None)
        return True, "Compte Higgsfield connecté."
    except Exception as exc:
        logging.error("Échange OAuth Higgsfield échoué: %s", exc)
        return False, "Connexion Higgsfield impossible (code invalide ou erreur du fournisseur)."


def obtenir_token_valide(user_id):
    if not user_id:
        return None
    now = time.time()
    cached = _cache.get(user_id)
    if cached and cached["until"] > now:
        return cached["token"]
    result = _supabase.table("higgsfield_oauth_connections").select("*").eq("user_id", user_id).execute()
    if not result.data:
        _cache[user_id] = {"token": None, "until": now + CACHE_TTL}
        return None
    row = result.data[0]
    try:
        expires = datetime.fromisoformat(row["expires_at"])
        token = row["access_token"]
        if datetime.now(timezone.utc) + MARGE_RAFRAICHISSEMENT >= expires:
            refresh_token = row.get("refresh_token")
            if not refresh_token:
                _cache[user_id] = {"token": None, "until": now + CACHE_TTL}
                return None
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": row["client_id"],
                "resource": MCP_URL,
            }
            if row.get("client_secret"):
                payload["client_secret"] = row["client_secret"]
            response = httpx.post(row["token_endpoint"], data=payload, timeout=15)
            response.raise_for_status()
            tokens = response.json()
            token = tokens["access_token"]
            expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
            _supabase.table("higgsfield_oauth_connections").update({
                "access_token": token,
                "refresh_token": tokens.get("refresh_token", refresh_token),
                "expires_at": expiry.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("user_id", user_id).execute()
        _cache[user_id] = {"token": token, "until": now + CACHE_TTL}
        return token
    except Exception as exc:
        logging.warning("Token Higgsfield à renouveler pour user %s: %s", user_id, exc)
        _cache[user_id] = {"token": None, "until": now + CACHE_TTL}
        return None


def _ligne_existe(user_id):
    result = _supabase.table("higgsfield_oauth_connections").select("user_id").eq("user_id", user_id).execute()
    return bool(result.data)


def est_connecte(user_id):
    """True seulement si le jeton est utilisable (valide ou rafraichissable)."""
    if not user_id:
        return False
    return obtenir_token_valide(user_id) is not None


def a_reconnecter(user_id):
    """Connexion enregistree mais devenue inutilisable (jeton expire ou revoque)."""
    if not user_id:
        return False
    return _ligne_existe(user_id) and not est_connecte(user_id)


def deconnecter(user_id):
    if not user_id:
        return False
    _supabase.table("higgsfield_oauth_connections").delete().eq("user_id", user_id).execute()
    _cache.pop(user_id, None)
    return True


# Compte de service partage (31/10/2026, demande de Bourama) : un seul compte
# Classinus connecte via le flux OAuth ci-dessus, utilise par le backend pour
# les fonctions MCP-only de tous les utilisateurs. Son identifiant vient de
# la variable Railway HIGGSFIELD_MCP_SERVICE_USER_ID (l'UUID Classinus du
# compte qui a fait la connexion), jamais du code. Sans elle, le MCP partage
# est simplement non configure. Les connexions personnelles des utilisateurs
# ne sont ni lues ni modifiees par ces fonctions.

def utilisateur_service():
    valeur = (os.environ.get("HIGGSFIELD_MCP_SERVICE_USER_ID") or "").strip()
    return valeur or None


def etat_service():
    """Etat du compte partage, en booleens seulement (aucune valeur de jeton)."""
    service_id = utilisateur_service()
    if not service_id:
        return {"configure": False, "connecte": False, "a_reconnecter": False, "refresh_present": False}
    try:
        result = _supabase.table("higgsfield_oauth_connections").select(
            "refresh_token, expires_at"
        ).eq("user_id", service_id).execute()
    except Exception as exc:
        logging.error("Etat du MCP Higgsfield partage illisible: %s", exc)
        return {"configure": True, "connecte": False, "a_reconnecter": True, "refresh_present": False}
    if not result.data:
        return {"configure": True, "connecte": False, "a_reconnecter": False, "refresh_present": False}
    connecte = obtenir_token_valide(service_id) is not None
    return {
        "configure": True,
        "connecte": connecte,
        "a_reconnecter": not connecte,
        "refresh_present": bool(result.data[0].get("refresh_token")),
    }


def obtenir_token_service():
    service_id = utilisateur_service()
    if not service_id:
        return None
    return obtenir_token_valide(service_id)
