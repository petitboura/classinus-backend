"""Produits publics (28/11/2026, demande de Bourama).

Un produit (site, appli ou plateforme) a une page publique indexée par Google. La liste et le
détail sont publics, sans compte. Publier, modifier, supprimer, envoyer des images et lancer la
capture automatique d'un site exigent un compte. Le retrait par un administrateur passe aussi par
le traitement des signalements (api/signalements.py). La logique est dans core/produits_publics.py
et core/images_produits_publics.py.
"""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant, utilisateur_optionnel
from api.journal import journaliser
from api.permissions_hierarchie import _est_admin
from core import config_produits_publics as cfg
from core import images_produits_publics as images
from core import produits_publics
from core.erreurs import erreur_api
from core.limitation_debit import limiteur

router = APIRouter(prefix="/api/produits-publics", tags=["produits_publics"])


class ImageProduit(BaseModel):
    chemin: str
    alt: str = ""
    url: str | None = None


class ProduitPublic(BaseModel):
    id: str
    nom: str
    accroche: str = ""
    description: str = ""
    type_produit: str
    url: str
    logo_chemin: str | None = None
    logo_url: str | None = None
    images: list[ImageProduit] = []
    etiquettes: list[str] = []
    createur_nom: str | None = None
    publie_le: str | None = None
    modifie_le: str | None = None
    est_a_moi: bool = False


class DonneesProduit(BaseModel):
    nom: str
    accroche: str
    description: str = ""
    type_produit: str
    url: str
    logo_chemin: str | None = None
    images: list[ImageProduit] = Field(default_factory=list)
    etiquettes: list[str] = Field(default_factory=list)


class ImageEnvoyee(BaseModel):
    chemin: str
    url: str | None = None


class DemandeCapture(BaseModel):
    url: str


class RetraitAdmin(BaseModel):
    motif: str = ""


@router.get("", response_model=list[ProduitPublic])
def lister_produits(
    q: str | None = None,
    type_produit: str | None = None,
    etiquette: str | None = None,
    decalage: int = 0,
    limite: int = cfg.LISTE_LIMITE_DEFAUT,
    utilisateur=Depends(utilisateur_optionnel),
):
    """Liste publique, jamais de 401 : un visiteur sans compte (et Google) peut tout parcourir."""
    return produits_publics.lister(
        q or "", type_produit or "", etiquette or "", decalage, limite, utilisateur.id if utilisateur else None
    )


# Les routes fixes sont déclarées avant /{produit_id}, sinon "mes-produits" serait lu comme un identifiant.
@router.get("/mes-produits", response_model=list[ProduitPublic])
def mes_produits(utilisateur=Depends(utilisateur_courant)):
    return produits_publics.lister_mes_produits(utilisateur.id)


@router.post("/images", response_model=ImageEnvoyee, status_code=201)
@limiteur.limit("30/minute")
def envoyer_image(
    request: Request,
    fichier: UploadFile = File(...),
    logo: bool = Form(False),
    utilisateur=Depends(utilisateur_courant),
):
    octets = fichier.file.read(cfg.IMAGE_TAILLE_MAX_OCTETS + 1)
    return images.envoyer_image(utilisateur.id, octets, fichier.content_type or "", logo=logo)


@router.post("/capture", response_model=list[ImageEnvoyee])
@limiteur.limit("6/minute")
def capturer_site(request: Request, demande: DemandeCapture, utilisateur=Depends(utilisateur_courant)):
    """Capture automatique du site : une image bureau et une image téléphone, rangées pour ce compte."""
    return images.capturer_site(utilisateur.id, demande.url)


@router.get("/{produit_id}", response_model=ProduitPublic)
def obtenir_produit(produit_id: str, utilisateur=Depends(utilisateur_optionnel)):
    return produits_publics.obtenir(produit_id, utilisateur.id if utilisateur else None)


@router.post("", response_model=ProduitPublic, status_code=201)
@limiteur.limit("10/minute")
def publier_produit(request: Request, donnees: DonneesProduit, utilisateur=Depends(utilisateur_courant)):
    produit = produits_publics.publier(donnees.model_dump(), utilisateur.id)
    journaliser(action="produit.publie", user_id=utilisateur.id, cible_type="produit_public", cible_id=produit["id"], request=request)
    return produit


@router.put("/{produit_id}", response_model=ProduitPublic)
@limiteur.limit("30/minute")
def modifier_produit(request: Request, produit_id: str, donnees: DonneesProduit, utilisateur=Depends(utilisateur_courant)):
    return produits_publics.modifier(produit_id, donnees.model_dump(), utilisateur.id)


@router.delete("/{produit_id}", status_code=204)
def supprimer_produit(request: Request, produit_id: str, utilisateur=Depends(utilisateur_courant)):
    produits_publics.supprimer(produit_id, utilisateur.id)
    journaliser(action="produit.supprime", user_id=utilisateur.id, cible_type="produit_public", cible_id=produit_id, request=request)


@router.post("/{produit_id}/retirer-admin", status_code=204)
def retirer_produit_admin(request: Request, produit_id: str, payload: RetraitAdmin, utilisateur=Depends(utilisateur_courant)):
    """Retrait par un administrateur, sans passer par un signalement."""
    if not _est_admin(utilisateur.id):
        raise erreur_api(403, "PAS_LE_DROIT_ADMIN")
    produits_publics.retirer_par_admin(produit_id, payload.motif)
    journaliser(
        action="produit.retire_admin", user_id=utilisateur.id, cible_type="produit_public", cible_id=produit_id,
        details={"motif": payload.motif.strip()}, request=request,
    )
