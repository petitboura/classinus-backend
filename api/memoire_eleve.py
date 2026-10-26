"""
Ecran "Ma memoire" de l'eleve (27/09/2026, chantier memoire eleve, puis
fusion avec l'ancien ecran le 29/09/2026 : il n'y a plus qu'un seul
systeme de memoire, celui de core/memoire_eleve.py).

Quatre routes :
- GET /api/memoire-eleve : tout ce que Classinus retient de l'eleve
  connecte, groupe par categorie. Les categories sont libres
  (29/10/2026) : seules celles creees par Classinus apparaissent.
- DELETE /api/memoire-eleve/{categorie} : oublie une categorie entiere
  (sa ligne racine et toutes ses sous-categories).
- DELETE /api/memoire-eleve : oublie tout.
- PUT /api/memoire-eleve/{categorie} : remplace le contenu d'UNE ligne
  existante (18/10/2026, demande de Bourama : le menu "..." de chaque
  categorie propose Editer en plus d'Oublier). Remplace la decision du
  29/09/2026 (lecture seule). La description de la ligne n'est pas
  modifiable ici, elle reste celle ecrite par le modele.
"""

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth import utilisateur_courant, supabase
from api.journal import journaliser
from core.erreurs import erreur_api
from core.memoire_eleve import ecrire_categorie

router = APIRouter(prefix="/api/memoire-eleve", tags=["memoire_eleve"])

# Meme convention que core/memoire_eleve.py : la ligne racine d'une
# categorie a une sous_categorie egale a la chaine vide en base, jamais NULL.
_RACINE = ""


class LignePayload(BaseModel):
    sous_categorie: str | None
    contenu: dict
    description: str
    updated_at: str


class CategoriePayload(BaseModel):
    categorie: str
    lignes: list[LignePayload]


class MemoirePayload(BaseModel):
    categories: list[CategoriePayload]


@router.get("", response_model=MemoirePayload)
def obtenir_ma_memoire(utilisateur=Depends(utilisateur_courant)):
    """
    Liste vide pour une categorie sans rien de note, pas une erreur : le
    frontend affiche alors un etat "rien retenu ici" plutot qu'un message
    d'erreur.
    """
    try:
        lignes = (
            supabase.table("memoire_eleve")
            .select("categorie, sous_categorie, contenu, description, updated_at")
            .eq("user_id", utilisateur.id)
            .execute()
        ).data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture memoire_eleve user={utilisateur.id}) : {e}")
        raise erreur_api(500, "MEMOIRE_ELEVE_LECTURE_ECHEC")

    par_categorie: dict[str, list[dict]] = {}
    for ligne in lignes:
        par_categorie.setdefault(ligne["categorie"], []).append(ligne)

    categories = []
    for categorie in sorted(par_categorie):
        lignes_categorie = sorted(par_categorie[categorie], key=lambda l: l["sous_categorie"] or _RACINE)
        categories.append(
            CategoriePayload(
                categorie=categorie,
                lignes=[
                    LignePayload(
                        sous_categorie=l["sous_categorie"] or None,
                        contenu=l.get("contenu") or {},
                        description=l.get("description") or "",
                        updated_at=l.get("updated_at") or "",
                    )
                    for l in lignes_categorie
                ],
            )
        )
    return MemoirePayload(categories=categories)


class EditionPayload(BaseModel):
    sous_categorie: str | None = None
    contenu: dict


@router.put("/{categorie}", status_code=204)
def modifier_une_ligne(
    categorie: str,
    payload: EditionPayload,
    request: Request,
    utilisateur=Depends(utilisateur_courant),
):
    """Remplace le contenu d'une ligne qui existe deja (jamais de creation ici)."""
    sous = payload.sous_categorie or _RACINE
    try:
        existantes = (
            supabase.table("memoire_eleve")
            .select("description")
            .eq("user_id", utilisateur.id)
            .eq("categorie", categorie)
            .eq("sous_categorie", sous)
            .execute()
        ).data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture avant edition memoire_eleve {categorie} user={utilisateur.id}) : {e}")
        raise erreur_api(500, "MEMOIRE_ELEVE_LECTURE_ECHEC")
    if not existantes:
        raise erreur_api(404, "MEMOIRE_ELEVE_LIGNE_INTROUVABLE")

    succes, _message = ecrire_categorie(
        utilisateur.id, categorie, payload.sous_categorie, payload.contenu, existantes[0].get("description") or ""
    )
    if not succes:
        raise erreur_api(500, "MEMOIRE_ELEVE_EDITION_ECHEC")

    journaliser(
        action="memoire.ligne_editee_par_user",
        user_id=utilisateur.id,
        cible_type="profile",
        cible_id=utilisateur.id,
        details={"categorie": categorie, "sous_categorie": sous},
        request=request,
    )


@router.delete("/{categorie}", status_code=204)
def oublier_une_categorie(categorie: str, request: Request, utilisateur=Depends(utilisateur_courant)):
    try:
        (
            supabase.table("memoire_eleve")
            .delete()
            .eq("user_id", utilisateur.id)
            .eq("categorie", categorie)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (delete memoire_eleve {categorie} user={utilisateur.id}) : {e}")
        raise erreur_api(500, "MEMOIRE_ELEVE_EFFACEMENT_ECHEC")

    journaliser(
        action="memoire.categorie_effacee_par_user",
        user_id=utilisateur.id,
        cible_type="profile",
        cible_id=utilisateur.id,
        details={"categorie": categorie},
        request=request,
    )


@router.delete("", status_code=204)
def tout_oublier(request: Request, utilisateur=Depends(utilisateur_courant)):
    try:
        supabase.table("memoire_eleve").delete().eq("user_id", utilisateur.id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (delete memoire_eleve user={utilisateur.id}) : {e}")
        raise erreur_api(500, "MEMOIRE_ELEVE_EFFACEMENT_ECHEC")

    journaliser(
        action="memoire.effacee_par_user",
        user_id=utilisateur.id,
        cible_type="profile",
        cible_id=utilisateur.id,
        request=request,
    )
