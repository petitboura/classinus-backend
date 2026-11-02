"""Catalogue des skills actifs d'un utilisateur, annoncé à l'IA dans le prompt.

Seuls le nom et la description sont annoncés (chargement progressif, comme chez
Claude). Le contenu est lu à la demande par l'outil gerer_skill.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


# Skills officiels de Classinus (02/11/2026) : fournis par l'entreprise, identiques pour tous les
# comptes, en lecture seule. Même table que les skills personnels, portee = 'plateforme'.
_cache_officiels: dict = {"valeur": None, "expire": 0.0}
_verrou_cache = threading.Lock()


def _abreger(description: str) -> str:
    description = (description or "").strip()
    maximum = config_skills.CATALOGUE_DESCRIPTION_MAX
    if len(description) > maximum:
        return description[: maximum - 1].rstrip() + "…"
    return description


def vider_cache_officiels() -> None:
    """Oublie la liste gardée en mémoire (utilisé par le script de synchronisation et les tests)."""
    with _verrou_cache:
        _cache_officiels["valeur"], _cache_officiels["expire"] = None, 0.0


def lister_skills_officiels() -> list[dict]:
    """Skills officiels actifs : [{id, nom, description}]. Gardés en mémoire quelques secondes.

    Une erreur est consignée et rend la dernière liste connue, ou une liste vide : le chat ne
    doit jamais échouer parce que cette lecture a échoué. Une erreur n'est jamais gardée en cache.
    """
    maintenant = time.monotonic()
    with _verrou_cache:
        if _cache_officiels["valeur"] is not None and maintenant < _cache_officiels["expire"]:
            return _cache_officiels["valeur"]
        derniere = _cache_officiels["valeur"]
    try:
        res = (
            supabase.table("skills")
            .select("id,nom,description")
            .eq("portee", "plateforme")
            .eq("actif", True)
            .order("nom")
            .limit(config_skills.CATALOGUE_NB_MAX)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (catalogue skills officiels) : {e}")
        return derniere or []
    officiels = [
        {"id": l["id"], "nom": l.get("nom") or "", "description": _abreger(l.get("description"))}
        for l in (res.data or [])
    ]
    with _verrou_cache:
        _cache_officiels["valeur"] = officiels
        _cache_officiels["expire"] = time.monotonic() + config_skills.PLATEFORME_CACHE_SECONDES
    return officiels


def ne_plus_proposer_officiels(user_id: str | None) -> bool:
    """Vrai si l'utilisateur a demandé de ne plus lui signaler les skills officiels équivalents aux siens."""
    if not user_id:
        return False
    try:
        res = (
            supabase.table("preferences_skills_officiels")
            .select("ne_plus_proposer")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (préférence skills officiels {user_id}) : {e}")
        return False
    return bool(res and res.data and res.data.get("ne_plus_proposer"))


def lister_catalogue_complet(user_id: str | None) -> dict:
    """Catalogue annoncé à l'IA : skills de l'utilisateur, skills officiels et préférence.

    Renvoie {skills, total, officiels, ne_plus_proposer}. Les trois lectures sont indépendantes :
    elles partent en parallèle pour ne rien ajouter au temps d'attente du chat.
    """
    vide = {"skills": [], "total": 0, "officiels": [], "ne_plus_proposer": False}
    if not user_id:
        return vide
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_compte = pool.submit(lister_catalogue_skills, user_id)
        f_officiels = pool.submit(lister_skills_officiels)
        f_preference = pool.submit(ne_plus_proposer_officiels, user_id)
        catalogue = dict(f_compte.result())
        catalogue["officiels"] = f_officiels.result()
        catalogue["ne_plus_proposer"] = f_preference.result()
    return catalogue
