"""
Chantier "mémoire élève" (27/09/2026, demande Bourama), Lot E, écran
élève minimal : progression par matière, à partir des lignes
`apprentissage.*` de sa propre mémoire (voir core/memoire_eleve.py).
Volontairement minimal (décision explicite de Bourama, pas de vue
admin/analytics, pas d'historique QCM détaillé ici) : une seule route,
lecture seule, rien d'autre pour cette première version.

Contrairement à api/memoire.py (ancien système, conversation_summaries,
résumé unique en texte libre), cette route ne lit QUE la catégorie
`apprentissage` de la nouvelle mémoire structurée, pas les catégories
identite/scolarite/preferences, qui n'ont pas leur place sur un écran de
progression.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant, supabase
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/memoire-eleve", tags=["memoire_eleve"])


class MatierePayload(BaseModel):
    sous_categorie: str
    contenu: dict
    description: str
    updated_at: str


class ProgressionPayload(BaseModel):
    matieres: list[MatierePayload]


@router.get("/progression", response_model=ProgressionPayload)
def obtenir_ma_progression(utilisateur=Depends(utilisateur_courant)):
    """
    Une entrée par sous-catégorie déjà notée sous `apprentissage` pour
    l'élève connecté (une par matière en pratique, ex. sous_categorie=
    "maths"). Liste vide si rien n'a encore été noté, pas une erreur,
    le frontend affiche alors un état "pas encore de suivi" plutôt qu'un
    message d'erreur.
    """
    try:
        lignes = (
            supabase.table("memoire_eleve")
            .select("sous_categorie, contenu, description, updated_at")
            .eq("user_id", utilisateur.id)
            .eq("categorie", "apprentissage")
            .neq("sous_categorie", "")
            .order("sous_categorie")
            .execute()
        ).data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture progression memoire_eleve user={utilisateur.id}) : {e}")
        raise erreur_api(500, "MEMOIRE_ELEVE_LECTURE_ECHEC")

    return ProgressionPayload(matieres=[MatierePayload(**l) for l in lignes])
