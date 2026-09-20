"""Etape 2 du chantier "guide de decouverte", 16/09/2026, demande Bourama
-- voir core/guide_conversation.py. Leger : deux routes, lire et definir
si le guide interactif est actif sur une conversation. Meme forme que
api/persona_pedagogique_conversation.py, sans regle de verrouillage
mineur (rien ne l'a demandee ici, a ajouter seulement si Bourama le
demande explicitement).

ETENDU le 20/09/2026 (chantier "demo + guide visuel", voir
specs-demo-decouverte.md dans clovis-frontend) : sous_mode ajoute aux
deux routes ("textuel" par defaut, "visuel" ou "demo"), meme forme que
core/guide_conversation.py cote fonctions.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.guide_conversation import obtenir_guide_actif, definir_guide_actif

router_guide_conversation = APIRouter(prefix="/api/conversations", tags=["guide_conversation"])


@router_guide_conversation.get("/{conversation_id}/guide-actif")
def lire(conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    return obtenir_guide_actif(conversation_id, utilisateur.id)


class GuideActifPayload(BaseModel):
    actif: bool
    sous_mode: str = "textuel"


@router_guide_conversation.put("/{conversation_id}/guide-actif")
def definir(conversation_id: str, payload: GuideActifPayload, utilisateur=Depends(utilisateur_courant)):
    resultat = definir_guide_actif(conversation_id, utilisateur.id, payload.actif, payload.sous_mode)
    return {"actif": resultat["actif"], "sous_mode": resultat.get("sous_mode", "textuel")}
