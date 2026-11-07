"""API directe Higgsfield pour la page /higgsfield (hors chat MCP).

Branchée sur la même logique que core/outils_higgsfield.py (clé partagée),
mais en REST pour le frontend : upload → lancer → polling statut.
Limite journalière identique (higgsfield_usage).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.higgsfield_limites import reserver_generation
from core.higgsfield_requetes import ErreurHiggsfield, construire_requete_genjutsu, construire_requete_image, construire_requete_video
from core.generation_video_higgsfield import annuler_generation, estimer_cout, higgsfield_api_disponible, lancer_generation
from core.limitation_debit import limiteur
from core import higgsfield_suivi
from core.outils_generation_commun import _supabase_memoire

router = APIRouter(prefix="/api/higgsfield", tags=["higgsfield"])


def _verifier_disponible():
    if not higgsfield_api_disponible():
        raise erreur_api(503, "HIGGSFIELD_NON_CONFIGURE")


class DemandeVideo(BaseModel):
    prompt: str = ""
    titre: str = Field(..., min_length=1, max_length=120)
    modele: str = "seedance"
    duree_secondes: int = 5
    format_video: str = ""
    qualite: str = ""
    son: bool = True
    image_url: str = ""
    image_fin_url: str = ""
    images_reference: Optional[List[str]] = None
    videos_reference: Optional[List[str]] = None
    sons_reference: Optional[List[str]] = None


class DemandeImage(BaseModel):
    prompt: str = Field(..., min_length=1)
    titre: str = Field(..., min_length=1, max_length=120)
    modele: str = "grok"
    # Vide : Higgsfield applique le réglage par défaut du modèle (grok ou soul n'ont pas les mêmes valeurs).
    format_image: str = ""
    qualite: str = ""
    images_reference: Optional[List[str]] = None
    style_id: str = ""


class DemandeGenjutsu(BaseModel):
    video_url: str = Field(..., min_length=8)
    titre: str = Field(..., min_length=1, max_length=120)
    modele: str = "genjutsu-motion"
    prompt: str = ""
    images_reference: Optional[List[str]] = None
    resolution: str = ""
    preset_id: str = ""


class DemandeEstimation(BaseModel):
    genre: str = Field(..., description="video | image | genjutsu")
    prompt: str = ""
    modele: str = ""
    duree_secondes: int = 5
    format_video: str = ""
    qualite: str = ""
    son: bool = True
    image_url: str = ""
    images_reference: Optional[List[str]] = None
    style_id: str = ""


@router.post("/video")
@limiteur.limit("10/minute")
def lancer_video(request: Request, demande: DemandeVideo, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        adresse, corps = construire_requete_video(
            demande.modele, demande.prompt, demande.duree_secondes, demande.format_video, demande.qualite, demande.son,
            demande.image_url, demande.image_fin_url, demande.images_reference, demande.videos_reference, demande.sons_reference,
        )
        reserver_generation(_supabase_memoire, utilisateur.id, "video")
        resultat = lancer_generation(adresse, corps)
        higgsfield_suivi.enregistrer(utilisateur.id, resultat["request_id"], demande.titre, "video")
        return {"request_id": resultat["request_id"], "titre": demande.titre}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield video user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


@router.post("/image")
@limiteur.limit("10/minute")
def lancer_image(request: Request, demande: DemandeImage, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_image, demande.qualite, demande.images_reference, demande.style_id)
        reserver_generation(_supabase_memoire, utilisateur.id, "image")
        resultat = lancer_generation(adresse, corps)
        higgsfield_suivi.enregistrer(utilisateur.id, resultat["request_id"], demande.titre, "image")
        return {"request_id": resultat["request_id"], "titre": demande.titre}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield image user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


@router.post("/genjutsu")
@limiteur.limit("10/minute")
def lancer_genjutsu(request: Request, demande: DemandeGenjutsu, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        adresse, corps = construire_requete_genjutsu(demande.modele, demande.video_url, demande.images_reference, demande.prompt, demande.resolution, demande.preset_id)
        reserver_generation(_supabase_memoire, utilisateur.id, "video")
        resultat = lancer_generation(adresse, corps)
        higgsfield_suivi.enregistrer(utilisateur.id, resultat["request_id"], demande.titre, "video")
        return {"request_id": resultat["request_id"], "titre": demande.titre}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield genjutsu user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


@router.get("/statut/{request_id}")
def statut(request_id: str, utilisateur=Depends(utilisateur_courant)):
    """État d'une génération de l'utilisateur, lu en base. Le suivi et la sauvegarde sont faits
    par le serveur (boucle de fond) : cet appel ne fait que rafraîchir plus vite si besoin."""
    try:
        ligne = higgsfield_suivi.obtenir(utilisateur.id, request_id)
        if ligne is None:
            raise erreur_api(404, "GENERATION_HIGGSFIELD_INTROUVABLE")
        if ligne["etat"] == "en_cours":
            higgsfield_suivi.traiter_une_generation(utilisateur.id, request_id)
            ligne = higgsfield_suivi.obtenir(utilisateur.id, request_id) or ligne
        return {"etat": ligne["etat"], "etape": ligne.get("etape", "creation"), "url": ligne["url"], "erreur": ligne["erreur"]}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR Higgsfield statut {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.get("/generations")
def generations(limite: int = 20, utilisateur=Depends(utilisateur_courant)):
    """Générations récentes de l'utilisateur (en cours et terminées), pour retrouver ce qui a tourné app fermée."""
    try:
        return {"generations": higgsfield_suivi.lister(utilisateur.id, limite)}
    except Exception as e:
        logging.error(f"ERREUR Higgsfield liste generations user {utilisateur.id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.post("/annuler/{request_id}")
def annuler(request_id: str, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        if higgsfield_suivi.obtenir(utilisateur.id, request_id) is None:
            raise erreur_api(404, "GENERATION_HIGGSFIELD_INTROUVABLE")
        ok = annuler_generation(request_id)
        if ok:
            higgsfield_suivi.marquer_annulee(utilisateur.id, request_id)
        return {"annulee": ok}
    except HTTPException:
        raise
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_ID_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield annuler {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_ANNULER_HIGGSFIELD")


@router.post("/estimation")
def estimation(demande: DemandeEstimation, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        g = (demande.genre or "").strip().lower()
        if g == "image":
            adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_video, demande.qualite, demande.images_reference, demande.style_id)
        elif g == "genjutsu":
            refs = demande.images_reference if demande.images_reference else ["https://example.com/ref.jpg"]
            adresse, corps = construire_requete_genjutsu(demande.modele or "genjutsu-motion", demande.image_url or "https://example.com/video.mp4", refs, demande.prompt, demande.qualite or "", "")
        else:
            adresse, corps = construire_requete_video(demande.modele, demande.prompt, demande.duree_secondes, demande.format_video, demande.qualite, demande.son, demande.image_url, "", demande.images_reference)
        prix = estimer_cout(adresse, corps)
        return {"credits": prix.get("credits")}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield estimation: {e}")
        raise erreur_api(500, "IMPOSSIBLE_ESTIMER_HIGGSFIELD")


@router.get("/disponible")
def disponible(utilisateur=Depends(utilisateur_courant)):
    return {"disponible": higgsfield_api_disponible()}
