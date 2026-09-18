"""
Route REST de l'analytique agrégée du catalogue public, en lot (étape
7). Voir core/analytique_catalogue_public.py pour la logique et la note
sur la performance (un seul appel pour toute une page de cartes).
"""

from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from core.analytique_catalogue_public import analytique_en_lot

router = APIRouter(prefix="/api/analytique-catalogue-public", tags=["analytique-catalogue-public"])


class ElementDemande(BaseModel):
    type_element: str
    id: str


class LotPayload(BaseModel):
    elements: List[ElementDemande]


class Compteurs(BaseModel):
    partages_count: int
    etoiles_count: int
    cta_count: int
    enregistrements_count: int


@router.post("/lot", response_model=Dict[str, Compteurs])
def lot(payload: LotPayload):
    return analytique_en_lot([e.model_dump() for e in payload.elements])
