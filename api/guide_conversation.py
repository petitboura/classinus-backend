"""Etape 2 du chantier "guide de decouverte", 16/09/2026, demande Bourama
-- voir core/guide_conversation.py. Leger : deux routes, lire et definir
si le guide interactif est actif sur une conversation. Meme forme que
api/persona_pedagogique_conversation.py, sans regle de verrouillage
mineur (rien ne l'a demandee ici, a ajouter seulement si Bourama le
demande explicitement).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.guide_conversation import obtenir_guide_actif, definir_guide_actif

router_guide_conversation = APIRouter(prefix="/api/conversations", tags=["guide_conversation"])


@router_guide_conversation.get("/{conversation_id}/guide-actif")
def lire(conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    actif = obtenir_guide_actif(conversation_id, utilisateur.id)
    return {"actif": actif}


class GuideActifPayload(BaseModel):
    actif: bool


@router_guide_conversation.put("/{conversation_id}/guide-actif")
def definir(conversation_id: str, payload: GuideActifPayload, utilisateur=Depends(utilisateur_courant)):
    resultat = definir_guide_actif(conversation_id, utilisateur.id, payload.actif)
    return {"actif": resultat["actif"]}
