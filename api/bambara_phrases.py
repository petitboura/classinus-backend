"""Page bambara : phrases proactives (22/11/2026, demande de Bourama).

La logique est dans core/phrases_bambara.py. Deux routes, réservées au compte connecté :
  GET /api/bambara/phrases              les phrases prêtes, avec les délais de la phrase « outil lent ».
                                        Celles dont l'audio manque ou n'est plus bon (texte ou voix changés)
                                        sont fabriquées en arrière plan : `en_preparation` dit combien.
  GET /api/bambara/phrases/{id}/audio   le fichier audio (WAV) d'une phrase prête, gardé par le navigateur.
Le frontend (lib/phrasesBambara.ts) n'affiche jamais d'erreur : la page est faite pour quelqu'un qui ne lit pas.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response

from api.auth import utilisateur_courant
from api.voix_bambara import bouche_branchee, synthetiser_texte, voix_active
from core.bambara_profils import ErreurBambara
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.outils_generation_commun import _supabase_memoire
from core.phrases_bambara import fabriquer_audios, lire_audio, lister_phrases

router = APIRouter(prefix="/api/bambara", tags=["bambara"])

_STATUT_HTTP = {
    "BAMBARA_PHRASE_INTROUVABLE": 404,
    "BAMBARA_INDISPONIBLE": 503,
}

# Un audio ne change jamais pour une même version (voix et texte) : le navigateur le garde un an, le
# paramètre `v` de l'adresse (la version) change dès que la voix ou le texte change.
_ENTETES_AUDIO = {"Cache-Control": "private, max-age=31536000, immutable"}


def _erreur(e: ErreurBambara):
    return erreur_api(_STATUT_HTTP.get(e.code, 503), e.code)


def _fabriquer_en_arriere_plan(identifiants, voix: str) -> None:
    try:
        fabriquer_audios(_supabase_memoire, voix, identifiants, synthetiser_texte)
    except Exception:
        logging.exception("Fabrication des audios des phrases bambara")


@router.get("/phrases")
@limiteur.limit("30/minute")
def mes_phrases(request: Request, taches: BackgroundTasks, utilisateur=Depends(utilisateur_courant)):
    voix = voix_active()
    try:
        reponse, a_fabriquer = lister_phrases(_supabase_memoire, voix)
    except ErreurBambara as e:
        raise _erreur(e)
    # Sans service de voix, rien n'est tenté : les phrases déjà prêtes restent proposées.
    if a_fabriquer and bouche_branchee():
        taches.add_task(_fabriquer_en_arriere_plan, a_fabriquer, voix)
    elif a_fabriquer:
        reponse["en_preparation"] = 0
    return reponse


@router.get("/phrases/{phrase_id}/audio")
@limiteur.limit("120/minute")
def audio_phrase(request: Request, phrase_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        contenu = lire_audio(_supabase_memoire, phrase_id, voix_active())
    except ErreurBambara as e:
        raise _erreur(e)
    return Response(content=contenu, media_type="audio/wav", headers=_ENTETES_AUDIO)
