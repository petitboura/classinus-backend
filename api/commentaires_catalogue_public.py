"""
Routes REST pour les commentaires sur un élément du catalogue public
(18/09/2026, chantier "profil contributeur bibliotheque publique").
Toute la logique vit dans core/commentaires_catalogue_public.py -- ce
routeur n'est qu'un fin wrapper (auth, conversion des erreurs en
réponses HTTP), même principe que api/etoiles_catalogue_public.py.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.commentaires_catalogue_public import (
    creer_commentaire,
    lister_commentaires,
    supprimer_commentaire,
)

router = APIRouter(prefix="/api/commentaires-catalogue-public", tags=["commentaires-catalogue-public"])


class Commentaire(BaseModel):
    id: str
    contenu: str
    created_at: str
    utilisateur_id: str
    auteur_nom: str
    auteur_avatar_url: Optional[str] = None


class ListeCommentaires(BaseModel):
    commentaires: List[Commentaire]
    total: int


class CreerCommentairePayload(BaseModel):
    type_element: str
    element_id: str
    contenu: str


@router.get("/{type_element}/{element_id}", response_model=ListeCommentaires)
def lister(type_element: str, element_id: str, decalage: int = Query(0, ge=0), limite: int = Query(20, ge=1)):
    try:
        return lister_commentaires(type_element, element_id, decalage, limite)
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            raise erreur_api(400, "TYPE_ELEMENT_INCONNU")
        raise
    except Exception:
        raise erreur_api(500, "ECHEC_DU_STOCKAGE_REESSAIE")


@router.post("", response_model=Commentaire, status_code=201)
def creer(payload: CreerCommentairePayload, utilisateur=Depends(utilisateur_courant)):
    try:
        cree = creer_commentaire(payload.type_element, payload.element_id, utilisateur.id, payload.contenu)
    except ValueError as e:
        code = str(e)
        if code == "TYPE_ELEMENT_INCONNU":
            raise erreur_api(400, "TYPE_ELEMENT_INCONNU")
        if code == "ELEMENT_INTROUVABLE":
            raise erreur_api(404, "ELEMENT_CATALOGUE_PUBLIC_INTROUVABLE")
        if code == "COMMENTAIRE_VIDE":
            raise erreur_api(400, "COMMENTAIRE_VIDE")
        if code == "PROFIL_PUBLIC_REQUIS_POUR_COMMENTER":
            raise erreur_api(403, "PROFIL_PUBLIC_REQUIS_POUR_COMMENTER")
        raise
    except Exception:
        raise erreur_api(500, "ECHEC_DU_STOCKAGE_REESSAIE")
    return {
        **cree,
        "auteur_nom": "",  # rempli par le frontend depuis son propre profil déjà en mémoire (c'est lui l'auteur)
        "auteur_avatar_url": None,
    }


@router.delete("/{commentaire_id}", status_code=204)
def supprimer(commentaire_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        supprimer_commentaire(commentaire_id, utilisateur.id)
    except ValueError as e:
        code = str(e)
        if code == "COMMENTAIRE_INTROUVABLE":
            raise erreur_api(404, "COMMENTAIRE_INTROUVABLE")
        if code == "COMMENTAIRE_NE_T_APPARTIENT_PAS":
            raise erreur_api(403, "COMMENTAIRE_NE_T_APPARTIENT_PAS")
        raise
