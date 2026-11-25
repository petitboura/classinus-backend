"""Catalogue public des skills (24/11/2026, demande de Bourama).

Un skill est publié depuis la page Skills de son auteur ou par l'IA. Cette route sert la
recherche (publique, sans compte), le détail d'un skill public, l'ajout chez soi (compte
obligatoire) et la mise à jour d'une copie. La logique est dans core/skills_publics.py, la même
que celle de l'outil de l'IA : l'IA et la page obéissent donc aux mêmes règles.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant, utilisateur_optionnel
from core import skills_publics
from core.etoiles_catalogue_public import etoiles_utilisateur

router = APIRouter(prefix="/api/skills-publics", tags=["skills_publics"])


class SkillPublicResume(BaseModel):
    id: str
    nom: str
    description: str = ""
    activations_count: int = 0
    etoiles_count: int = 0
    version_publique: int = 1
    publie_le: str | None = None
    est_a_moi: bool = False
    mon_etoile: bool = False


class FichierPublic(BaseModel):
    chemin: str
    type_mime: str | None = None
    taille_octets: int = 0


class SkillPublicDetail(SkillPublicResume):
    skill_md: str = ""
    fichiers: list[FichierPublic] = []


class StatutPublication(BaseModel):
    id: str
    visibilite: str
    publie_le: str | None = None
    retire_le: str | None = None


class AjoutSkillPublic(BaseModel):
    id: str
    nom: str
    description: str = ""
    deja_ajoute: bool


class MiseAJourDisponible(BaseModel):
    copie_id: str
    source_id: str
    nom: str
    modifiee_localement: bool


class MiseAJourFaite(BaseModel):
    copie_id: str
    nom: str
    version: int


def _resume(ligne: dict, mon_id: str | None, mes_etoiles: set) -> dict:
    return {
        **ligne,
        "description": ligne.get("description") or "",
        "est_a_moi": mon_id is not None and ligne.get("owner_id") == mon_id,
        "mon_etoile": ligne["id"] in mes_etoiles,
    }


@router.get("", response_model=list[SkillPublicResume])
def rechercher_skills_publics(q: str | None = None, utilisateur=Depends(utilisateur_optionnel)):
    """Recherche publique, jamais de 401 : un visiteur sans compte peut parcourir le catalogue.
    est_a_moi n'est calculé que si un visiteur connecté regarde (bouton Retirer réservé à l'auteur)."""
    lignes = skills_publics.chercher(q or "")
    mon_id = utilisateur.id if utilisateur else None
    mes_etoiles = etoiles_utilisateur("skill", [l["id"] for l in lignes], mon_id)
    return [_resume(l, mon_id, mes_etoiles) for l in lignes]


# Déclarée avant /{identifiant}, sinon "mises-a-jour" serait lu comme un identifiant de skill.
@router.get("/mises-a-jour", response_model=list[MiseAJourDisponible])
def lister_mises_a_jour(utilisateur=Depends(utilisateur_courant)):
    return skills_publics.mises_a_jour_disponibles(utilisateur.id)


@router.get("/{identifiant}", response_model=SkillPublicDetail)
def obtenir_skill_public(identifiant: str, utilisateur=Depends(utilisateur_optionnel)):
    """Détail d'un skill public pour la page /skills/[id]. Accepte aussi l'ancien identifiant du
    catalogue (legacy_public_id), pour que les anciens liens partagés continuent de marcher."""
    detail = skills_publics.obtenir(identifiant)
    lecture = skills_publics.lire_fichier(detail["id"])
    mon_id = utilisateur.id if utilisateur else None
    mes_etoiles = etoiles_utilisateur("skill", [detail["id"]], mon_id)
    return {**_resume(detail, mon_id, mes_etoiles), "skill_md": lecture.get("contenu") or "", "fichiers": detail["fichiers"]}


@router.post("/{skill_id}/publier", response_model=StatutPublication)
def publier_mon_skill(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    return skills_publics.publier(skill_id, utilisateur.id)


@router.post("/{skill_id}/retirer", response_model=StatutPublication)
def retirer_mon_skill(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    return skills_publics.retirer(skill_id, utilisateur.id)


@router.post("/{identifiant}/activer", response_model=AjoutSkillPublic, status_code=201)
def ajouter_skill_public(identifiant: str, utilisateur=Depends(utilisateur_courant)):
    """Ajoute le skill aux skills de l'utilisateur (copie indépendante). Compte obligatoire."""
    resultat = skills_publics.activer(identifiant, utilisateur.id)
    copie = resultat["copie"]
    return {"id": copie["id"], "nom": copie["nom"], "description": copie.get("description") or "", "deja_ajoute": resultat["deja_ajoute"]}


@router.post("/{copie_id}/mettre-a-jour", response_model=MiseAJourFaite)
def mettre_a_jour_ma_copie(copie_id: str, utilisateur=Depends(utilisateur_courant)):
    """Remplace la copie par la version publique actuelle. Le frontend ne l'appelle qu'après un
    accord explicite de l'utilisateur, car ses propres modifications de la copie sont remplacées."""
    return skills_publics.mettre_a_jour_copie(copie_id, utilisateur.id)
