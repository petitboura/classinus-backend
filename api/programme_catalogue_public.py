"""
Routes REST pour le catalogue public du Programme (22/09/2026, demande
Bourama). Toute la logique vit dans core/programme_catalogue_public.py
-- ce routeur n'est qu'un fin wrapper (auth, conversion des erreurs en
réponses HTTP), même principe que api/comportements_publics.py.

Recherche/liste/lecture publiques (utilisateur_optionnel, jamais de
401) ; publier/modifier/supprimer/copier_vers_perso réservés à un
compte (utilisateur_courant).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import utilisateur_courant, utilisateur_optionnel
from core.erreurs import erreur_api
from core.etoiles_catalogue_public import etoiles_utilisateur
from core.programme_catalogue_public import (
    publier_programme_public,
    modifier_programme_public,
    supprimer_programme_public,
    lire_programme_public,
    lister_programmes_catalogue_public,
    chercher_programmes_catalogue_public,
    copier_programme_vers_perso,
    obtenir_programmes_publics_par_ids,
)

router = APIRouter(prefix="/api/programmes-catalogue-public", tags=["programmes_catalogue_public"])


class NotionPublique(BaseModel):
    id: str
    notion_parent_id: Optional[str] = None
    nom: str
    ordre: int
    regle_comportement: Optional[str] = None
    consigne_llm: Optional[str] = None


class ProgrammePublic(BaseModel):
    id: str
    publie_par: str
    nom: str
    description: str
    inclut_regles_consignes: bool
    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    classe: list[str] = []
    specialite: list[str] = []
    etoiles_count: int = 0
    created_at: str
    est_a_moi: bool = False
    mon_etoile: bool = False


class ProgrammePublicDetail(ProgrammePublic):
    notions: list[NotionPublique] = []


class ListeProgrammesPublics(BaseModel):
    programmes: list[ProgrammePublic]
    total: int


def _avec_etoile_et_proprietaire(lignes: list[dict], utilisateur) -> list[dict]:
    mon_id = utilisateur.id if utilisateur else None
    mes_etoiles = etoiles_utilisateur("programme", [l["id"] for l in lignes], mon_id) if lignes else set()
    for l in lignes:
        l["est_a_moi"] = mon_id is not None and l.get("publie_par") == mon_id
        l["mon_etoile"] = l["id"] in mes_etoiles
    return lignes


@router.get("", response_model=ListeProgrammesPublics)
def rechercher_programmes_catalogue_public(
    q: str | None = None, nombre: int = 15,
    pays: str | None = None, niveau: str | None = None, categorie: str | None = None, classe: str | None = None, specialite: str | None = None,
    utilisateur=Depends(utilisateur_optionnel),
):
    """Publique, jamais de 401 -- même philosophie que
    rechercher_comportements_publics. `q` absent ou vide = liste des
    plus récents (browse), `q` fourni = recherche par mot clé."""
    if (q or "").strip():
        lignes = chercher_programmes_catalogue_public(
            q.strip(), match_count=nombre, pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
        )
        total = len(lignes)
    else:
        resultat = lister_programmes_catalogue_public(
            limite=nombre, pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
        )
        lignes, total = resultat["programmes"], resultat["total"]
        # lister_programmes_catalogue_public n'inclut pas publie_par
        # (pas nécessaire au chat) -- rechargé ici pour est_a_moi.
    if lignes:
        complet = obtenir_programmes_publics_par_ids([l["id"] for l in lignes])
        lignes = [complet.get(l["id"], l) for l in lignes]
    return {"programmes": _avec_etoile_et_proprietaire(lignes, utilisateur), "total": total}


@router.get("/{entree_id}", response_model=ProgrammePublicDetail)
def lire_programme_catalogue_public_detail(entree_id: str, utilisateur=Depends(utilisateur_optionnel)):
    """Public, aucune auth requise -- pour consulter avant de récupérer."""
    entree = lire_programme_public(entree_id)
    if not entree:
        raise erreur_api(404, "PROGRAMME_PUBLIC_INTROUVABLE")
    entree["est_a_moi"] = utilisateur is not None and entree.get("publie_par") == utilisateur.id
    entree["mon_etoile"] = utilisateur is not None and bool(etoiles_utilisateur("programme", [entree_id], utilisateur.id))
    return entree


class PublierProgrammePayload(BaseModel):
    code_id: str
    nom: str
    description: str = ""
    inclure_regles_consignes: bool = False
    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    classe: list[str] = []
    specialite: list[str] = []


@router.post("", response_model=ProgrammePublic, status_code=201)
def publier_mon_programme(payload: PublierProgrammePayload, utilisateur=Depends(utilisateur_courant)):
    """Publie le Programme ENTIER d'un des codes de cet utilisateur (jamais une branche partielle)."""
    resultat = publier_programme_public(
        payload.code_id, utilisateur.id, payload.nom, payload.description, payload.inclure_regles_consignes,
        payload.pays, payload.niveau, payload.categorie, payload.classe, payload.specialite,
    )
    if resultat == "CODE_INTROUVABLE":
        raise erreur_api(404, "CODE_INTROUVABLE")
    if resultat == "NOM_REQUIS":
        raise erreur_api(400, "NOM_REQUIS")
    if resultat == "PROGRAMME_VIDE":
        raise erreur_api(400, "PROGRAMME_VIDE")
    resultat["est_a_moi"] = True
    resultat["mon_etoile"] = False
    return resultat


class ModifierProgrammePublicPayload(BaseModel):
    nom: Optional[str] = None
    description: Optional[str] = None
    pays: Optional[list[str]] = None
    niveau: Optional[list[str]] = None
    categorie: Optional[list[str]] = None
    classe: Optional[list[str]] = None
    specialite: Optional[list[str]] = None


@router.patch("/{entree_id}", response_model=ProgrammePublicDetail)
def modifier_mon_programme_public(entree_id: str, payload: ModifierProgrammePublicPayload, utilisateur=Depends(utilisateur_courant)):
    erreur = modifier_programme_public(
        entree_id, utilisateur.id,
        nom=payload.nom, description=payload.description,
        pays=payload.pays, niveau=payload.niveau, categorie=payload.categorie, classe=payload.classe, specialite=payload.specialite,
    )
    # 404 générique (ENTREE_INTROUVABLE ou pas propriétaire) : ne
    # jamais confirmer à un tiers qu'une entrée existe et appartient à
    # quelqu'un d'autre -- même principe que modifier_mon_skill_public.
    if erreur in ("ENTREE_INTROUVABLE", "CETTE_ENTREE_NE_T_APPARTIENT_PAS"):
        raise erreur_api(404, "PROGRAMME_PUBLIC_INTROUVABLE")
    if erreur == "NOM_REQUIS":
        raise erreur_api(400, "NOM_REQUIS")
    if erreur == "AUCUNE_MODIFICATION_FOURNIE":
        raise erreur_api(400, "AUCUNE_MODIFICATION_FOURNIE")
    entree = lire_programme_public(entree_id)
    entree["est_a_moi"] = True
    entree["mon_etoile"] = bool(etoiles_utilisateur("programme", [entree_id], utilisateur.id))
    return entree


@router.post("/{entree_id}/supprimer", status_code=204)
def supprimer_mon_programme_public(entree_id: str, utilisateur=Depends(utilisateur_courant)):
    if not supprimer_programme_public(entree_id, utilisateur.id):
        raise erreur_api(404, "PROGRAMME_PUBLIC_INTROUVABLE")


class CopierProgrammePayload(BaseModel):
    code_id: Optional[str] = None
    nouveau_code_nom: Optional[str] = None
    inclure_regles_consignes: bool = False


class ProgrammeCopie(BaseModel):
    code_id: str
    nb_notions: int


@router.post("/{entree_id}/copier-vers-perso", response_model=ProgrammeCopie, status_code=201)
def copier_programme_public_vers_mon_espace(entree_id: str, payload: CopierProgrammePayload, utilisateur=Depends(utilisateur_courant)):
    """Requiert un compte -- seule action gatée de ce router avec la publication, la recherche/lecture au-dessus restent publiques."""
    resultat = copier_programme_vers_perso(
        entree_id, utilisateur.id, code_id=payload.code_id, nouveau_code_nom=payload.nouveau_code_nom,
        inclure_regles_consignes=payload.inclure_regles_consignes,
    )
    if resultat == "ENTREE_INTROUVABLE":
        raise erreur_api(404, "PROGRAMME_PUBLIC_INTROUVABLE")
    if resultat == "CODE_INTROUVABLE":
        raise erreur_api(404, "CODE_INTROUVABLE")
    if resultat == "PROGRAMME_VIDE":
        raise erreur_api(400, "PROGRAMME_VIDE")
    return {"code_id": resultat["code_id"], "nb_notions": resultat["nb_notions"]}
