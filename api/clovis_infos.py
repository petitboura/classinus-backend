"""
Route REST pour l'état "étoiles" de Classinus lui-même (18/09/2026, étape
13 du chantier "profil contributeur bibliotheque publique"). Le nombre
de commentaires est déjà couvert par GET /api/commentaires-catalogue-
public (type_element="clovis") -- cet endpoint ne renvoie que ce que ce
dernier n'a pas : le compteur d'étoiles et si LA PERSONNE CONNECTÉE en a
déjà posé une (même besoin que mon_etoile sur les entrées de liste du
catalogue, voir core/dossiers_catalogue_public.py, mais ici il n'y a
qu'un seul élément fixe, pas une liste).

ID_CLOVIS doit rester synchronisé avec la ligne unique de la table
classinus_infos (voir migration clovis_infos_singleton_et_type_clovis).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant, supabase
from core.etoiles_catalogue_public import etoiles_utilisateur

router = APIRouter(prefix="/api/clovis-infos", tags=["clovis-infos"])

ID_CLOVIS = "00000000-0000-0000-0000-000000000001"


class ClovisInfos(BaseModel):
    etoiles_count: int
    mon_etoile: bool


@router.get("", response_model=ClovisInfos)
def obtenir(utilisateur=Depends(utilisateur_courant)):
    res = supabase.table("classinus_infos").select("etoiles_count").eq("id", ID_CLOVIS).maybe_single().execute()
    etoiles_count = (res.data or {}).get("etoiles_count", 0) if res else 0
    mon_etoile = ID_CLOVIS in etoiles_utilisateur("clovis", [ID_CLOVIS], utilisateur.id)
    return {"etoiles_count": etoiles_count, "mon_etoile": mon_etoile}
