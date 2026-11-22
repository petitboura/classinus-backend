"""Page bambara : les messages audio d'une conversation (22/11/2026).

La logique est dans core/bambara_audios_messages.py. Chaque route est réservée au compte connecté. Le
frontend (components/bambara) n'affiche jamais d'erreur : la page est faite pour quelqu'un qui ne lit pas.
"""
from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from api.bambara_profils import _STATUT_HTTP
from core.bambara_audios_messages import (
    enregistrer_audio_message,
    lire_audio_message,
    lister_audios_conversation,
)
from core.bambara_profils import LONGUEUR_MAX_AUDIO_BASE64, ErreurBambara
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.outils_generation_commun import _supabase_memoire

router = APIRouter(prefix="/api/bambara", tags=["bambara"])


def _erreur(e: ErreurBambara):
    return erreur_api(_STATUT_HTTP.get(e.code, 503), e.code)


class DemandeAudioMessage(BaseModel):
    sens: str = Field(..., max_length=10)
    base64: str = Field(..., min_length=1, max_length=LONGUEUR_MAX_AUDIO_BASE64)
    duree_ms: int = Field(..., ge=0, le=600_000)
    pics: List[float] = Field(default_factory=list, max_length=64)


@router.put("/conversations/{conversation_id}/messages/{message_id}/audio")
@limiteur.limit("60/minute")
def audio_du_message(
    request: Request, conversation_id: str, message_id: int, demande: DemandeAudioMessage, utilisateur=Depends(utilisateur_courant)
):
    try:
        return enregistrer_audio_message(
            _supabase_memoire,
            utilisateur.id,
            conversation_id,
            message_id,
            demande.sens,
            {"base64": demande.base64, "duree_ms": demande.duree_ms, "pics": demande.pics},
        )
    except ErreurBambara as e:
        raise _erreur(e)


@router.get("/conversations/{conversation_id}/audios")
@limiteur.limit("60/minute")
def audios_conversation(request: Request, conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        return {"audios": lister_audios_conversation(_supabase_memoire, utilisateur.id, conversation_id)}
    except ErreurBambara as e:
        raise _erreur(e)


@router.get("/audios/{audio_id}")
@limiteur.limit("120/minute")
def audio_message(request: Request, audio_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        return lire_audio_message(_supabase_memoire, utilisateur.id, audio_id)
    except ErreurBambara as e:
        raise _erreur(e)
