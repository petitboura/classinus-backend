"""API de gestion des skills autonomes. Les contenus sont stockés dans R2.

Chaque version d'un fichier est écrite sous une clé R2 unique
(proprietaire/skill/version/chemin). Une modification ne touche donc jamais
à l'ancien contenu tant que la base n'a pas suivi : en cas d'échec, l'ancienne
version reste intacte et lisible.
"""
import json
import logging
import mimetypes
import posixpath
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant, supabase
from core import config_skills, stockage_r2
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/skills", tags=["skills"])


# Réglages dans core/config_skills.py (variables d'environnement SKILLS_*).
BUCKET = config_skills.BUCKET
TAILLE_FICHIER_MAX = config_skills.TAILLE_FICHIER_MAX
TAILLE_TOTALE_MAX = config_skills.TAILLE_TOTALE_MAX
NB_FICHIERS_MAX = config_skills.NB_FICHIERS_MAX
NB_SKILLS_MAX = config_skills.NB_SKILLS_MAX
TELECHARGEMENTS_PARALLELES = config_skills.TELECHARGEMENTS_PARALLELES


class Fichier(BaseModel):
    chemin: str = Field(min_length=1, max_length=500)
    contenu: str = Field(max_length=TAILLE_FICHIER_MAX)
    type_mime: str | None = None


class SkillPayload(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    actif: bool = True
    fichiers: list[Fichier] = Field(default_factory=list, max_length=NB_FICHIERS_MAX)


def _erreur_taille() -> Exception:
    return erreur_api(
        413, "SKILL_TROP_VOLUMINEUX",
        total_mo=TAILLE_TOTALE_MAX // (1024 * 1024),
        fichier_mo=TAILLE_FICHIER_MAX // (1024 * 1024),
    )


def _path(value: str) -> str:
    value = value.replace("\\", "/").strip("/")
    path = posixpath.normpath(value)
    if not value or path in (".", "..") or path.startswith("../") or path.startswith("/") or "\x00" in path:
        raise erreur_api(422, "CHEMIN_FICHIER_INVALIDE")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise erreur_api(422, "CHEMIN_FICHIER_INVALIDE")
    return path


def _texte_une_ligne(valeur: str) -> bool:
    return not any(c in valeur for c in ("\n", "\r", "\x00"))


def _entete(nom: str, description: str) -> str:
    # Guillemets JSON : valides en YAML et sans risque d'injection d'une autre clé.
    return f"---\nname: {json.dumps(nom, ensure_ascii=False)}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n"


def _owned(skill_id: str, owner_id: str) -> dict:
    try:
        row = supabase.table("skills").select("*").eq("id", skill_id).eq("owner_id", owner_id).maybe_single().execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (chargement skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_SKILL")
    if not row or not row.data:
        raise erreur_api(404, "SKILL_INTROUVABLE")
    return row.data


def _prepare(payload: SkillPayload) -> list[dict]:
    nom, description = payload.nom.strip(), payload.description.strip()
    if not nom:
        raise erreur_api(422, "NOM_SKILL_REQUIS")
    if not _texte_une_ligne(nom) or not _texte_une_ligne(description):
        raise erreur_api(422, "NOM_SKILL_INVALIDE")
    # Les caractères sont toujours au plus aussi nombreux que les octets : si
    # leur somme dépasse déjà le plafond, on refuse avant tout encodage.
    if sum(len(f.contenu) for f in payload.fichiers) > TAILLE_TOTALE_MAX:
        raise _erreur_taille()
    files, seen, total = [], set(), 0
    for f in payload.fichiers:
        path = _path(f.chemin)
        if path in seen:
            raise erreur_api(422, "CHEMIN_FICHIER_DUPLIQUE")
        seen.add(path)
        data = f.contenu.encode("utf-8")
        total += len(data)
        if len(data) > TAILLE_FICHIER_MAX or total > TAILLE_TOTALE_MAX:
            raise _erreur_taille()
        files.append({"chemin": path, "contenu": data, "type_mime": f.type_mime or mimetypes.guess_type(path)[0] or "application/octet-stream"})
    if "SKILL.md" not in seen:
        files.insert(0, {"chemin": "SKILL.md", "contenu": _entete(nom, description).encode("utf-8"), "type_mime": "text/markdown"})
    return files


def _supprimer_cles(cles: list[str], contexte: str) -> None:
    """Suppression R2 au mieux : un échec est consigné, jamais montré à l'utilisateur."""
    if not cles:
        return
    try:
        stockage_r2.from_(BUCKET).remove(cles)
    except Exception as e:
        logging.error(f"ERREUR R2 ({contexte}, {len(cles)} objet(s) orphelin(s) possible(s) : {cles[:5]}) : {e}")


def _upload(owner: str, skill_id: str, files: list[dict]) -> list[dict]:
    """Envoie chaque fichier sous une clé de version unique. Tout ou rien."""
    rows, version = [], uuid.uuid4().hex[:12]
    store = stockage_r2.from_(BUCKET)
    try:
        for f in files:
            key = f"{owner}/{skill_id}/{version}/{f['chemin']}"
            store.upload(key, f["contenu"], {"content-type": f["type_mime"]})
            rows.append({"skill_id": skill_id, "chemin": f["chemin"], "cle_stockage": key, "type_mime": f["type_mime"], "taille_octets": len(f["contenu"]), "updated_at": datetime.now(timezone.utc).isoformat()})
    except Exception:
        _supprimer_cles([r["cle_stockage"] for r in rows], "annulation envoi skill")
        raise
    return rows


def _lire(row: dict) -> dict:
    item = {"chemin": row["chemin"], "type_mime": row.get("type_mime"), "taille_octets": row.get("taille_octets", 0), "mis_a_jour_le": row.get("updated_at")}
    try:
        brut = stockage_r2.from_(BUCKET).download(row["cle_stockage"])
    except Exception as e:
        logging.error(f"ERREUR R2 (lecture fichier skill {row.get('cle_stockage')}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_LIRE_FICHIER_SKILL")
    try:
        item["contenu"], item["binaire"] = brut.decode("utf-8"), False
    except UnicodeDecodeError:
        # Fichier non texte : listé, mais sans contenu, pour ne pas bloquer tout le skill.
        item["contenu"], item["binaire"] = None, True
    return item


def _files(skill_id: str, with_content: bool = False) -> list[dict]:
    try:
        rows = supabase.table("skill_files").select("*").eq("skill_id", skill_id).order("chemin").execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fichiers skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_FICHIERS_SKILL")
    if not with_content:
        return [{"chemin": r["chemin"], "type_mime": r.get("type_mime"), "taille_octets": r.get("taille_octets", 0), "mis_a_jour_le": r.get("updated_at")} for r in rows]
    with ThreadPoolExecutor(max_workers=TELECHARGEMENTS_PARALLELES) as pool:
        return list(pool.map(_lire, rows))


def _resume(files: list[dict]) -> list[dict]:
    return [{"chemin": f["chemin"], "type_mime": f["type_mime"], "taille_octets": len(f["contenu"])} for f in files]


@router.get("")
def lister(utilisateur=Depends(utilisateur_courant)):
    try:
        rows = supabase.table("skills").select("id,nom,description,actif,created_at,updated_at").eq("owner_id", utilisateur.id).order("updated_at", desc=True).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (liste skills {utilisateur.id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_LISTER_SKILLS")
    return rows.data or []


@router.post("")
def creer(payload: SkillPayload, utilisateur=Depends(utilisateur_courant)):
    files = _prepare(payload)
    try:
        nb = supabase.table("skills").select("id", count="exact").eq("owner_id", utilisateur.id).limit(1).execute().count or 0
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (comptage skills {utilisateur.id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CREER_SKILL")
    if nb >= NB_SKILLS_MAX:
        raise erreur_api(409, "SKILLS_LIMITE_ATTEINTE", maximum=NB_SKILLS_MAX)
    skill_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    row = {"id": skill_id, "owner_id": utilisateur.id, "nom": payload.nom.strip(), "description": payload.description.strip(), "actif": payload.actif, "created_at": now, "updated_at": now}
    file_rows: list[dict] = []
    try:
        file_rows = _upload(utilisateur.id, skill_id, files)
        supabase.table("skills").insert(row).execute()
        supabase.table("skill_files").insert(file_rows).execute()
    except Exception as e:
        logging.error(f"ERREUR création skill {skill_id} : {e}")
        _supprimer_cles([r["cle_stockage"] for r in file_rows], "annulation création skill")
        try:
            supabase.table("skills").delete().eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
        except Exception as e2:
            logging.error(f"ERREUR SUPABASE (nettoyage skill {skill_id}) : {e2}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CREER_SKILL")
    return {**row, "fichiers": _resume(files)}


@router.get("/{skill_id}")
def obtenir(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    return {**_owned(skill_id, utilisateur.id), "fichiers": _files(skill_id, True)}


@router.put("/{skill_id}")
def modifier(skill_id: str, payload: SkillPayload, utilisateur=Depends(utilisateur_courant)):
    old = _owned(skill_id, utilisateur.id)
    files = _prepare(payload)
    try:
        old_rows = supabase.table("skill_files").select("chemin,cle_stockage").eq("skill_id", skill_id).execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (anciens fichiers skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_SKILL")
    # 1. Nouveaux contenus sous de nouvelles clés : l'ancienne version n'est pas touchée.
    try:
        new_rows = _upload(utilisateur.id, skill_id, files)
    except Exception as e:
        logging.error(f"ERREUR R2 (envoi modification skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_SKILL")
    nouveaux_chemins = {r["chemin"] for r in new_rows}
    # 2. Bascule des lignes vers les nouvelles clés, en une seule requête.
    try:
        supabase.table("skill_files").upsert(new_rows, on_conflict="skill_id,chemin").execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (bascule fichiers skill {skill_id}) : {e}")
        _supprimer_cles([r["cle_stockage"] for r in new_rows], "annulation modification skill")
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_SKILL")
    # À partir d'ici la base pointe vers les nouvelles clés : on ne les supprime plus jamais.
    changes = {"nom": payload.nom.strip(), "description": payload.description.strip(), "actif": payload.actif, "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        retires = [r["chemin"] for r in old_rows if r["chemin"] not in nouveaux_chemins]
        if retires:
            supabase.table("skill_files").delete().eq("skill_id", skill_id).in_("chemin", retires).execute()
        supabase.table("skills").update(changes).eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fin modification skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_SKILL")
    # 3. Seulement maintenant, les anciennes clés sont supprimées.
    _supprimer_cles([r["cle_stockage"] for r in old_rows], "anciens fichiers skill")
    return {**old, **changes, "fichiers": _resume(files)}


@router.delete("/{skill_id}")
def supprimer(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    _owned(skill_id, utilisateur.id)
    try:
        rows = supabase.table("skill_files").select("cle_stockage").eq("skill_id", skill_id).execute().data or []
        supabase.table("skills").delete().eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (suppression skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_SUPPRIMER_SKILL")
    _supprimer_cles([r["cle_stockage"] for r in rows], f"suppression skill {skill_id}")
    return {"supprime": True, "id": skill_id}
