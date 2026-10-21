"""OAuth par utilisateur pour les serveurs MCP officiels Vercel, Railway et Supabase.

Vercel/Supabase : découverte OAuth MCP + Dynamic Client Registration quand le serveur
l'annonce. Railway : OAuth officiel avec client applicatif configuré côté serveur.
Aucun jeton partagé entre utilisateurs.
"""
import base64
import hashlib
import logging
import os
import secrets
import string
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from supabase import create_client, ClientOptions
from core.client_http_supabase import nouveau_client_http_supabase

URL_RETOUR = os.environ.get("URL_RETOUR_APP")
MARGE_RAFRAICHISSEMENT = timedelta(minutes=5)
CACHE_TTL = 120
DUREE_VIE_ETAT = timedelta(minutes=15)

FOURNISSEURS = {
    "vercel_mcp": {
        "resource_url": "https://mcp.vercel.com/",
        "mcp_url": "https://mcp.vercel.com",
        "scopes": ["openid", "offline_access"],
    },
    "railway_mcp": {
        "resource_url": "https://mcp.railway.com/",
        "mcp_url": "https://mcp.railway.com",
        "issuer": "https://backboard.railway.com",
        "authorization_endpoint": "https://backboard.railway.com/oauth/auth",
        "token_endpoint": "https://backboard.railway.com/oauth/token",
        "client_id_env": "RAILWAY_OAUTH_CLIENT_ID",
        "client_secret_env": "RAILWAY_OAUTH_CLIENT_SECRET",
        "scopes": ["openid", "email", "profile", "offline_access"],
        "extra_auth_params": {"prompt": "consent"},
        "token_auth_method": "client_secret_basic",
        "send_resource": False,
    },
    "supabase_mcp": {
        "resource_url": "https://mcp.supabase.com/mcp",
        "mcp_url": "https://mcp.supabase.com/mcp",
        "scopes": ["openid", "offline_access"],
    },
}

_supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SECRET"),
    options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
)
_cache = {}


def _pkce():
    verifier = "".join(secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(96))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _limite_etat():
    return (datetime.now(timezone.utc) - DUREE_VIE_ETAT).isoformat()


def _metadata_resource(resource_url):
    parsed = urlparse(resource_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [f"{origin}/.well-known/oauth-protected-resource"]
    path = parsed.path.strip("/")
    if path:
        candidates.insert(0, f"{origin}/.well-known/oauth-protected-resource/{path}")
    last_error = None
    for url in candidates:
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            if data.get("authorization_servers"):
                return data
        except Exception as exc:
            last_error = exc
    if last_error:
        logging.info("Découverte OAuth MCP (%s) : %s", resource_url, last_error)
    return {}


def _metadata_authorization(issuer):
    issuer = issuer.rstrip("/")
    candidates = [
        f"{issuer}/.well-known/oauth-authorization-server",
        f"{issuer}/.well-known/openid-configuration",
    ]
    last_error = None
    for url in candidates:
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
            if data.get("authorization_endpoint") and data.get("token_endpoint"):
                data["_issuer"] = issuer
                return data
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Métadonnées OAuth incomplètes pour {issuer}: {last_error}")


def _obtenir_configuration(service):
    config = FOURNISSEURS.get(service)
    if not config:
        raise RuntimeError("Fournisseur MCP inconnu.")
    resource = {}
    if config.get("authorization_endpoint") and config.get("token_endpoint"):
        metadata = {
            "issuer": config.get("issuer"),
            "authorization_endpoint": config["authorization_endpoint"],
            "token_endpoint": config["token_endpoint"],
            "registration_endpoint": None,
            "token_endpoint_auth_methods_supported": [config.get("token_auth_method", "client_secret_post")],
        }
    else:
        resource = _metadata_resource(config["resource_url"])
        issuers = resource.get("authorization_servers") or []
        if not issuers:
            raise RuntimeError("Le serveur MCP n'annonce aucun serveur OAuth.")
        metadata = _metadata_authorization(issuers[0])
    metadata["_resource"] = resource.get("resource", config["resource_url"])
    metadata["_config"] = config
    return metadata


def _client_oauth(service, metadata, redirect_uri):
    config = metadata["_config"]
    registration_endpoint = metadata.get("registration_endpoint")
    if not registration_endpoint and not config.get("client_id_env"):
        # Certaines métadonnées sont publiées par le serveur de ressources,
        # alors que registration_endpoint se trouve sur l'issuer.
        issuer = metadata.get("_issuer") or metadata.get("issuer") or config.get("issuer")
        if issuer:
            auth_meta = _metadata_authorization(issuer)
            metadata.update(auth_meta)
            registration_endpoint = metadata.get("registration_endpoint")
    if registration_endpoint:
        # Le fournisseur annonce les méthodes d'authentification qu'il accepte au jeton.
        # Si "none" n'y figure pas (cas de Supabase : seulement des méthodes à secret),
        # on demande une méthode à secret au lieu d'un client public.
        methodes_annoncees = metadata.get("token_endpoint_auth_methods_supported") or []
        methode_demandee = "none"
        if methodes_annoncees and "none" not in methodes_annoncees:
            methode_demandee = "client_secret_post" if "client_secret_post" in methodes_annoncees else methodes_annoncees[0]
        response = httpx.post(
            registration_endpoint,
            json={
                "client_name": "Classinus",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": methode_demandee,
            },
            timeout=10,
        )
        response.raise_for_status()
        client = response.json()
        if not client.get("client_id"):
            raise RuntimeError("Enregistrement OAuth sans client_id.")
        client_secret = client.get("client_secret")
        # Un secret reçu à l'enregistrement doit être renvoyé à l'échange du code :
        # annoncer "none" dans ce cas fait refuser le jeton (« Required parameter: client_secret »).
        if client_secret:
            methode_enregistree = client.get("token_endpoint_auth_method")
            if methode_enregistree in ("client_secret_post", "client_secret_basic"):
                methode = methode_enregistree
            elif methodes_annoncees and "client_secret_post" not in methodes_annoncees and "client_secret_basic" in methodes_annoncees:
                methode = "client_secret_basic"
            else:
                methode = "client_secret_post"
        else:
            methode = "none"
        # Booléen seulement : jamais la valeur du secret dans les journaux.
        logging.info(
            "Enregistrement OAuth %s : méthode demandée %s, secret reçu %s, méthode retenue %s",
            service, methode_demandee, bool(client_secret), methode,
        )
        return client.get("client_id"), client_secret, methode
    client_id = os.environ.get(config.get("client_id_env", ""))
    client_secret = os.environ.get(config.get("client_secret_env", ""))
    if not client_id:
        raise RuntimeError(
            f"Enregistrement OAuth dynamique indisponible ; configurez {config.get('client_id_env', 'le client OAuth')}."
        )
    return client_id, client_secret, config.get("token_auth_method", "client_secret_post")


def demarrer_connexion(service, user_id, agent_id=None):
    if service not in FOURNISSEURS or not user_id or not URL_RETOUR:
        return None
    try:
        _supabase.table("platform_mcp_oauth_temp").delete().lt("created_at", _limite_etat()).execute()
        metadata = _obtenir_configuration(service)
        client_id, client_secret, auth_method = _client_oauth(service, metadata, URL_RETOUR)
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(32)
        config = metadata["_config"]
        _supabase.table("platform_mcp_oauth_temp").insert({
            "state": state,
            "service": service,
            "user_id": user_id,
            "agent_id": agent_id,
            "code_verifier": verifier,
            "client_id": client_id,
            "client_secret": client_secret,
            "token_endpoint": metadata["token_endpoint"],
            "issuer": metadata.get("_issuer") or metadata.get("issuer") or config.get("issuer"),
            "resource_url": metadata["_resource"],
            "redirect_uri": URL_RETOUR,
            "token_auth_method": auth_method,
        }).execute()
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": URL_RETOUR,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": " ".join(config.get("scopes") or metadata.get("scopes_supported") or []),
        }
        if metadata.get("_resource") and config.get("send_resource", True):
            params["resource"] = metadata["_resource"]
        params.update(config.get("extra_auth_params") or {})
        return f'{metadata["authorization_endpoint"]}?{urlencode(params)}'
    except Exception as exc:
        logging.error("Démarrage OAuth %s échoué: %s", service, exc)
        return None


def etat_en_attente(state):
    if not state:
        return None
    try:
        result = (
            _supabase.table("platform_mcp_oauth_temp").select("service")
            .eq("state", state).gte("created_at", _limite_etat()).execute()
        )
        return result.data[0]["service"] if result.data else None
    except Exception as exc:
        logging.warning("Lecture état OAuth MCP impossible: %s", exc)
        return None


def _poster_token(pending, payload):
    headers = {"Accept": "application/json"}
    auth_method = pending.get("token_auth_method") or "none"
    auth = None
    if auth_method == "client_secret_basic":
        auth = (pending["client_id"], pending.get("client_secret") or "")
    elif auth_method == "none":
        payload["client_id"] = pending["client_id"]
    else:
        payload["client_id"] = pending["client_id"]
        if pending.get("client_secret"):
            payload["client_secret"] = pending["client_secret"]
    response = httpx.post(
        pending["token_endpoint"], data=payload, headers=headers, auth=auth, timeout=15
    )
    if response.status_code >= 400:
        # Diagnostic : on garde le corps renvoyé par le fournisseur (il nomme
        # en général le champ refusé) et les NOMS des champs envoyés, jamais
        # leurs valeurs (code, verifier et secret restent hors des logs).
        logging.error(
            "Jeton OAuth refusé par %s : statut %s, méthode %s, champs envoyés %s, réponse : %s",
            pending["token_endpoint"],
            response.status_code,
            auth_method,
            sorted(payload.keys()),
            (response.text or "")[:500],
        )
    response.raise_for_status()
    return response.json()


def finaliser_connexion(service, code, state):
    result = (
        _supabase.table("platform_mcp_oauth_temp").select("*")
        .eq("state", state).eq("service", service)
        .gte("created_at", _limite_etat()).execute()
    )
    if not result.data:
        return False, "Session de connexion expirée ou déjà utilisée."
    pending = result.data[0]
    _supabase.table("platform_mcp_oauth_temp").delete().eq("state", state).execute()
    try:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["code_verifier"],
        }
        if service != "railway_mcp":
            payload["resource"] = pending["resource_url"]
        tokens = _poster_token(pending, payload)
        if not tokens.get("access_token"):
            raise RuntimeError("Réponse OAuth sans access_token.")
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        _supabase.table("platform_mcp_oauth_connections").upsert({
            "user_id": pending["user_id"],
            "service": service,
            "client_id": pending["client_id"],
            "client_secret": pending.get("client_secret"),
            "token_endpoint": pending["token_endpoint"],
            "token_auth_method": pending.get("token_auth_method"),
            "resource_url": pending["resource_url"],
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": expiry.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,service").execute()
        _cache.pop((service, pending["user_id"]), None)
        return True, f"Compte {service} connecté."
    except Exception as exc:
        logging.error("Échange OAuth %s échoué: %s", service, exc)
        return False, f"Connexion {service} impossible (code invalide ou erreur du fournisseur)."


def obtenir_token_valide(service, user_id):
    if service not in FOURNISSEURS or not user_id:
        return None
    now = time.time()
    key = (service, user_id)
    cached = _cache.get(key)
    if cached and cached["until"] > now:
        return cached["token"]
    result = (
        _supabase.table("platform_mcp_oauth_connections").select("*")
        .eq("user_id", user_id).eq("service", service).execute()
    )
    if not result.data:
        _cache[key] = {"token": None, "until": now + CACHE_TTL}
        return None
    row = result.data[0]
    token = row["access_token"]
    try:
        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) + MARGE_RAFRAICHISSEMENT >= expires:
            refresh = row.get("refresh_token")
            if not refresh:
                _cache[key] = {"token": None, "until": now + CACHE_TTL}
                return None
            payload = {"grant_type": "refresh_token", "refresh_token": refresh}
            if service != "railway_mcp":
                payload["resource"] = row["resource_url"]
            tokens = _poster_token(row, payload)
            token = tokens.get("access_token")
            if not token:
                raise RuntimeError("Rafraîchissement OAuth sans access_token.")
            expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
            _supabase.table("platform_mcp_oauth_connections").update({
                "access_token": token,
                "refresh_token": tokens.get("refresh_token", refresh),
                "expires_at": expiry.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("user_id", user_id).eq("service", service).execute()
    except Exception as exc:
        logging.warning("Jeton OAuth %s inutilisable pour %s: %s", service, user_id, exc)
        token = None
    _cache[key] = {"token": token, "until": now + CACHE_TTL}
    return token


def _ligne_existe(service, user_id):
    result = (
        _supabase.table("platform_mcp_oauth_connections").select("user_id")
        .eq("user_id", user_id).eq("service", service).execute()
    )
    return bool(result.data)


def est_connecte(service, user_id):
    """True seulement si le jeton est utilisable (valide ou rafraichissable)."""
    if service not in FOURNISSEURS or not user_id:
        return False
    return obtenir_token_valide(service, user_id) is not None


def a_reconnecter(service, user_id):
    """Connexion enregistree mais devenue inutilisable (jeton expire ou revoque)."""
    if service not in FOURNISSEURS or not user_id:
        return False
    return _ligne_existe(service, user_id) and not est_connecte(service, user_id)


def deconnecter(service, user_id):
    if service not in FOURNISSEURS or not user_id:
        return False
    _supabase.table("platform_mcp_oauth_connections").delete().eq("user_id", user_id).eq("service", service).execute()
    _cache.pop((service, user_id), None)
    return True
