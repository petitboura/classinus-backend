"""
Route REST pour l'action de mettre/retirer une étoile sur un élément du
catalogue public (17/09/2026, demande Bourama). Toute la logique vit
dans core/etoiles_catalogue_public.py -- ce routeur n'est qu'un fin
wrapper (auth, conversion des erreurs en réponses HTTP).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.etoiles_catalogue_public import basculer_etoile

router = APIRouter(prefix="/api/etoiles-catalogue-public", tags=["etoiles-catalogue-public"])


class BasculerEtoilePayload(BaseModel):
    type_element: str
    element_id: str


class EtoileResultat(BaseModel):
    etoile: bool
    etoiles_count: int


@router.post("/basculer", response_model=EtoileResultat)
def basculer(payload: BasculerEtoilePayload, utilisateur=Depends(utilisateur_courant)):
    try:
        return basculer_etoile(payload.type_element, payload.element_id, utilisateur.id)
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            raise erreur_api(400, "TYPE_ELEMENT_INCONNU")
        if str(e) == "ELEMENT_INTROUVABLE":
            raise erreur_api(404, "ELEMENT_CATALOGUE_PUBLIC_INTROUVABLE")
        raise
