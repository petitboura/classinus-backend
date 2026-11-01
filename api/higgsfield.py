"""API directe Higgsfield pour la page /higgsfield (hors chat MCP).

Branchée sur la même logique que core/outils_higgsfield.py (clé partagée),
mais en REST pour le frontend : upload → lancer → polling statut.
Limite journalière identique (higgsfield_usage).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.higgsfield_limites import reserver_generation
from core.higgsfield_requetes import ErreurHiggsfield, construire_requete_genjutsu, construire_requete_image, construire_requete_video
from core.generation_video_higgsfield import annuler_generation, estimer_cout, higgsfield_api_disponible, lancer_generation, statut_generation
from core.limitation_debit import limiteur
from core.outils_generation_commun import _supabase_memoire, _sauvegarder_generation_bibliotheque

# Contexte minimal pour _sauvegarder_generation_bibliotheque (qui lit user_id dans ctx)
class _CtxMemoire:
    def __init__(self, user_id: str):
        self.request_context = type("obj", (), {"request": type("obj", (), {"query_params": {"user_id": user_id}})})()

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
    format_image: str = "auto"
    qualite: str = "1k"
    images_reference: Optional[List[str]] = None


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
        adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_image, demande.qualite, demande.images_reference)
        reserver_generation(_supabase_memoire, utilisateur.id, "image")
        resultat = lancer_generation(adresse, corps)
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
        return {"request_id": resultat["request_id"], "titre": demande.titre}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield genjutsu user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


@router.get("/statut/{request_id}")
def statut(request_id: str, titre: str = "", utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        resultat = statut_generation(request_id)
        if resultat["etat"] == "terminee" and resultat.get("url") and titre:
            try:
                ctx = _CtxMemoire(utilisateur.id)
                nom = (titre.strip() or f"Higgsfield_{request_id}")
                url = resultat["url"]
                if url.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
                    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
                    _sauvegarder_generation_bibliotheque(ctx, url, f"{nom}.{ext}", mime)
                else:
                    _sauvegarder_generation_bibliotheque(ctx, url, f"{nom}.mp4", "video/mp4")
            except Exception as e:
                logging.warning(f"Sauvegarde bibliotheque Higgsfield echouee {request_id}: {e}")
        return resultat
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_ID_INVALIDE", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield statut {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.post("/annuler/{request_id}")
def annuler(request_id: str, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    try:
        ok = annuler_generation(request_id)
        return {"annulee": ok}
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
            adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_video, demande.qualite, demande.images_reference)
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
