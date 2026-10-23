"""Gestion sécurisée des serveurs MCP personnels via HTTP Streamable.

Configurations et jetons restent côté backend dans des tables sans politique
d'accès client. Les URLs sont validées contre les destinations privées/SSRF.
Les noms d'outils sont isolés du registre officiel et leur exécution exige
une confirmation utilisateur.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import logging
import os
import re
import secrets
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client
from supabase import create_client, ClientOptions
from client_http_supabase import nouveau_client_http_supabase

from api.auth import utilisateur_courant

router = APIRouter(prefix="/api/mcp-personnalises", tags=["MCP personnalisés"])
_SUPABASE = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SECRET"),
    options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
)
URL_RETOUR = os.environ.get("URL_RETOUR_APP")
DUREE_ETAT_OAUTH = timedelta(minutes=15)
DUREE_CACHE_OUTILS = 300
TAILLE_MAX_OUTILS_PAR_SERVEUR = 50
NOMBRE_MAX_SERVEURS_PAR_COMPTE = 10
_PREFIXE_OUTILS = "custommcp_"
_CACHE_OUTILS: dict[tuple, dict] = {}


class ServeurPayload(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=2048)
    auth_type: Literal["none", "bearer", "oauth"]
    # Token accepté en entrée seulement ; jamais renvoyé par l'API.
    token: str | None = Field(default=None, max_length=4096)


class ActifPayload(BaseModel):
    actif: bool


def _erreur(code: str, message: str, statut: int = 400):
    raise HTTPException(status_code=statut, detail={"code": code, "message": message})


def valider_url_mcp(url: str) -> str:
    """HTTPS seulement et hôtes publics ; vérifié avant découverte et appels MCP."""
    try:
        parsed = urlparse(url.strip())
        hostname = parsed.hostname
        port = parsed.port or 443
    except Exception:
        raise ValueError("L’URL du serveur MCP est invalide.")
    if parsed.scheme.lower() != "https" or not hostname:
        raise ValueError("L’URL doit utiliser HTTPS et comporter un nom d’hôte.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("L’URL ne doit contenir ni identifiants ni fragment.")
    if port < 1 or port > 65535:
        raise ValueError("Le port de l’URL est invalide.")
    hostname = hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".localhost", ".local", ".internal", ".test")):
        raise ValueError("Les serveurs locaux ou privés ne peuvent pas être connectés.")
    noms_secrets = {"token", "access_token", "api_key", "apikey", "key", "secret", "password", "authorization"}
    if any(cle.lower() in noms_secrets for cle, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise ValueError("Retire les clés et jetons de l’URL ; utilise le champ d’authentification.")
    try:
        ip_directe = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            adresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError:
            raise ValueError("Le nom d’hôte du serveur MCP ne peut pas être résolu.")
        ips = {item[4][0].split("%", 1)[0] for item in adresses}
        if not ips:
            raise ValueError("Le nom d’hôte du serveur MCP ne possède aucune adresse publique.")
        for valeur in ips:
            try:
                ip = ipaddress.ip_address(valeur)
            except ValueError:
                raise ValueError("L’adresse du serveur MCP est invalide.")
            if not ip.is_global:
                raise ValueError("Le serveur MCP pointe vers une adresse IP privée ou réservée.")
    else:
        if not ip_directe.is_global:
            raise ValueError("Les adresses IP privées ou réservées sont interdites.")
    return urlunparse((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.params, parsed.query, ""))


def _serveur_pour_utilisateur(serveur_id: str, user_id: str) -> dict:
    try:
        lignes = (
            _SUPABASE.table("mcp_personnalises").select("*")
            .eq("id", serveur_id).eq("user_id", user_id).limit(1).execute().data or []
        )
    except Exception as exc:
        logging.error("Lecture d'un MCP personnalisé impossible (%s).", type(exc).__name__)
        _erreur("MCP_LECTURE_IMPOSSIBLE", "Impossible de lire ce serveur MCP pour le moment.", 503)
    if not lignes:
        _erreur("MCP_INTROUVABLE", "Ce serveur MCP n’existe pas ou ne t’appartient pas.", 404)
    return lignes[0]


def _headers_serveur(serveur: dict, user_id: str) -> dict | None:
    mode = serveur.get("auth_type", "none")
    if mode == "none":
        return {}
    if mode == "bearer":
        jeton = serveur.get("bearer_token")
        return {"Authorization": f"Bearer {jeton}"} if jeton else None
    if mode == "oauth":
        jeton = obtenir_token_oauth(serveur["id"], user_id)
        return {"Authorization": f"Bearer {jeton}"} if jeton else None
    return None


async def _lister_outils_async(url: str, headers: dict | None):
    async with create_mcp_http_client(headers=headers) as client:
        async with streamable_http_client(url, http_client=client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resultat = await session.list_tools()
                return list(resultat.tools or [])


def _lister_outils_reseau(url: str, headers: dict | None):
    adresse = valider_url_mcp(url)
    try:
        return asyncio.run(asyncio.wait_for(_lister_outils_async(adresse, headers), timeout=18))
    except Exception as exc:
        logging.info("Découverte MCP personnalisée impossible (hôte %s, type %s).", urlparse(adresse).hostname, type(exc).__name__)
        raise ValueError("Impossible de joindre ce serveur MCP. Vérifie son URL, son accessibilité et son authentification.")


def _nom_outil_expose(serveur_id: str, nom_reel: str) -> str:
    """Nom unique entre serveurs et inférieur à la limite de 64 caractères."""
    origine = re.sub(r"[^a-zA-Z0-9_-]", "_", nom_reel).strip("_").lower() or "outil"
    trouve = re.match(r"[a-z]+", origine)
    verbe = (trouve.group(0) if trouve else "outil")[:8]
    empreinte = hashlib.sha256(nom_reel.encode("utf-8")).hexdigest()[:4]
    return f"{_PREFIXE_OUTILS}{verbe}_{serveur_id.replace('-', '')[:6]}_{origine[:28]}_{empreinte}"[:64]


def _invalider_cache_serveur(serveur_id: str):
    for cle in list(_CACHE_OUTILS):
        if cle and cle[0] == serveur_id:
            _CACHE_OUTILS.pop(cle, None)


def _outils_bruts_serveur(serveur: dict, user_id: str, headers: dict | None) -> list[dict]:
    url = valider_url_mcp(serveur["url"])
    jeton_cache = hashlib.sha256((headers or {}).get("Authorization", "").encode()).hexdigest()[:12]
    cle_cache = (serveur["id"], user_id, serveur.get("updated_at"), jeton_cache, url)
    maintenant = time.time()
    entree = _CACHE_OUTILS.get(cle_cache)
    if entree and entree["expire_a"] > maintenant:
        return entree["outils"]
    outils_reseau = _lister_outils_reseau(url, headers)
    resultat = []
    noms_exposes = set()
    for outil in outils_reseau[:TAILLE_MAX_OUTILS_PAR_SERVEUR]:
        nom_reel = str(getattr(outil, "name", "") or "").strip()
        if not nom_reel:
            continue
        nom_expose = _nom_outil_expose(serveur["id"], nom_reel)
        if nom_expose in noms_exposes:
            suffixe = hashlib.sha256((serveur["id"] + nom_reel).encode()).hexdigest()[:4]
            nom_expose = f"{nom_expose[:59]}_{suffixe}"[:64]
        noms_exposes.add(nom_expose)
        schema = getattr(outil, "input_schema", None) or getattr(outil, "inputSchema", None) or {"type": "object", "properties": {}}
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        description = str(getattr(outil, "description", "") or "")
        resultat.append({
            "nom": nom_expose,
            "nom_reel": nom_reel,
            "label": f"{serveur['nom']} · {nom_reel}"[:120],
            "description": f"Outil d’un serveur MCP personnalisé ({serveur['nom']}). {description}"[:4000],
            "icone": "Server",
            "onglet": "action_app",
            "parameters": schema,
            "url": url,
        })
    _CACHE_OUTILS[cle_cache] = {"outils": resultat, "expire_a": maintenant + DUREE_CACHE_OUTILS}
    for cle, valeur in list(_CACHE_OUTILS.items()):
        if valeur["expire_a"] <= maintenant:
            _CACHE_OUTILS.pop(cle, None)
    return resultat


def lister_outils_pour_utilisateur(user_id: str) -> list[dict]:
    """Catalogue personnalisé et routes pour le chat. Les secrets restent côté serveur."""
    if not user_id:
        return []
    try:
        serveurs = (
            _SUPABASE.table("mcp_personnalises").select("*")
            .eq("user_id", user_id).eq("actif", True).execute().data or []
        )
    except Exception as exc:
        logging.error("Lecture des MCP personnels impossible pour l’assistant (%s).", type(exc).__name__)
        return []

    def charger_serveur(serveur: dict) -> list[dict]:
        try:
            headers = _headers_serveur(serveur, user_id)
            if headers is None:
                return []
            return [
                {
                    **outil,
                    "route": {"url": outil["url"], "headers": headers, "nom_reel": outil["nom_reel"], "custom_mcp": True},
                }
                for outil in _outils_bruts_serveur(serveur, user_id, headers)
            ]
        except Exception as exc:
            logging.info("MCP personnalisé %s indisponible pour ce tour (%s).", serveur.get("id"), type(exc).__name__)
            return []

    # Lister en parallèle (4 connexions max) : un serveur injoignable ne doit
    # pas bloquer le démarrage du catalogue de tous les autres serveurs.
    resultat = []
    serveurs_actifs = serveurs[:NOMBRE_MAX_SERVEURS_PAR_COMPTE]
    if not serveurs_actifs:
        return resultat
    with ThreadPoolExecutor(max_workers=min(4, len(serveurs_actifs))) as pool:
        for outils in pool.map(charger_serveur, serveurs_actifs):
            resultat.extend(outils)
    return resultat


def outils_interface_pour_utilisateur(user_id: str) -> list[dict]:
    return [{cle: outil[cle] for cle in ("nom", "label", "icone", "onglet")} for outil in lister_outils_pour_utilisateur(user_id)]


def _get_metadata_oauth(url: str) -> dict:
    cible = valider_url_mcp(url)
    reponse = httpx.get(cible, timeout=8, follow_redirects=False, headers={"Accept": "application/json"})
    if reponse.status_code == 404:
        return {}
    reponse.raise_for_status()
    data = reponse.json()
    return data if isinstance(data, dict) else {}


def _metadata_resource(url: str) -> dict:
    p = urlparse(valider_url_mcp(url))
    origin = f"{p.scheme}://{p.netloc}"
    chemin = p.path.strip("/")
    candidats = []
    if chemin:
        candidats.append(f"{origin}/.well-known/oauth-protected-resource/{chemin}")
    candidats.append(f"{origin}/.well-known/oauth-protected-resource")
    for candidat in dict.fromkeys(candidats):
        try:
            data = _get_metadata_oauth(candidat)
            if data.get("authorization_servers"):
                return data
        except Exception:
            continue
    raise ValueError("Ce serveur ne publie pas de métadonnées OAuth Protected Resource compatibles.")


def _metadata_serveur_autorisation(issuer: str) -> dict:
    issuer = valider_url_mcp(issuer.rstrip("/"))
    p = urlparse(issuer)
    origin = f"{p.scheme}://{p.netloc}"
    prefixe = p.path.rstrip("/")
    candidats = [
        f"{origin}/.well-known/oauth-authorization-server{prefixe}",
        f"{origin}/.well-known/openid-configuration{prefixe}",
        f"{issuer}/.well-known/oauth-authorization-server",
        f"{issuer}/.well-known/openid-configuration",
    ]
    for candidat in dict.fromkeys(candidats):
        try:
            data = _get_metadata_oauth(candidat)
            if data.get("authorization_endpoint") and data.get("token_endpoint"):
                data["_issuer"] = issuer
                return data
        except Exception:
            continue
    raise ValueError("Le fournisseur OAuth du serveur MCP ne publie pas les métadonnées attendues.")


def _poster_json_securise(url: str, payload: dict) -> dict:
    cible = valider_url_mcp(url)
    reponse = httpx.post(cible, json=payload, timeout=10, follow_redirects=False, headers={"Accept": "application/json"})
    reponse.raise_for_status()
    data = reponse.json()
    if not isinstance(data, dict):
        raise ValueError("Réponse OAuth invalide.")
    return data


def demarrer_oauth(serveur_id: str, user_id: str) -> str:
    serveur = _serveur_pour_utilisateur(serveur_id, user_id)
    if serveur.get("auth_type") != "oauth":
        _erreur("MCP_OAUTH_NON_REQUIS", "Ce serveur n’utilise pas l’authentification OAuth.")
    if not URL_RETOUR:
        _erreur("OAUTH_NON_CONFIGURE", "La variable URL_RETOUR_APP n’est pas configurée côté backend.", 503)
    try:
        url_mcp = valider_url_mcp(serveur["url"])
        resource = _metadata_resource(url_mcp)
        issuers = resource.get("authorization_servers") or []
        if not issuers or not isinstance(issuers[0], str):
            raise ValueError("Aucun serveur d’autorisation OAuth n’est annoncé.")
        metadata = _metadata_serveur_autorisation(issuers[0])
        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise ValueError("Ce serveur OAuth n’accepte pas l’enregistrement dynamique. Si possible, choisis l’authentification Bearer.")
        methods = metadata.get("token_endpoint_auth_methods_supported") or []
        methode = "none" if not methods or "none" in methods else ("client_secret_post" if "client_secret_post" in methods else methods[0])
        client = _poster_json_securise(registration_endpoint, {
            "client_name": "Classinus",
            "redirect_uris": [URL_RETOUR],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": methode,
        })
        client_id = client.get("client_id")
        if not client_id:
            raise ValueError("Le fournisseur OAuth n’a pas renvoyé de client_id.")
        client_secret = client.get("client_secret")
        methode_retenue = client.get("token_endpoint_auth_method") or methode
        if client_secret and methode_retenue == "none":
            methode_retenue = "client_secret_post" if "client_secret_post" in methods else (
                "client_secret_basic" if "client_secret_basic" in methods else "client_secret_post"
            )
        verifier = secrets.token_urlsafe(64)
        challenge = __import__("base64").urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(32)
        resource_url = valider_url_mcp(resource.get("resource") or url_mcp)
        _SUPABASE.table("mcp_personnalises_oauth_temp").delete().lt(
            "created_at", (datetime.now(timezone.utc) - DUREE_ETAT_OAUTH).isoformat()
        ).execute()
        _SUPABASE.table("mcp_personnalises_oauth_temp").insert({
            "state": state, "server_id": serveur_id, "user_id": user_id, "server_url": url_mcp,
            "code_verifier": verifier, "client_id": client_id, "client_secret": client_secret,
            "token_endpoint": valider_url_mcp(metadata["token_endpoint"]),
            "issuer": metadata.get("_issuer") or metadata.get("issuer") or issuers[0],
            "resource_url": resource_url, "redirect_uri": URL_RETOUR, "token_auth_method": methode_retenue,
        }).execute()
        params = {
            "response_type": "code", "client_id": client_id, "redirect_uri": URL_RETOUR,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        }
        scopes = metadata.get("scopes_supported") or []
        if scopes:
            params["scope"] = " ".join(str(s) for s in scopes[:30])
        if resource_url:
            params["resource"] = resource_url
        endpoint = valider_url_mcp(metadata["authorization_endpoint"])
        return f"{endpoint}?{urlencode(params)}"
    except HTTPException:
        raise
    except Exception as exc:
        logging.warning("Démarrage OAuth d’un MCP personnalisé impossible (%s).", type(exc).__name__)
        _erreur("MCP_OAUTH_INDISPONIBLE", str(exc)[:300] or "La connexion OAuth n’a pas pu démarrer.", 400)


def etat_oauth_en_attente(state: str) -> bool:
    if not state:
        return False
    try:
        rows = (
            _SUPABASE.table("mcp_personnalises_oauth_temp").select("state").eq("state", state)
            .gte("created_at", (datetime.now(timezone.utc) - DUREE_ETAT_OAUTH).isoformat()).limit(1).execute().data or []
        )
        return bool(rows)
    except Exception as exc:
        logging.info("Lecture d’un état OAuth MCP personnel impossible (%s).", type(exc).__name__)
        return False


def finaliser_oauth(code: str, state: str) -> tuple[bool, str, str | None]:
    """Finalise OAuth via state à usage unique ; aucun jeton n'est renvoyé."""
    try:
        rows = (
            _SUPABASE.table("mcp_personnalises_oauth_temp").select("*").eq("state", state)
            .gte("created_at", (datetime.now(timezone.utc) - DUREE_ETAT_OAUTH).isoformat()).limit(1).execute().data or []
        )
        if not rows:
            return False, "Session OAuth MCP expirée ou déjà utilisée.", None
        pending = rows[0]
        _SUPABASE.table("mcp_personnalises_oauth_temp").delete().eq("state", state).execute()
        endpoint = valider_url_mcp(pending["token_endpoint"])
        method = pending.get("token_auth_method") or "none"
        payload = {
            "grant_type": "authorization_code", "code": code, "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["code_verifier"], "resource": pending["resource_url"],
        }
        auth = None
        if method == "client_secret_basic":
            auth = (pending["client_id"], pending.get("client_secret") or "")
        elif method == "none":
            payload["client_id"] = pending["client_id"]
        else:
            payload["client_id"] = pending["client_id"]
            if pending.get("client_secret"):
                payload["client_secret"] = pending["client_secret"]
        response = httpx.post(endpoint, data=payload, auth=auth, timeout=12, follow_redirects=False, headers={"Accept": "application/json"})
        response.raise_for_status()
        tokens = response.json()
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise ValueError("Le fournisseur OAuth n’a pas renvoyé de jeton d’accès.")
        expire = datetime.now(timezone.utc) + timedelta(seconds=max(60, int(tokens.get("expires_in", 3600))))
        _SUPABASE.table("mcp_personnalises_oauth_connections").upsert({
            "server_id": pending["server_id"], "user_id": pending["user_id"],
            "client_id": pending["client_id"], "client_secret": pending.get("client_secret"),
            "token_endpoint": pending["token_endpoint"], "token_auth_method": method,
            "resource_url": pending["resource_url"], "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"), "expires_at": expire.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="server_id").execute()
        _invalider_cache_serveur(pending["server_id"])
        return True, "Serveur MCP personnalisé connecté.", "mcp_personnalise"
    except Exception as exc:
        logging.warning("Finalisation OAuth d’un MCP personnalisé impossible (%s).", type(exc).__name__)
        return False, "La connexion OAuth à ce serveur MCP a échoué. Réessaie ou vérifie sa configuration.", "mcp_personnalise"


def obtenir_token_oauth(serveur_id: str, user_id: str) -> str | None:
    maintenant = datetime.now(timezone.utc)
    try:
        rows = (
            _SUPABASE.table("mcp_personnalises_oauth_connections").select("*")
            .eq("server_id", serveur_id).eq("user_id", user_id).limit(1).execute().data or []
        )
    except Exception as exc:
        logging.warning("Lecture du jeton OAuth MCP personnel impossible (%s).", type(exc).__name__)
        return None
    if not rows:
        return None
    ligne = rows[0]
    try:
        expire = datetime.fromisoformat(ligne["expires_at"].replace("Z", "+00:00"))
    except Exception:
        return None
    if maintenant + timedelta(minutes=5) >= expire:
        refresh = ligne.get("refresh_token")
        if not refresh:
            return None
        payload = {"grant_type": "refresh_token", "refresh_token": refresh, "resource": ligne["resource_url"]}
        auth = None
        method = ligne.get("token_auth_method") or "none"
        if method == "client_secret_basic":
            auth = (ligne["client_id"], ligne.get("client_secret") or "")
        else:
            payload["client_id"] = ligne["client_id"]
            if method != "none" and ligne.get("client_secret"):
                payload["client_secret"] = ligne["client_secret"]
        try:
            endpoint = valider_url_mcp(ligne["token_endpoint"])
            response = httpx.post(endpoint, data=payload, auth=auth, timeout=12, follow_redirects=False, headers={"Accept": "application/json"})
            response.raise_for_status()
            tokens = response.json()
            if not isinstance(tokens, dict) or not tokens.get("access_token"):
                return None
            expire = maintenant + timedelta(seconds=max(60, int(tokens.get("expires_in", 3600))))
            _SUPABASE.table("mcp_personnalises_oauth_connections").update({
                "access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", refresh),
                "expires_at": expire.isoformat(), "updated_at": maintenant.isoformat(),
            }).eq("server_id", serveur_id).eq("user_id", user_id).execute()
            ligne["access_token"] = tokens["access_token"]
            _invalider_cache_serveur(serveur_id)
        except Exception as exc:
            logging.warning("Rafraîchissement OAuth MCP personnel impossible (%s).", type(exc).__name__)
            return None
    return ligne.get("access_token")


def _config_publique(ligne: dict, user_id: str) -> dict:
    connecte = False
    if ligne.get("auth_type") in ("none", "bearer"):
        connecte = bool(ligne.get("actif"))
    elif ligne.get("auth_type") == "oauth":
        connecte = bool(obtenir_token_oauth(ligne["id"], user_id))
    return {
        "id": ligne["id"], "nom": ligne["nom"], "url": ligne["url"],
        "auth_type": ligne["auth_type"], "actif": bool(ligne.get("actif", True)),
        "connecte": connecte, "created_at": ligne.get("created_at"), "updated_at": ligne.get("updated_at"),
    }


@router.get("")
def lister_serveurs(utilisateur=Depends(utilisateur_courant)):
    try:
        lignes = (
            _SUPABASE.table("mcp_personnalises").select("id,nom,url,auth_type,actif,created_at,updated_at")
            .eq("user_id", utilisateur.id).order("created_at", desc=False).execute().data or []
        )
        return {"serveurs": [_config_publique(ligne, utilisateur.id) for ligne in lignes]}
    except Exception as exc:
        logging.error("Liste des MCP personnalisés indisponible (%s).", type(exc).__name__)
        _erreur("MCP_LISTE_INDISPONIBLE", "Impossible de charger les serveurs MCP pour le moment.", 503)


@router.post("")
def ajouter_serveur(payload: ServeurPayload, utilisateur=Depends(utilisateur_courant)):
    nom = payload.nom.strip()
    if not nom:
        _erreur("MCP_NOM_INVALIDE", "Saisis un nom pour ce serveur.")
    try:
        url = valider_url_mcp(payload.url)
    except ValueError as exc:
        _erreur("MCP_URL_INVALIDE", str(exc))
    token = (payload.token or "").strip()
    if payload.auth_type == "bearer" and not token:
        _erreur("MCP_JETON_REQUIS", "Un jeton Bearer est nécessaire pour ce mode d’authentification.")
    if payload.auth_type != "bearer":
        token = None
    try:
        courant = _SUPABASE.table("mcp_personnalises").select("id").eq("user_id", utilisateur.id).execute().data or []
        if len(courant) >= NOMBRE_MAX_SERVEURS_PAR_COMPTE:
            _erreur("MCP_LIMITE_ATTEINTE", f"Tu peux enregistrer au maximum {NOMBRE_MAX_SERVEURS_PAR_COMPTE} serveurs MCP.")
        if payload.auth_type != "oauth":
            _lister_outils_reseau(url, {"Authorization": f"Bearer {token}"} if token else {})
        lignes = _SUPABASE.table("mcp_personnalises").insert({
            "user_id": utilisateur.id, "nom": nom, "url": url, "auth_type": payload.auth_type,
            "bearer_token": token, "actif": True, "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute().data or []
        if not lignes:
            _erreur("MCP_ENREGISTREMENT_ECHOUE", "Le serveur MCP n’a pas pu être enregistré.", 503)
        return {"serveur": _config_publique(lignes[0], utilisateur.id)}
    except HTTPException:
        raise
    except ValueError as exc:
        _erreur("MCP_INACCESSIBLE", str(exc))
    except Exception as exc:
        logging.error("Ajout d’un MCP personnalisé impossible (%s).", type(exc).__name__)
        _erreur("MCP_ENREGISTREMENT_ECHOUE", "Le serveur MCP n’a pas pu être enregistré.", 503)


@router.patch("/{serveur_id}")
def modifier_serveur(serveur_id: str, payload: ServeurPayload, utilisateur=Depends(utilisateur_courant)):
    precedent = _serveur_pour_utilisateur(serveur_id, utilisateur.id)
    try:
        url = valider_url_mcp(payload.url)
    except ValueError as exc:
        _erreur("MCP_URL_INVALIDE", str(exc))
    nom = payload.nom.strip()
    if not nom:
        _erreur("MCP_NOM_INVALIDE", "Saisis un nom pour ce serveur.")
    token = (payload.token or "").strip()
    if payload.auth_type == "bearer":
        if not token:
            token = precedent.get("bearer_token") if precedent.get("auth_type") == "bearer" else None
        if not token:
            _erreur("MCP_JETON_REQUIS", "Saisis un jeton Bearer pour ce serveur.")
    else:
        token = None
    if payload.auth_type != "oauth":
        try:
            _lister_outils_reseau(url, {"Authorization": f"Bearer {token}"} if token else {})
        except ValueError as exc:
            _erreur("MCP_INACCESSIBLE", str(exc))
    try:
        _SUPABASE.table("mcp_personnalises").update({
            "nom": nom, "url": url, "auth_type": payload.auth_type, "bearer_token": token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", serveur_id).eq("user_id", utilisateur.id).execute()
        if url != precedent.get("url") or payload.auth_type != precedent.get("auth_type"):
            _SUPABASE.table("mcp_personnalises_oauth_connections").delete().eq("server_id", serveur_id).eq("user_id", utilisateur.id).execute()
        _invalider_cache_serveur(serveur_id)
        mis_a_jour = _serveur_pour_utilisateur(serveur_id, utilisateur.id)
        return {"serveur": _config_publique(mis_a_jour, utilisateur.id)}
    except HTTPException:
        raise
    except Exception as exc:
        logging.error("Modification d’un MCP personnalisé impossible (%s).", type(exc).__name__)
        _erreur("MCP_MODIFICATION_ECHOUEE", "La modification du serveur MCP a échoué.", 503)


@router.post("/{serveur_id}/actif")
def definir_actif(serveur_id: str, payload: ActifPayload, utilisateur=Depends(utilisateur_courant)):
    _serveur_pour_utilisateur(serveur_id, utilisateur.id)
    try:
        _SUPABASE.table("mcp_personnalises").update({
            "actif": payload.actif, "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", serveur_id).eq("user_id", utilisateur.id).execute()
        _invalider_cache_serveur(serveur_id)
        return {"actif": payload.actif}
    except Exception as exc:
        logging.error("Modification de l’état d’un MCP impossible (%s).", type(exc).__name__)
        _erreur("MCP_MODIFICATION_ECHOUEE", "L’état du serveur MCP n’a pas pu être modifié.", 503)


@router.post("/{serveur_id}/deconnecter")
def deconnecter_oauth(serveur_id: str, utilisateur=Depends(utilisateur_courant)):
    serveur = _serveur_pour_utilisateur(serveur_id, utilisateur.id)
    if serveur.get("auth_type") != "oauth":
        _erreur("MCP_OAUTH_NON_REQUIS", "Ce serveur n’utilise pas OAuth.")
    _SUPABASE.table("mcp_personnalises_oauth_connections").delete().eq("server_id", serveur_id).eq("user_id", utilisateur.id).execute()
    _invalider_cache_serveur(serveur_id)
    return {"connecte": False}


@router.delete("/{serveur_id}")
def supprimer_serveur(serveur_id: str, utilisateur=Depends(utilisateur_courant)):
    _serveur_pour_utilisateur(serveur_id, utilisateur.id)
    try:
        _SUPABASE.table("mcp_personnalises").delete().eq("id", serveur_id).eq("user_id", utilisateur.id).execute()
        _invalider_cache_serveur(serveur_id)
        return {"supprime": True}
    except Exception as exc:
        logging.error("Suppression d’un MCP personnalisé impossible (%s).", type(exc).__name__)
        _erreur("MCP_SUPPRESSION_ECHOUEE", "Le serveur MCP n’a pas pu être supprimé.", 503)


@router.post("/{serveur_id}/tester")
def tester_serveur(serveur_id: str, utilisateur=Depends(utilisateur_courant)):
    serveur = _serveur_pour_utilisateur(serveur_id, utilisateur.id)
    headers = _headers_serveur(serveur, utilisateur.id)
    if headers is None:
        _erreur("MCP_NON_CONNECTE", "Connecte ce serveur MCP avant de tester ses outils.")
    try:
        outils = _lister_outils_reseau(serveur["url"], headers)
        return {"connecte": True, "nombre_outils": len(outils), "outils": [
            {"nom": str(getattr(o, "name", "")), "description": str(getattr(o, "description", "") or "")[:500]}
            for o in outils[:TAILLE_MAX_OUTILS_PAR_SERVEUR]
        ]}
    except ValueError as exc:
        _erreur("MCP_TEST_ECHOUE", str(exc), 502)


@router.post("/{serveur_id}/demarrer-oauth")
def demarrer_connexion_oauth(serveur_id: str, utilisateur=Depends(utilisateur_courant)):
    return {"url": demarrer_oauth(serveur_id, utilisateur.id)}


@router.get("/outils-interface")
def lister_outils_interface(utilisateur=Depends(utilisateur_courant)):
    return {"outils": outils_interface_pour_utilisateur(utilisateur.id)}
