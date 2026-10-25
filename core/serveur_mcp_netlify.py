"""Serveur MCP interne pour Netlify, adossé à l'API REST officielle.

Le jeton est choisi côté serveur à partir du user_id de la requête interne,
jamais depuis un argument fourni par le modèle.
"""
import json
import logging
import os
import hmac
import requests
from mcp.server.mcpserver import MCPServer as FastMCP, Context
from connexions.netlify_mcp import obtenir_token_valide

mcp_netlify = FastMCP(name="netlify")
API = "https://api.netlify.com/api/v1"

def _user_id(ctx: Context) -> str:
    try:
        # This mounted MCP endpoint is reachable over HTTP. Never trust user_id
        # on its own: require a secret header emitted only by the backend registry.
        provided = ctx.request_context.request.headers.get("x-classinus-mcp-internal", "")
        expected = os.environ.get("SUPABASE_SECRET", "")
        if not expected or not hmac.compare_digest(provided, expected):
            return ""
        user_id = ctx.request_context.request.query_params.get("user_id", "")
        return user_id if user_id and user_id not in ("None", "null") else ""
    except Exception:
        return ""

def _api(ctx: Context, methode: str, chemin: str, params=None, body=None):
    user_id = _user_id(ctx)
    token = obtenir_token_valide(user_id)
    if not token:
        return {"erreur": "Compte Netlify non connecté. Connecte Netlify dans Personnaliser > Applications connectées."}
    try:
        response = requests.request(
            methode, API + chemin,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params, json=body, timeout=25,
        )
        if response.status_code in (401, 403):
            return {"erreur": "Le jeton Netlify a été révoqué ou n'a plus les permissions nécessaires. Déconnecte puis reconnecte Netlify."}
        response.raise_for_status()
        if not response.content:
            return {"ok": True}
        return response.json()
    except requests.RequestException as exc:
        logging.warning("Appel API Netlify échoué: %s", type(exc).__name__)
        return {"erreur": "L'API Netlify est indisponible ou a refusé la requête. Réessaie plus tard."}
    except ValueError:
        return {"erreur": "Netlify a renvoyé une réponse JSON invalide."}

def _resume_site(site):
    if not isinstance(site, dict):
        return site
    clefs = ("id", "name", "url", "ssl_url", "custom_domain", "state", "created_at", "updated_at", "admin_url", "build_settings")
    return {k: site.get(k) for k in clefs if k in site}

def _resume_deploiement(deploiement):
    if not isinstance(deploiement, dict):
        return deploiement
    clefs = ("id", "state", "name", "url", "ssl_url", "deploy_url", "created_at", "updated_at", "branch", "commit_ref", "commit_url", "error_message", "published_at")
    return {k: deploiement.get(k) for k in clefs if k in deploiement}

@mcp_netlify.tool()
def lister_sites(limite: int = 20, ctx: Context = None) -> str:
    """Liste les sites Netlify accessibles au compte connecté. Limite 1 à 100."""
    limite = max(1, min(int(limite), 100))
    data = _api(ctx, "GET", "/sites", params={"per_page": limite})
    if isinstance(data, dict) and data.get("erreur"):
        return data["erreur"]
    sites = data if isinstance(data, list) else data.get("sites", []) if isinstance(data, dict) else []
    return json.dumps([_resume_site(site) for site in sites], ensure_ascii=False)

@mcp_netlify.tool()
def consulter_site(site_id: str, ctx: Context = None) -> str:
    """Consulte les informations d'un site Netlify par son identifiant."""
    if not site_id.strip():
        return "Indique l'identifiant du site Netlify."
    data = _api(ctx, "GET", f"/sites/{site_id.strip()}")
    if isinstance(data, dict) and data.get("erreur"):
        return data["erreur"]
    return json.dumps(_resume_site(data), ensure_ascii=False)

@mcp_netlify.tool()
def lister_deploiements(site_id: str, limite: int = 10, ctx: Context = None) -> str:
    """Liste les déploiements récents d'un site Netlify."""
    if not site_id.strip():
        return "Indique l'identifiant du site Netlify."
    limite = max(1, min(int(limite), 100))
    data = _api(ctx, "GET", f"/sites/{site_id.strip()}/deploys", params={"per_page": limite})
    if isinstance(data, dict) and data.get("erreur"):
        return data["erreur"]
    deploys = data if isinstance(data, list) else data.get("deploys", []) if isinstance(data, dict) else []
    return json.dumps([_resume_deploiement(item) for item in deploys], ensure_ascii=False)

@mcp_netlify.tool()
def consulter_deploiement(deploiement_id: str, ctx: Context = None) -> str:
    """Consulte le statut et les métadonnées d'un déploiement Netlify."""
    if not deploiement_id.strip():
        return "Indique l'identifiant du déploiement."
    data = _api(ctx, "GET", f"/deploys/{deploiement_id.strip()}")
    if isinstance(data, dict) and data.get("erreur"):
        return data["erreur"]
    return json.dumps(_resume_deploiement(data), ensure_ascii=False)

@mcp_netlify.tool()
def relancer_deploiement(site_id: str, vider_cache: bool = False, ctx: Context = None) -> str:
    """Déclenche un nouveau build pour un site Netlify. Cette action modifie l'état du site et nécessite une confirmation explicite."""
    if not site_id.strip():
        return "Indique l'identifiant du site Netlify."
    data = _api(ctx, "POST", f"/sites/{site_id.strip()}/builds", body={"clear_cache": bool(vider_cache)})
    return json.dumps(data, ensure_ascii=False)
