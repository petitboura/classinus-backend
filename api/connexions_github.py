"""
Route propre à GitHub, pour le sélecteur de dépôts du bouton Applications :
liste les dépôts (publics et privés) de la personne connectée.

Le site appelle GET /api/connexions/github/depots (voir depotsGithub dans
lib/api.ts du frontend). Cette route manquait côté serveur : le bouton
recevait donc une erreur et affichait une liste vide.

Le jeton utilisé est toujours celui de la personne connectée, jamais une clé
partagée de la plateforme, pour que les dépôts privés restent les siens.
"""

import logging

import requests
from fastapi import APIRouter, Depends

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from connexions.oauth_generique import obtenir_token_valide

URL_DEPOTS = "https://api.github.com/user/repos"
DELAI_SECONDES = 10
NOMBRE_MAX_DEPOTS = 100

router = APIRouter(prefix="/api/connexions/github", tags=["connexions-github"])


@router.get("/depots")
def depots_github(utilisateur=Depends(utilisateur_courant)):
    token = obtenir_token_valide("github", utilisateur.id)
    if not token:
        raise erreur_api(400, "GITHUB_NON_CONNECTE")

    entetes = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        reponse = requests.get(
            URL_DEPOTS,
            headers=entetes,
            params={"sort": "updated", "per_page": NOMBRE_MAX_DEPOTS},
            timeout=DELAI_SECONDES,
        )
    except Exception as e:
        logging.error(f"ERREUR DEPOTS GITHUB (appel impossible) : {e}")
        raise erreur_api(502, "GITHUB_DEPOTS_INDISPONIBLE")

    if reponse.status_code == 401:
        # Jeton refusé par GitHub : la personne doit reconnecter son compte.
        logging.error("ERREUR DEPOTS GITHUB : jeton refusé par GitHub (401)")
        raise erreur_api(400, "GITHUB_NON_CONNECTE")
    if reponse.status_code != 200:
        try:
            detail = (reponse.json().get("message") or "")[:200]
        except Exception:
            detail = ""
        logging.error(f"ERREUR DEPOTS GITHUB : statut {reponse.status_code} ({detail})")
        raise erreur_api(502, "GITHUB_DEPOTS_INDISPONIBLE")

    return {
        "depots": [
            {
                "nom_complet": d.get("full_name"),
                "prive": bool(d.get("private")),
                "description": d.get("description"),
                "url": d.get("html_url"),
            }
            for d in reponse.json()
            if d.get("full_name")
        ]
    }
