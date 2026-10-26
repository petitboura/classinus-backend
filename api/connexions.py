"""
Routes de connexion aux applications externes (Notion, Google Drive, et tout
service futur ajouté dans connexions/oauth_generique.py).

Flux vu du site :
1. GET /api/connexions/{service}/statut : dit si la personne est déjà
   connectée (bouton "Connecter" ou point vert).
2. GET /api/connexions/{service}/demarrer : renvoie l'adresse du fournisseur
   où envoyer la personne pour qu'elle accepte l'accès.
3. Le fournisseur renvoie la personne sur URL_RETOUR_APP, une page du site
   (/oauth/retour) avec ?code=...&state=... dans l'adresse.
4. Cette page appelle POST /api/connexions/finaliser {code, state}. Le service
   n'est pas à préciser : il est retrouvé grâce à `state`, car l'adresse de
   retour est partagée entre tous les services.

Notion suit son propre moteur (connexions/notion.py : enregistrement
dynamique du client, tables dédiées). Chaque route ci-dessous aiguille donc
vers Notion quand service vaut "notion", sinon vers le moteur générique. Le
site appelle les mêmes adresses dans les deux cas.

Les routes propres à Notion (recherche de pages, lignes d'une base, création
d'une page) sont dans api/connexions_notion.py, pour ne pas faire grossir ce
fichier.
"""

import logging
import os
import sys

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from connexions.oauth_generique import (
    SERVICES,
    URL_RETOUR,
    demarrer_connexion,
    est_connecte,
    deconnecter as deconnecter_oauth_generique,
    a_reconnecter as a_reconnecter_oauth_generique,
    obtenir_token_valide as obtenir_token_valide_generique,
    etat_en_attente,
    finaliser_connexion,
    get_secret,
)
import connexions.notion as notion
import connexions.higgsfield_mcp as higgsfield_mcp
import connexions.netlify_mcp as netlify_mcp
import connexions.render_mcp as render_mcp
import connexions.platform_mcp_oauth as platform_mcp_oauth
import connexions.mcp_personnalises as mcp_personnalises

# core/ est sur le chemin des imports comme dans api/agents.py : le module doit être chargé sous le
# MÊME nom que dans la boucle de l'IA, sinon deux copies et deux caches (l'invalidation ne servirait à rien).
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
import etat_connexions  # noqa: E402

router = APIRouter(prefix="/api/connexions", tags=["connexions"])


@router.get("/{service}/statut")
def statut_connexion(service: str, utilisateur=Depends(utilisateur_courant)):
    # Même lecture que celle de l'IA (core/etat_connexions.py) : une seule source de vérité.
    statut = etat_connexions.etat_service(service, utilisateur.id)
    if statut is None:
        raise erreur_api(404, "SERVICE_INCONNU", service=service)
    return statut


@router.post("/{service}/deconnecter")
def deconnecter_plateforme_mcp(service: str, utilisateur=Depends(utilisateur_courant)):
    """Supprime uniquement la connexion personnelle au service demandé."""
    try:
        return _deconnecter(service, utilisateur)
    finally:
        # L'IA doit voir le changement tout de suite (voir core/etat_connexions.py).
        etat_connexions.invalider_etats(utilisateur.id)


def _deconnecter(service: str, utilisateur):
    if service == "netlify_mcp":
        netlify_mcp.deconnecter(utilisateur.id)
        return {"connecte": False}
    if service == "render_mcp":
        render_mcp.deconnecter(utilisateur.id)
        return {"connecte": False}
    if service == "higgsfield_mcp":
        higgsfield_mcp.deconnecter(utilisateur.id)
        return {"connecte": False}
    if service in platform_mcp_oauth.FOURNISSEURS:
        platform_mcp_oauth.deconnecter(service, utilisateur.id)
        return {"connecte": False}
    if service in SERVICES:
        deconnecter_oauth_generique(service, utilisateur.id)
        return {"connecte": False}
    raise erreur_api(404, "SERVICE_INCONNU", service=service)


@router.get("/diagnostic/{service}")
def diagnostic_config(service: str):
    """
    Dit si la configuration attendue est visible par le serveur qui tourne
    réellement, sans jamais renvoyer de secret : seulement des présent/absent.
    URL_RETOUR_APP n'est pas un secret (adresse publique de retour), elle est
    renvoyée en clair pour repérer une faute de frappe ou un mauvais domaine.
    """
    if service == "higgsfield_mcp":
        return {"url_retour_app": URL_RETOUR, "oauth_dynamique": True}
    if service in platform_mcp_oauth.FOURNISSEURS:
        config = platform_mcp_oauth.FOURNISSEURS[service]
        if service == "microsoft_mcp":
            return {
                "url_retour_app": URL_RETOUR,
                "client_id_present": bool(get_secret("MICROSOFT_MCP_CLIENT_ID")),
                "client_secret_present": bool(get_secret("MICROSOFT_MCP_CLIENT_SECRET")),
                "oauth_dynamique": False,
                "serveur_mcp": config["mcp_url"],
            }
        if service == "railway_mcp":
            return {
                "url_retour_app": URL_RETOUR,
                "client_id_present": bool(get_secret("RAILWAY_OAUTH_CLIENT_ID")),
                "client_secret_present": bool(get_secret("RAILWAY_OAUTH_CLIENT_SECRET")),
                "oauth_dynamique": False,
            }
        return {"url_retour_app": URL_RETOUR, "oauth_dynamique": True, "serveur_mcp": config["mcp_url"]}
    if service == "notion":
        return {"url_retour_app": notion.URL_RETOUR}

    config = SERVICES.get(service)
    if not config:
        raise erreur_api(404, "SERVICE_INCONNU", service=service)

    return {
        "client_id_present": bool(get_secret(config["client_id_env"])),
        "client_secret_present": bool(get_secret(config.get("client_secret_env", ""))),
        "url_retour_app": URL_RETOUR,
    }


@router.get("/{service}/demarrer")
def demarrer(service: str, agent_id: str = "", utilisateur=Depends(utilisateur_courant)):
    # On vérifie nous-mêmes chaque pièce de configuration avant de démarrer,
    # pour renvoyer une erreur précise plutôt qu'un échec muet.
    if service == "higgsfield_mcp":
        url = higgsfield_mcp.demarrer_connexion(utilisateur.id, agent_id or None)
        if not url:
            raise erreur_api(503, "CONNEXION_INDISPONIBLE", message="Connexion Higgsfield indisponible : vérifie les métadonnées OAuth du fournisseur et URL_RETOUR_APP.")
        return {"url": url}
    if service in platform_mcp_oauth.FOURNISSEURS:
        url = platform_mcp_oauth.demarrer_connexion(service, utilisateur.id, agent_id or None)
        if not url:
            if service == "railway_mcp":
                message = "Connexion Railway indisponible : configure RAILWAY_OAUTH_CLIENT_ID et RAILWAY_OAUTH_CLIENT_SECRET dans Railway, ainsi que URL_RETOUR_APP."
            elif service == "microsoft_mcp":
                message = "Connexion Microsoft MCP indisponible : configure MICROSOFT_MCP_CLIENT_ID et MICROSOFT_MCP_CLIENT_SECRET, l’URI de retour OAuth, puis les permissions MCP côté Microsoft Entra. Le serveur est en préversion et limité aux lectures d’annuaire."
            else:
                message = f"Connexion {service} indisponible : le serveur MCP n'a pas fourni de métadonnées OAuth compatibles ou URL_RETOUR_APP est absent."
            raise erreur_api(503, "CONNEXION_INDISPONIBLE", message=message)
        return {"url": url}

    if service == "notion":
        if not notion.URL_RETOUR:
            raise erreur_api(
                503,
                "CONNEXION_INDISPONIBLE",
                message="Connexion notion indisponible : URL_RETOUR_APP absent(e) du serveur actuellement déployé.",
            )
        url = notion.demarrer_connexion_notion(utilisateur.id, agent_id or None)
        if not url:
            raise erreur_api(500, "CONNEXION_INDISPONIBLE", service=service)
        return {"url": url}

    config = SERVICES.get(service)
    if not config:
        raise erreur_api(404, "SERVICE_INCONNU", service=service)

    manques = []
    if not get_secret(config["client_id_env"]):
        manques.append(config["client_id_env"])
    if not URL_RETOUR:
        manques.append("URL_RETOUR_APP")
    if manques:
        raise erreur_api(
            503,
            "CONNEXION_INDISPONIBLE",
            message=(
                f"Connexion {service} indisponible : {', '.join(manques)} absent(e) du serveur "
                "actuellement déployé (vérifie que ces variables sont sur le bon service Railway "
                "et qu'un redéploiement a eu lieu après leur ajout)."
            ),
        )

    url = demarrer_connexion(service, utilisateur.id, agent_id or None)
    if not url:
        raise erreur_api(500, "CONNEXION_INDISPONIBLE", service=service)
    return {"url": url}


class JetonNetlifyPayload(BaseModel):
    token: str


@router.post("/netlify_mcp/jeton")
def enregistrer_jeton_netlify(payload: JetonNetlifyPayload, utilisateur=Depends(utilisateur_courant)):
    try:
        return _enregistrer_jeton_netlify(payload, utilisateur)
    finally:
        etat_connexions.invalider_etats(utilisateur.id)


def _enregistrer_jeton_netlify(payload, utilisateur):
    try:
        netlify_mcp.enregistrer_token(utilisateur.id, payload.token)
    except ValueError as exc:
        raise erreur_api(400, "JETON_NETLIFY_INVALIDE", message=str(exc))
    except RuntimeError as exc:
        raise erreur_api(502, "CONNEXION_NETLIFY_INDISPONIBLE", message=str(exc))
    except Exception:
        logging.exception("Enregistrement du jeton Netlify échoué")
        raise erreur_api(500, "ERREUR_CONNEXION_NETLIFY", message="Classinus n'a pas pu enregistrer le jeton Netlify.")
    return {"connecte": True}


class JetonRenderPayload(BaseModel):
    token: str


@router.post("/render_mcp/jeton")
def enregistrer_jeton_render(payload: JetonRenderPayload, utilisateur=Depends(utilisateur_courant)):
    try:
        return _enregistrer_jeton_render(payload, utilisateur)
    finally:
        etat_connexions.invalider_etats(utilisateur.id)


def _enregistrer_jeton_render(payload, utilisateur):
    try:
        render_mcp.enregistrer_token(utilisateur.id, payload.token)
    except ValueError as exc:
        raise erreur_api(400, "JETON_RENDER_INVALIDE", message=str(exc))
    except RuntimeError as exc:
        raise erreur_api(502, "CONNEXION_RENDER_INDISPONIBLE", message=str(exc))
    except Exception:
        logging.exception("Enregistrement de la clé Render échoué")
        raise erreur_api(500, "ERREUR_CONNEXION_RENDER", message="Classinus n'a pas pu enregistrer la clé Render.")
    return {"connecte": True}


class FinaliserPayload(BaseModel):
    code: str
    state: str


@router.post("/finaliser")
def finaliser(payload: FinaliserPayload):
    try:
        return _finaliser(payload)
    finally:
        # Aucune session ici : on vide l'état de tous, il sera relu au prochain message.
        etat_connexions.invalider_etats()


def _finaliser(payload: FinaliserPayload):
    # MCP personnel : state opaque à usage unique, rattaché au serveur et au compte.
    if mcp_personnalises.etat_oauth_en_attente(payload.state):
        succes, message, service = mcp_personnalises.finaliser_oauth(payload.code, payload.state)
        return {"succes": succes, "message": message, "service": service}

    # Pas de connexion requise ici : la page de retour appelle cette route
    # juste après la redirection du fournisseur. Le `state` (opaque, généré
    # par le serveur, à usage unique) sert de preuve d'origine.
    if higgsfield_mcp.etat_en_attente(payload.state):
        succes, message = higgsfield_mcp.finaliser_connexion(payload.code, payload.state)
        return {"succes": succes, "message": message, "service": "higgsfield_mcp"}

    service_platform = platform_mcp_oauth.etat_en_attente(payload.state)
    if service_platform:
        succes, message = platform_mcp_oauth.finaliser_connexion(service_platform, payload.code, payload.state)
        return {"succes": succes, "message": message, "service": service_platform}

    service = etat_en_attente(payload.state)
    if service:
        succes, message = finaliser_connexion(service, payload.code, payload.state)
        return {"succes": succes, "message": message, "service": service}

    # Absent de la table générique : on tente celle de Notion, même adresse
    # de retour partagée entre les deux moteurs.
    if notion.etat_notion_en_attente(payload.state):
        succes, message = notion.finaliser_connexion_notion(payload.code, payload.state)
        return {"succes": succes, "message": message, "service": "notion"}

    return {"succes": False, "message": "Session de connexion expirée ou déjà utilisée.", "service": None}
