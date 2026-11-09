"""Parrainage (étape 3) : enregistrer le parrain d'un compte et lire son propre résumé.

La logique est dans core/parrainage.py et dans les fonctions SQL qu'il appelle. Le frontend appelle
POST /enregistrer quand la personne est connectée et qu'un code de lien est gardé de son arrivée.
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.outils_generation_commun import _supabase_memoire
from core.parrainage import (
    LONGUEUR_MAX_CODE,
    ErreurParrainage,
    enregistrer_parrainage,
    resume_parrainage,
)

router = APIRouter(prefix="/api/parrainage", tags=["parrainage"])

_STATUT_HTTP = {"PARRAINAGE_CODE_INVALIDE": 400, "PARRAINAGE_INDISPONIBLE": 503}


class DemandeEnregistrement(BaseModel):
    code: str = Field(..., min_length=1, max_length=LONGUEUR_MAX_CODE)


@router.post("/enregistrer")
@limiteur.limit("10/minute")
def enregistrer(request: Request, demande: DemandeEnregistrement, utilisateur=Depends(utilisateur_courant)):
    try:
        return enregistrer_parrainage(_supabase_memoire, utilisateur.id, demande.code)
    except ErreurParrainage as e:
        raise erreur_api(_STATUT_HTTP.get(e.code, 503), e.code)


@router.get("/moi")
@limiteur.limit("30/minute")
def mon_parrainage(request: Request, utilisateur=Depends(utilisateur_courant)):
    try:
        return resume_parrainage(_supabase_memoire, utilisateur.id)
    except ErreurParrainage as e:
        raise erreur_api(_STATUT_HTTP.get(e.code, 503), e.code)
