"""
Logo d'un site pour l'affichage (29/10/2026, demande de Bourama).
Toute la logique est dans core/logos_sites.py.

Route : GET /api/logos-sites/{domaine}
- 200 avec l'image : Google a une vraie icône pour ce site ;
- 404 sans image : pas d'icône, l'écran affiche la lettre de secours.

Sans authentification, comme /api/outils/registre : l'écran la charge dans une simple
balise image, qui ne peut pas joindre de jeton, et la réponse ne contient rien de
personnel. La limite de débit protège le serveur contre quelqu'un qui testerait des
milliers de noms de sites.
"""

import os

from fastapi import APIRouter, Request, Response

from core.limitation_debit import limiteur
from core.logos_sites import TROUVE, duree_cache_navigateur, logo_du_site

router = APIRouter(tags=["logos"])

# Une page du chat peut afficher beaucoup de logos d'un coup : la limite est large.
_LIMITE = os.environ.get("LOGOS_SITES_LIMITE") or "600/minute"


@router.get("/api/logos-sites/{domaine}")
@limiteur.limit(_LIMITE)
def logo_d_un_site(request: Request, domaine: str):
    statut, octets, type_contenu, _nom = logo_du_site(domaine)
    entetes = {"Cache-Control": f"public, max-age={duree_cache_navigateur(statut)}"}
    if statut == TROUVE:
        return Response(content=octets, media_type=type_contenu, headers=entetes)
    return Response(status_code=404, headers=entetes)
