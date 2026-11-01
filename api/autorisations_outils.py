"""
Écran Applications connectées : actions que la personne a autorisées pour de bon
avec le bouton "Toujours autoriser" (31/10/2026).

Deux routes :
- GET /api/autorisations-outils : la liste, pour afficher les actions de chaque application.
- DELETE /api/autorisations-outils?cle=... : retire une autorisation, la confirmation
  est de nouveau demandée la prochaine fois.

L'ajout se fait au moment du clic sur "Toujours autoriser" (core/main.py), pas ici.
"""

import logging

from fastapi import APIRouter, Depends, Query, Request

from api.auth import utilisateur_courant
from api.journal import journaliser
from core.erreurs import erreur_api
from core.autorisations_outils import lister_autorisations, retirer_autorisation, LONGUEUR_MAX_CLE

router = APIRouter(prefix="/api/autorisations-outils", tags=["autorisations_outils"])


@router.get("")
def lister(utilisateur=Depends(utilisateur_courant)):
    try:
        return {"autorisations": lister_autorisations(utilisateur.id)}
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture autorisations_outils_permanentes user={utilisateur.id}) : {e}")
        raise erreur_api(500, "AUTORISATIONS_OUTILS_LECTURE_ECHEC")


@router.delete("", status_code=204)
def retirer(request: Request, cle: str = Query(min_length=1, max_length=LONGUEUR_MAX_CLE), utilisateur=Depends(utilisateur_courant)):
    try:
        retirer_autorisation(utilisateur.id, cle)
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (retrait autorisations_outils_permanentes user={utilisateur.id} cle={cle}) : {e}")
        raise erreur_api(500, "AUTORISATIONS_OUTILS_RETRAIT_ECHEC")
    journaliser(
        action="outils.autorisation_permanente_retiree",
        user_id=utilisateur.id,
        cible_type="profile",
        cible_id=utilisateur.id,
        details={"cle": cle},
        request=request,
    )
