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

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from connexions.oauth_generique import (
    SERVICES,
    URL_RETOUR,
    demarrer_connexion,
    est_connecte,
    etat_en_attente,
    finaliser_connexion,
    get_secret,
)
import connexions.notion as notion

router = APIRouter(prefix="/api/connexions", tags=["connexions"])


@router.get("/{service}/statut")
def statut_connexion(service: str, utilisateur=Depends(utilisateur_courant)):
    if service == "notion":
        return {"connecte": notion.est_connecte(utilisateur.id)}
    if service not in SERVICES:
        raise erreur_api(404, "SERVICE_INCONNU", service=service)
    return {"connecte": est_connecte(service, utilisateur.id)}


@router.get("/diagnostic/{service}")
def diagnostic_config(service: str):
    """
    Dit si la configuration attendue est visible par le serveur qui tourne
    réellement, sans jamais renvoyer de secret : seulement des présent/absent.
    URL_RETOUR_APP n'est pas un secret (adresse publique de retour), elle est
    renvoyée en clair pour repérer une faute de frappe ou un mauvais domaine.
    """
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


class FinaliserPayload(BaseModel):
    code: str
    state: str


@router.post("/finaliser")
def finaliser(payload: FinaliserPayload):
    # Pas de connexion requise ici : la page de retour appelle cette route
    # juste après la redirection du fournisseur. Le `state` (opaque, généré
    # par le serveur, à usage unique) sert de preuve d'origine.
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
