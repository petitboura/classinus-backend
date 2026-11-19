"""API directe Higgsfield pour la page /higgsfield (hors chat MCP).

Branchée sur la même logique que core/outils_higgsfield.py (clé partagée),
mais en REST pour le frontend : upload → lancer → polling statut.
Vidéos : limite journalière (higgsfield_usage). Images : 1 crédit par image (credits_images).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant
from core.credits_images import (
    ErreurCreditsImages,
    rattacher_credit_image,
    rendre_credit_image,
    reserver_credit_image,
)
from core.erreurs import erreur_api
from core.higgsfield_limites import reserver_generation
from core.higgsfield_messages_en import message_en
from core.higgsfield_requetes import ErreurHiggsfield, construire_requete_genjutsu, construire_requete_image, construire_requete_video
from core.generation_video_higgsfield import annuler_generation, estimer_cout, higgsfield_api_disponible, lancer_generation
from core.limitation_debit import limiteur
from core import higgsfield_suivi
from core import higgsfield_telechargement
from core import higgsfield_marketing_studio as marketing_studio
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
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", detail=str(e), detail_en=message_en(str(e)))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield video user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


@router.post("/image")
@limiteur.limit("10/minute")
def lancer_image(request: Request, demande: DemandeImage, utilisateur=Depends(utilisateur_courant)):
    _verifier_disponible()
    reference_credit = None
    try:
        adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_image, demande.qualite, demande.images_reference, demande.style_id)
        # Un crédit est retiré juste avant l'envoi (la demande est déjà validée) et rendu si l'envoi échoue.
        reference_credit = reserver_credit_image(_supabase_memoire, utilisateur.id)
        resultat = lancer_generation(adresse, corps)
        rattacher_credit_image(_supabase_memoire, utilisateur.id, reference_credit, resultat["request_id"])
        higgsfield_suivi.enregistrer(utilisateur.id, resultat["request_id"], demande.titre, "image")
        return {"request_id": resultat["request_id"], "titre": demande.titre}
    except ErreurCreditsImages as e:
        raise erreur_api(402, e.code)
    except ErreurHiggsfield as e:
        rendre_credit_image(_supabase_memoire, utilisateur.id, reference_credit)
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", detail=str(e), detail_en=message_en(str(e)))
    except Exception as e:
        rendre_credit_image(_supabase_memoire, utilisateur.id, reference_credit)
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
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", detail=str(e), detail_en=message_en(str(e)))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield genjutsu user {utilisateur.id}: {e}")
        raise erreur_api(500, "ECHEC_LANCEMENT_HIGGSFIELD")


class DemandeMarketingStudio(BaseModel):
    preset_id: str = Field(..., min_length=8, max_length=64)
    preset_type: str = Field(..., min_length=3, max_length=40)
    preset_nom: str = ""
    titre: str = Field(..., min_length=1, max_length=120)
    image_produit_url: str = ""
    image_avatar_url: str = ""
    url_marque: str = ""
    prompt: str = ""
    format_image: str = ""


@router.post("/marketing-studio")
@limiteur.limit("10/minute")
def lancer_marketing_studio(request: Request, demande: DemandeMarketingStudio, utilisateur=Depends(utilisateur_courant)):
    """Genere a partir d'un preset Marketing Studio, par le compte partage (MCP).
    Les images sont d'abord envoyees a Higgsfield, puis la generation est lancee et suivie
    par le meme suivi serveur que les autres generations (identifiant prefixe "mcp:")."""
    try:
        # Validation complete avant tout envoi : on ne depense ni ne reserve rien si la demande est incoherente.
        faux = "00000000-0000-0000-0000-000000000000"
        marketing_studio.construire_creation(
            demande.preset_id, demande.preset_type, demande.preset_nom,
            faux if demande.image_produit_url else "", faux if demande.image_avatar_url else "",
            demande.url_marque, demande.prompt, demande.format_image,
        )
        media_produit = marketing_studio.importer_image(demande.image_produit_url) if demande.image_produit_url else ""
        media_avatar = marketing_studio.importer_image(demande.image_avatar_url) if demande.image_avatar_url else ""
        arguments = marketing_studio.construire_creation(
            demande.preset_id, demande.preset_type, demande.preset_nom, media_produit, media_avatar,
            demande.url_marque, demande.prompt, demande.format_image,
        )
        media = marketing_studio.media_du_type(demande.preset_type)
        reference_credit = None
        if media == "image":
            # Une image coûte 1 crédit d'images (pas de limite par jour) ; les videos gardent la limite du compte partage.
            reference_credit = reserver_credit_image(_supabase_memoire, utilisateur.id)
        else:
            try:
                reserver_generation(_supabase_memoire, utilisateur.id, "mcp")
            except ErreurHiggsfield as e:
                if "Limite du jour" in str(e):
                    from core.higgsfield_limites import limite_du_jour
                    raise marketing_studio.ErreurMarketingStudio("MARKETING_LIMITE_JOUR", limite=limite_du_jour("mcp")) from e
                raise marketing_studio.ErreurMarketingStudio("MARKETING_LIMITE_INDISPONIBLE") from e
        try:
            job_id = marketing_studio.creer(arguments)
        except Exception:
            # Le lancement a échoué : le crédit retiré est rendu avant de remonter l'erreur.
            rendre_credit_image(_supabase_memoire, utilisateur.id, reference_credit)
            raise
        request_id = marketing_studio.PREFIXE_SUIVI + job_id
        rattacher_credit_image(_supabase_memoire, utilisateur.id, reference_credit, request_id)
        higgsfield_suivi.enregistrer(utilisateur.id, request_id, demande.titre, media)
        return {"request_id": request_id, "titre": demande.titre}
    except ErreurCreditsImages as e:
        raise erreur_api(402, e.code)
    except marketing_studio.ErreurMarketingStudio as e:
        raise erreur_api(400, e.code, **e.params)
    except ErreurHiggsfield as e:
        logging.error(f"ERREUR Higgsfield marketing studio user {utilisateur.id}: {e}")
        raise erreur_api(400, "MARKETING_INDISPONIBLE")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR Higgsfield marketing studio user {utilisateur.id}: {e}")
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
        return {
            "etat": ligne["etat"], "etape": ligne.get("etape", "creation"), "url": ligne["url"], "erreur": ligne["erreur"],
            "telechargement_debloque": higgsfield_telechargement.est_debloque(ligne),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR Higgsfield statut {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.get("/generations")
def generations(limite: int = 20, utilisateur=Depends(utilisateur_courant)):
    """Générations récentes de l'utilisateur (en cours et terminées), pour retrouver ce qui a tourné app fermée."""
    try:
        lignes = higgsfield_suivi.lister(utilisateur.id, limite)
        for ligne in lignes:
            ligne["telechargement_debloque"] = higgsfield_telechargement.est_debloque(ligne)
        return {"generations": lignes}
    except Exception as e:
        logging.error(f"ERREUR Higgsfield liste generations user {utilisateur.id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.post("/partage-termine/{request_id}")
@limiteur.limit("30/minute")
def partage_termine(request: Request, request_id: str, utilisateur=Depends(utilisateur_courant)):
    """L'appli signale que l'utilisateur a terminé le partage de son image : le téléchargement se débloque."""
    try:
        if higgsfield_suivi.obtenir(utilisateur.id, request_id) is None:
            raise erreur_api(404, "GENERATION_HIGGSFIELD_INTROUVABLE")
        if not higgsfield_telechargement.marquer_partage_termine(utilisateur.id, request_id):
            raise erreur_api(400, "PARTAGE_IMAGE_INVALIDE")
        return {"telechargement_debloque": True}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR Higgsfield partage termine {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_STATUT_HIGGSFIELD")


@router.get("/telecharger/{request_id}")
@limiteur.limit("30/minute")
def telecharger(request: Request, request_id: str, utilisateur=Depends(utilisateur_courant)):
    """Télécharge le résultat d'une génération. Une image exige un partage terminé, la vidéo non."""
    try:
        ligne = higgsfield_suivi.obtenir(utilisateur.id, request_id)
        if ligne is None:
            raise erreur_api(404, "GENERATION_HIGGSFIELD_INTROUVABLE")
        if ligne["etat"] != "terminee" or not ligne.get("url"):
            raise erreur_api(409, "IMPOSSIBLE_TELECHARGER_HIGGSFIELD")
        if not higgsfield_telechargement.est_debloque(ligne):
            raise erreur_api(403, "TELECHARGEMENT_PARTAGE_REQUIS")
        contenu, type_mime, nom = higgsfield_telechargement.lire_fichier(ligne)
        return Response(content=contenu, media_type=type_mime, headers={"Content-Disposition": f'attachment; filename="{nom}"'})
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR Higgsfield telecharger {request_id}: {e}")
        raise erreur_api(500, "IMPOSSIBLE_TELECHARGER_HIGGSFIELD")


@router.post("/annuler/{request_id}")
def annuler(request_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        if higgsfield_suivi.obtenir(utilisateur.id, request_id) is None:
            raise erreur_api(404, "GENERATION_HIGGSFIELD_INTROUVABLE")
        if request_id.startswith(marketing_studio.PREFIXE_SUIVI):
            # Aucun outil d'annulation connu pour Marketing Studio : on ne pretend pas annuler.
            return {"annulee": False}
        _verifier_disponible()
        ok = annuler_generation(request_id)
        if ok:
            higgsfield_suivi.marquer_annulee(utilisateur.id, request_id)
        return {"annulee": ok}
    except HTTPException:
        raise
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_ID_INVALIDE", detail=str(e), detail_en=message_en(str(e)))
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
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", detail=str(e), detail_en=message_en(str(e)))
    except Exception as e:
        logging.error(f"ERREUR Higgsfield estimation: {e}")
        raise erreur_api(500, "IMPOSSIBLE_ESTIMER_HIGGSFIELD")


@router.get("/disponible")
def disponible(utilisateur=Depends(utilisateur_courant)):
    return {"disponible": higgsfield_api_disponible()}
