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
from core.higgsfield_presets_controle import controler_presets
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
        adresse, corps = construire_requete_image(demande.modele, demande.prompt, demande.format_image, demande.qualite, demande.images_reference)
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
        reserver_generation(_supabase_memoire, utilisateur.id, "mcp")
        job_id = marketing_studio.creer(arguments)
        request_id = marketing_studio.PREFIXE_SUIVI + job_id
        higgsfield_suivi.enregistrer(utilisateur.id, request_id, demande.titre, "video")
        return {"request_id": request_id, "titre": demande.titre}
    except ErreurHiggsfield as e:
        raise erreur_api(400, "HIGGSFIELD_REQUETE_INVALIDE", message=str(e))
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
        return {"etat": ligne["etat"], "url": ligne["url"], "erreur": ligne["erreur"]}
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


@router.get("/diagnostic/presets-marketing-studio")
def diagnostic_presets_marketing_studio():
    """Lecture seule, sans credit depense : compare nos presets Marketing Studio a ceux de l'API Higgsfield.
    Ne renvoie jamais la cle (meme principe que /api/connexions/diagnostic)."""
    _verifier_disponible()
    try:
        return controler_presets()
    except ErreurHiggsfield as e:
        raise erreur_api(502, "HIGGSFIELD_CONTROLE_PRESETS_ECHEC", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR controle presets Marketing Studio: {e}")
        raise erreur_api(500, "HIGGSFIELD_CONTROLE_PRESETS_ECHEC", message="Controle impossible pour le moment.")


@router.get("/diagnostic/outils-marketing-studio")
def diagnostic_outils_marketing_studio():
    """Lecture seule, sans credit depense : renvoie les schemas reels des outils MCP Marketing Studio
    du compte partage (champs attendus par marketing_studio_v2_create, etc.).
    Ne renvoie jamais de jeton (meme principe que /diagnostic/presets-marketing-studio)."""
    from core.higgsfield_mcp_partage import lister_outils_partages
    try:
        outils = [
            o for o in lister_outils_partages()
            if "marketing_studio" in (o.get("nom") or "")
        ]
    except ErreurHiggsfield as e:
        raise erreur_api(502, "HIGGSFIELD_MCP_DIAGNOSTIC_ECHEC", message=str(e))
    except Exception as e:
        logging.error(f"ERREUR diagnostic outils Marketing Studio: {e}")
        raise erreur_api(500, "HIGGSFIELD_MCP_DIAGNOSTIC_ECHEC", message="Diagnostic impossible pour le moment.")
    return {"outils_trouves": len(outils), "outils": outils}


def _reduire_pour_diagnostic(valeur, profondeur=0):
    """Raccourcit une reponse JSON pour l'affichage : 2 elements par liste, textes coupes."""
    if profondeur > 8:
        return "..."
    if isinstance(valeur, list):
        reduit = [_reduire_pour_diagnostic(x, profondeur + 1) for x in valeur[:2]]
        if len(valeur) > 2:
            reduit.append(f"... ({len(valeur)} elements au total)")
        return reduit
    if isinstance(valeur, dict):
        return {k: _reduire_pour_diagnostic(v, profondeur + 1) for k, v in valeur.items()}
    if isinstance(valeur, str) and len(valeur) > 400:
        return valeur[:400] + "..."
    return valeur


@router.get("/diagnostic/mcp-marketing-studio-complet")
def diagnostic_mcp_marketing_studio_complet():
    """Lecture seule, sans credit depense : reponse MCP COMPLETE (contenu structure compris) de
    marketing_studio_v2_presets pour quelques categories, raccourcie (2 elements par liste).
    Sert a voir ou sont metadata, required_inputs et format_slugs. Ne renvoie jamais de jeton."""
    from core.higgsfield_mcp_partage import appeler_outil_brut_diagnostic
    rapport = {}
    for categorie in ("all", "product-shot", "motion", "ugc"):
        try:
            brut = appeler_outil_brut_diagnostic(
                "marketing_studio_v2_presets", {"category": categorie, "size": 3}
            )
            rapport[categorie] = {
                "cles_reponse": sorted(brut.keys()) if isinstance(brut, dict) else str(type(brut)),
                "reponse_reduite": _reduire_pour_diagnostic(brut),
            }
        except Exception as e:
            logging.error(f"ERREUR diagnostic MCP presets ({categorie}): {e}")
            rapport[categorie] = {"erreur": str(e)[:300]}
    return rapport


@router.get("/diagnostic/mcp-marketing-studio-contrats")
def diagnostic_mcp_marketing_studio_contrats():
    """Lecture seule, sans credit depense : (1) schemas de marketing_studio_v2_costs et des outils voisins,
    (2) tout le flux de presets parcouru page par page, resume par type : nombre, format_slugs,
    required_inputs distincts, cles presentes. Ne renvoie jamais de jeton."""
    import json as _json
    from core.higgsfield_mcp_partage import lister_tous_outils_diagnostic, appeler_outil_brut_diagnostic
    rapport = {}
    noms = {"marketing_studio_v2_costs", "marketing_list_avatars", "get_preset_instructions",
            "marketing_studio_v2_avatars"}
    try:
        rapport["schemas"] = [o for o in lister_tous_outils_diagnostic() if o["nom"] in noms]
    except Exception as e:
        logging.error(f"ERREUR diagnostic contrats (schemas): {e}")
        rapport["erreur_schemas"] = str(e)[:300]
    par_type = {}
    pages = 0
    cursor = None
    deja = set()
    try:
        while pages < 15:
            args = {"category": "all", "size": 100}
            if cursor is not None:
                args["cursor"] = cursor
            brut = appeler_outil_brut_diagnostic("marketing_studio_v2_presets", args)
            bloc = ((brut.get("structuredContent") or {}).get("presets")) or {}
            items = bloc.get("items") or []
            if not items:
                break
            pages += 1
            for it in items:
                if it.get("id") in deja:
                    continue
                deja.add(it.get("id"))
                t = str(it.get("type"))
                r = par_type.setdefault(t, {"nombre": 0, "format_slugs": set(), "required_inputs": set(),
                                            "cles": set(), "exemple_id": it.get("id")})
                r["nombre"] += 1
                r["format_slugs"].update(it.get("format_slugs") or [])
                r["cles"].update(it.keys())
                if "required_inputs" in it:
                    r["required_inputs"].add(_json.dumps(it["required_inputs"], sort_keys=True))
            nouveau = bloc.get("cursor")
            if nouveau is None or nouveau == cursor:
                break
            cursor = nouveau
        rapport["pages_lues"] = pages
        rapport["total_presets_vus"] = len(deja)
        rapport["par_type"] = {
            t: {
                "nombre": r["nombre"],
                "format_slugs": sorted(r["format_slugs"]),
                "required_inputs_distincts": sorted(r["required_inputs"])[:6],
                "cles_presentes": sorted(r["cles"]),
                "exemple_id": r["exemple_id"],
            }
            for t, r in par_type.items()
        }
    except Exception as e:
        logging.error(f"ERREUR diagnostic contrats (flux): {e}")
        rapport["erreur_flux"] = str(e)[:300]
    return rapport
