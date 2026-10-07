"""
Routes du rendu vidéo des animations du chat (07/10/2026, demande Bourama).

Le frontend (classinus-frontend) envoie le document HTML complet du lecteur
d'animation, déjà mis en page pour le format demandé (16:9 ou 9:16), puis
suit l'avancement et télécharge le MP4 une fois prêt. Tout le travail se
fait ici : le navigateur de l'utilisateur ne fait que demander et
récupérer le fichier, ce qui marche aussi sur téléphone.

Le rendu lui même est décrit dans core/rendu_animation_travaux.py (file
d'attente, isolation) et core/rendu_animation_processus.py (navigateur sans
écran et ffmpeg).
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.rendu_animation_constantes import TAILLE_MAX_DOCUMENT_OCTETS
from core.rendu_animation_travaux import (
    ErreurRendu,
    annuler_travail,
    creer_travail,
    lire_travail,
    serialiser,
)

router = APIRouter(prefix="/api/rendu-video-animation", tags=["rendu-video-animation"])


class DemandeRenduVideo(BaseModel):
    document_html: str = Field(max_length=TAILLE_MAX_DOCUMENT_OCTETS)
    format: str = Field(max_length=10)


def _lever(e: ErreurRendu):
    raise erreur_api(e.statut_http, e.code)


@router.post("", status_code=202)
@limiteur.limit("6/minute")
def demander_rendu(request: Request, demande: DemandeRenduVideo, utilisateur=Depends(utilisateur_courant)):
    try:
        return serialiser(creer_travail(utilisateur.id, demande.format, demande.document_html))
    except ErreurRendu as e:
        _lever(e)


@router.get("/{travail_id}")
def etat_rendu(travail_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        return serialiser(lire_travail(travail_id, utilisateur.id))
    except ErreurRendu as e:
        _lever(e)


@router.get("/{travail_id}/video")
def telecharger_video(travail_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        t = lire_travail(travail_id, utilisateur.id)
    except ErreurRendu as e:
        _lever(e)
    if t.statut != "pret" or t.chemin_video is None or not t.chemin_video.exists():
        raise erreur_api(409 if t.statut in ("attente", "en_cours") else 404,
                         "RENDU_VIDEO_PAS_PRETE" if t.statut in ("attente", "en_cours") else "RENDU_VIDEO_INTROUVABLE")
    nom = f"animation-{t.format.replace(':', 'x')}.mp4"
    return FileResponse(t.chemin_video, media_type="video/mp4", filename=nom)


@router.delete("/{travail_id}", status_code=204)
def annuler_rendu(travail_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        annuler_travail(travail_id, utilisateur.id)
    except ErreurRendu as e:
        _lever(e)
    return Response(status_code=204)
