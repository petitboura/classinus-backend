"""
Routes admin du deblocage d'un modele pour tout le monde ou pour une liste d'adresses (26/11/2026,
demande de Bourama). Toute la logique vit dans core/deblocage_modeles.py ; ces routes sont reservees aux
comptes profiles.role = 'admin'. Un deblocage ou une revocation prend effet en moins d'une minute (cache de
la configuration des modeles).
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth import utilisateur_courant
from api.permissions_hierarchie import _est_admin
from core import deblocage_modeles
from core.deblocage_paliers import ErreurDeblocage
from core.erreurs import erreur_api
from core.limitation_debit import limiteur

router_deblocage_modeles = APIRouter(prefix="/api/admin/deblocages-modeles", tags=["deblocages-modeles"])


def _exige_admin(utilisateur):
    if not _est_admin(utilisateur.id):
        raise erreur_api(403, "PAS_LE_DROIT_ADMIN")


class DebloquerModelePayload(BaseModel):
    modele_id: str
    # Exactement une cible : tout le monde (tous = true) OU une liste d'adresses e-mail.
    tous: bool = False
    adresses: Optional[List[str]] = None
    # Facultatif : sans date de fin, le deblocage dure jusqu'a sa revocation. Sans fuseau, la date est lue en UTC.
    expire_le: Optional[datetime] = None
    motif: Optional[str] = None


class RevoquerModelePayload(BaseModel):
    modele_id: str
    tous: bool = False
    adresses: Optional[List[str]] = None


@router_deblocage_modeles.get("")
@limiteur.limit("60/minute")
def lire_deblocages_modeles(request: Request, modele_id: Optional[str] = None, utilisateur=Depends(utilisateur_courant)):
    """Les deblocages actifs, regroupes par modele (un seul modele si modele_id est donne)."""
    _exige_admin(utilisateur)
    try:
        return deblocage_modeles.lister(modele_id)
    except ErreurDeblocage as e:
        raise erreur_api(e.statut_http, e.code)


@router_deblocage_modeles.post("")
@limiteur.limit("30/minute")
def debloquer_un_modele(request: Request, payload: DebloquerModelePayload, utilisateur=Depends(utilisateur_courant)):
    """Debloque un modele pour tout le monde ou pour une liste d'adresses."""
    _exige_admin(utilisateur)
    try:
        return deblocage_modeles.debloquer_modele(
            payload.modele_id,
            tous=payload.tous,
            adresses=payload.adresses,
            accorde_par=utilisateur.id,
            motif=payload.motif,
            expire_le=payload.expire_le,
        )
    except ErreurDeblocage as e:
        raise erreur_api(e.statut_http, e.code)


@router_deblocage_modeles.post("/revoquer")
@limiteur.limit("30/minute")
def revoquer_un_deblocage_de_modele(request: Request, payload: RevoquerModelePayload, utilisateur=Depends(utilisateur_courant)):
    """Revoque le deblocage d'un modele pour tout le monde ou pour une liste d'adresses."""
    _exige_admin(utilisateur)
    try:
        return deblocage_modeles.revoquer_modele(payload.modele_id, tous=payload.tous, adresses=payload.adresses)
    except ErreurDeblocage as e:
        raise erreur_api(e.statut_http, e.code)
