"""Catalogue des skills actifs d'un utilisateur, annoncé à l'IA dans le prompt.

Seuls le nom et la description sont annoncés (chargement progressif, comme chez
Claude). Le contenu est lu à la demande par l'outil gerer_skill.
"""
import logging

from api.auth import supabase
from core import config_skills


def lister_catalogue_skills(user_id: str | None) -> dict:
    """Renvoie {"skills": [{id, nom, description}], "total": int} pour les skills actifs.

    Toute erreur est consignée et donne un catalogue vide : le chat ne doit jamais
    échouer parce que cette lecture a échoué.
    """
    vide = {"skills": [], "total": 0}
    if not user_id:
        return vide
    try:
        res = (
            supabase.table("skills")
            .select("id,nom,description", count="exact")
            .eq("owner_id", user_id)
            .eq("actif", True)
            .order("nom")
            .limit(config_skills.CATALOGUE_NB_MAX)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (catalogue skills {user_id}) : {e}")
        return vide
    lignes = res.data or []
    maximum = config_skills.CATALOGUE_DESCRIPTION_MAX
    skills = []
    for ligne in lignes:
        description = (ligne.get("description") or "").strip()
        if len(description) > maximum:
            description = description[: maximum - 1].rstrip() + "…"
        skills.append({"id": ligne["id"], "nom": ligne.get("nom") or "", "description": description})
    total = getattr(res, "count", None)
    return {"skills": skills, "total": total if isinstance(total, int) else len(skills)}
