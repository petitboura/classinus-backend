"""
Routes d'incrément des compteurs bruts du catalogue public (18/09/2026,
étape 6 + partages). Appelées à chaque clic sur BoutonAvecIA ou sur le
bouton "Partager" pour un élément du catalogue public -- jamais
bloquantes pour l'action utilisateur (voir docstrings frontend
correspondantes) : accessibles sans connexion (Depends(utilisateur_
optionnel), un visiteur peut cliquer "Partager" sans compte) et
best-effort côté frontend (l'appel échoue en silence, voir
ButtonPartager.tsx / BoutonAvecIA.tsx).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_optionnel
from core.erreurs import erreur_api
from core.compteurs_catalogue_public import incrementer_cta, incrementer_partage

router = APIRouter(prefix="/api/compteurs-catalogue-public", tags=["compteurs-catalogue-public"])


class IncrementPayload(BaseModel):
    type_element: str
    element_id: str


class IncrementResultat(BaseModel):
    total: int


@router.post("/cta", response_model=IncrementResultat)
def incrementer_cta_route(payload: IncrementPayload, utilisateur=Depends(utilisateur_optionnel)):
    try:
        return {"total": incrementer_cta(payload.type_element, payload.element_id)}
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            raise erreur_api(400, "TYPE_ELEMENT_INCONNU")
        if str(e) == "ELEMENT_INTROUVABLE":
            raise erreur_api(404, "ELEMENT_CATALOGUE_PUBLIC_INTROUVABLE")
        raise


@router.post("/partages", response_model=IncrementResultat)
def incrementer_partage_route(payload: IncrementPayload, utilisateur=Depends(utilisateur_optionnel)):
    try:
        return {"total": incrementer_partage(payload.type_element, payload.element_id)}
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            raise erreur_api(400, "TYPE_ELEMENT_INCONNU")
        if str(e) == "ELEMENT_INTROUVABLE":
            raise erreur_api(404, "ELEMENT_CATALOGUE_PUBLIC_INTROUVABLE")
        raise
