"""Page bambara : profils, historique des conversations et éléments gardés (18/11/2026).

La logique est dans core/bambara_profils.py. Chaque route est réservée au compte connecté et ne voit
que ses propres lignes. Le frontend (components/bambara) appelle ces routes sans jamais montrer
d'erreur à l'écran : la page est faite pour quelqu'un qui ne lit pas.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.bambara_profils import (
    LONGUEUR_MAX_AUDIO_BASE64,
    LONGUEUR_MAX_NOM,
    ErreurBambara,
    creer_profil,
    enregistrer_premier_message,
    garder,
    lire_audio,
    lister_conversations,
    lister_gardes,
    lister_profils,
    normaliser_profil,
    retirer_garde,
)
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.outils_generation_commun import _supabase_memoire

router = APIRouter(prefix="/api/bambara", tags=["bambara"])

_STATUT_HTTP = {
    "BAMBARA_PROFIL_NOM_INVALIDE": 400,
    "BAMBARA_TROP_DE_PROFILS": 400,
    "BAMBARA_PROFIL_INTROUVABLE": 404,
    "BAMBARA_CONVERSATION_INVALIDE": 400,
    "BAMBARA_CONVERSATION_INTROUVABLE": 404,
    "BAMBARA_MESSAGE_VIDE": 400,
    "BAMBARA_AUDIO_INVALIDE": 400,
    "BAMBARA_GARDE_INVALIDE": 400,
    "BAMBARA_INDISPONIBLE": 503,
}


def _erreur(e: ErreurBambara):
    return erreur_api(_STATUT_HTTP.get(e.code, 503), e.code)


class DemandeProfil(BaseModel):
    nom: str = Field(..., min_length=1, max_length=LONGUEUR_MAX_NOM * 2)
    prenom: str = Field(..., min_length=1, max_length=LONGUEUR_MAX_NOM * 2)


class AudioPremierMessage(BaseModel):
    base64: str = Field(..., min_length=1, max_length=LONGUEUR_MAX_AUDIO_BASE64)
    duree_ms: int = Field(..., ge=0, le=600_000)
    pics: List[float] = Field(default_factory=list, max_length=64)


class DemandePremierMessage(BaseModel):
    profil_id: Optional[str] = None
    texte: Optional[str] = Field(default=None, max_length=4000)
    audio: Optional[AudioPremierMessage] = None


class DemandeGarde(BaseModel):
    profil_id: Optional[str] = None
    genre: str = Field(..., max_length=10)
    url: str = Field(..., min_length=1, max_length=2000)
    titre: Optional[str] = Field(default="", max_length=600)
    miniature: Optional[str] = Field(default=None, max_length=2000)
    id_video: Optional[str] = Field(default=None, max_length=64)


@router.get("/profils")
@limiteur.limit("30/minute")
def mes_profils(request: Request, utilisateur=Depends(utilisateur_courant)):
    try:
        return {"profils": lister_profils(_supabase_memoire, utilisateur.id)}
    except ErreurBambara as e:
        raise _erreur(e)


@router.post("/profils")
@limiteur.limit("10/minute")
def nouveau_profil(request: Request, demande: DemandeProfil, utilisateur=Depends(utilisateur_courant)):
    try:
        return creer_profil(_supabase_memoire, utilisateur.id, demande.nom, demande.prenom)
    except ErreurBambara as e:
        raise _erreur(e)


@router.get("/conversations")
@limiteur.limit("30/minute")
def mes_conversations(request: Request, profil_id: Optional[str] = None, utilisateur=Depends(utilisateur_courant)):
    try:
        return {"conversations": lister_conversations(_supabase_memoire, utilisateur.id, normaliser_profil(profil_id))}
    except ErreurBambara as e:
        raise _erreur(e)


@router.put("/conversations/{conversation_id}/premier-message")
@limiteur.limit("30/minute")
def premier_message(
    request: Request, conversation_id: str, demande: DemandePremierMessage, utilisateur=Depends(utilisateur_courant)
):
    try:
        audio = demande.audio.model_dump() if demande.audio else None
        return enregistrer_premier_message(
            _supabase_memoire,
            utilisateur.id,
            conversation_id,
            normaliser_profil(demande.profil_id),
            demande.texte,
            audio,
        )
    except ErreurBambara as e:
        raise _erreur(e)


@router.get("/conversations/{conversation_id}/audio")
@limiteur.limit("60/minute")
def audio_conversation(request: Request, conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        return lire_audio(_supabase_memoire, utilisateur.id, conversation_id)
    except ErreurBambara as e:
        raise _erreur(e)


@router.get("/gardes")
@limiteur.limit("30/minute")
def mes_gardes(request: Request, profil_id: Optional[str] = None, utilisateur=Depends(utilisateur_courant)):
    try:
        return {"gardes": lister_gardes(_supabase_memoire, utilisateur.id, normaliser_profil(profil_id))}
    except ErreurBambara as e:
        raise _erreur(e)


@router.post("/gardes")
@limiteur.limit("60/minute")
def nouvelle_garde(request: Request, demande: DemandeGarde, utilisateur=Depends(utilisateur_courant)):
    try:
        return garder(
            _supabase_memoire,
            utilisateur.id,
            normaliser_profil(demande.profil_id),
            demande.genre,
            demande.url,
            demande.titre,
            demande.miniature,
            demande.id_video,
        )
    except ErreurBambara as e:
        raise _erreur(e)


@router.delete("/gardes/{garde_id}")
@limiteur.limit("60/minute")
def supprimer_garde(request: Request, garde_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        retirer_garde(_supabase_memoire, utilisateur.id, garde_id)
        return {"ok": True}
    except ErreurBambara as e:
        raise _erreur(e)
