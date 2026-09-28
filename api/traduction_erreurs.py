"""
Endpoint de traduction des messages d'erreur d'exécution de code (voir
core/traduction_erreurs.py) -- 27/09/2026, demande Bourama.

Réservé aux comptes connectés (utilisateur_courant, donc 401 sinon) :
"il clique sur traduire et on lui dit connecte-toi pour traduire" pour un
visiteur sans compte -- le chat lui-même reste accessible sans compte
(api/chat.py utilise utilisateur_optionnel), seule la traduction des
erreurs est réservée aux comptes.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.traduction_erreurs import traduire_erreur_execution

logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/api", tags=["traduction"])


class TraduireMessagePayload(BaseModel):
    texte: str
    langue_cible: str


class TraduireMessageReponse(BaseModel):
    # None si Gemini échoue -- l'appelant garde l'erreur originale, voir
    # core/traduction_erreurs.py.
    traduction: str | None


@router.post("/traduire-message", response_model=TraduireMessageReponse)
def traduire_message(payload: TraduireMessagePayload, utilisateur=Depends(utilisateur_courant)):
    traduction = traduire_erreur_execution(payload.texte, payload.langue_cible)
    return TraduireMessageReponse(traduction=traduction)
