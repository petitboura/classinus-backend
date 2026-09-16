"""Chantier "mode source" (voir contexte-mode-source-clovis.md), demande
Bourama, 16/09/2026 -- voir core/mode_source_conversation.py. Leger : deux
routes, lire et definir le mode source actif d'une conversation. Meme
forme que api/persona_pedagogique_conversation.py, SANS regle de
verrouillage mineur (ce groupe doit rester visible et modifiable par tout
le monde, majeurs et mineurs).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.mode_source_conversation import (
    obtenir_mode_source,
    definir_mode_source,
)

router_mode_source = APIRouter(prefix="/api/conversations", tags=["mode_source"])


@router_mode_source.get("/{conversation_id}/mode-source")
def lire(conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    mode_source = obtenir_mode_source(conversation_id, utilisateur.id)
    return {"mode_source": mode_source}


class ModeSourcePayload(BaseModel):
    mode_source: str | None = None


@router_mode_source.put("/{conversation_id}/mode-source")
def definir(conversation_id: str, payload: ModeSourcePayload, utilisateur=Depends(utilisateur_courant)):
    resultat = definir_mode_source(conversation_id, utilisateur.id, payload.mode_source)
    if resultat is None and payload.mode_source is not None:
        raise erreur_api(400, "MODE_SOURCE_INVALIDE")
    return {"mode_source": resultat["mode_source"] if resultat else None}
