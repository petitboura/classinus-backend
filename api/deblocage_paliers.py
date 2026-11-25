"""
Routes admin du deblocage de palier par personne (25/11/2026, demande de Bourama).

REGLE : Classinus n'a qu'UN SEUL agent. Le palier appartient a la personne, jamais a un agent.

Toute la logique vit dans core/deblocage_paliers.py. Ces routes sont reservees aux comptes
profiles.role = 'admin'. Aucun paiement n'est pris : le futur webhook de paiement appellera
core.deblocage_paliers.debloquer(source="paiement") directement, sans passer par ici.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth import utilisateur_courant
from api.permissions_hierarchie import _est_admin
from core import deblocage_paliers
from core.erreurs import erreur_api
from core.limitation_debit import limiteur

router_deblocage_paliers = APIRouter(prefix="/api/admin/deblocages-paliers", tags=["deblocages-paliers"])


def _exige_admin(utilisateur):
    if not _est_admin(utilisateur.id):
        raise erreur_api(403, "PAS_LE_DROIT_ADMIN")


def _lever(e: deblocage_paliers.ErreurDeblocage):
    raise erreur_api(e.statut_http, e.code)


class DebloquerPayload(BaseModel):
    # Exactement un des deux : l'identifiant du compte ou son e-mail.
    user_id: Optional[str] = None
    email: Optional[str] = None
    palier: str
    # Facultatif : sans date de fin, le deblocage dure jusqu'a sa revocation. Sans fuseau, la date est lue en UTC.
    expire_le: Optional[datetime] = None
    motif: Optional[str] = None


class RevoquerPayload(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None


@router_deblocage_paliers.get("")
@limiteur.limit("60/minute")
def lire_deblocages(
    request: Request,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    utilisateur=Depends(utilisateur_courant),
):
    """Les deblocages actifs d'une personne et son plus haut palier debloque."""
    _exige_admin(utilisateur)
    try:
        return deblocage_paliers.etat(deblocage_paliers.resoudre_utilisateur(user_id, email))
    except deblocage_paliers.ErreurDeblocage as e:
        _lever(e)


@router_deblocage_paliers.post("")
@limiteur.limit("30/minute")
def debloquer_palier(request: Request, payload: DebloquerPayload, utilisateur=Depends(utilisateur_courant)):
    """Accorde un palier a une personne (source manuel)."""
    _exige_admin(utilisateur)
    try:
        cible = deblocage_paliers.resoudre_utilisateur(payload.user_id, payload.email)
        deblocage = deblocage_paliers.debloquer(
            cible,
            payload.palier,
            accorde_par=utilisateur.id,
            motif=payload.motif,
            expire_le=payload.expire_le,
            source="manuel",
        )
        return {"user_id": cible, "deblocage": deblocage, **deblocage_paliers.etat(cible)}
    except deblocage_paliers.ErreurDeblocage as e:
        _lever(e)


@router_deblocage_paliers.post("/revoquer")
@limiteur.limit("30/minute")
def revoquer_deblocages(request: Request, payload: RevoquerPayload, utilisateur=Depends(utilisateur_courant)):
    """Revoque tous les deblocages actifs d'une personne."""
    _exige_admin(utilisateur)
    try:
        cible = deblocage_paliers.resoudre_utilisateur(payload.user_id, payload.email)
        return {"user_id": cible, **deblocage_paliers.revoquer(cible)}
    except deblocage_paliers.ErreurDeblocage as e:
        _lever(e)
