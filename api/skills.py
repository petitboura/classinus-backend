"""API de gestion des skills autonomes. Les contenus sont stockés dans R2."""
import mimetypes
import posixpath
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from api.auth import utilisateur_courant, supabase
from core import stockage_r2
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/skills", tags=["skills"])
BUCKET = "skills"

class Fichier(BaseModel):
    chemin: str = Field(min_length=1, max_length=500)
    contenu: str = Field(max_length=5 * 1024 * 1024)
    type_mime: str | None = None

class SkillPayload(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    actif: bool = True
    fichiers: list[Fichier] = Field(default_factory=list, max_length=200)

def _path(value: str) -> str:
    value = value.replace("\\", "/").strip("/")
    path = posixpath.normpath(value)
    if not value or path in (".", "..") or path.startswith("../") or path.startswith("/") or "\x00" in path:
        raise erreur_api(422, "CHEMIN_FICHIER_INVALIDE")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise erreur_api(422, "CHEMIN_FICHIER_INVALIDE")
    return path

def _owned(skill_id: str, owner_id: str) -> dict:
    try:
        row = supabase.table("skills").select("*").eq("id", skill_id).eq("owner_id", owner_id).maybe_single().execute()
    except Exception:
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_SKILL")
    if not row or not row.data:
        raise erreur_api(404, "SKILL_INTROUVABLE")
    return row.data

def _prepare(payload: SkillPayload) -> list[dict]:
    if not payload.nom.strip():
        raise erreur_api(422, "NOM_SKILL_REQUIS")
    files, seen, total = [], set(), 0
    for f in payload.fichiers:
        path = _path(f.chemin)
        if path in seen:
            raise erreur_api(422, "CHEMIN_FICHIER_DUPLIQUE")
        seen.add(path)
        data = f.contenu.encode("utf-8")
        total += len(data)
        if len(data) > 5 * 1024 * 1024 or total > 20 * 1024 * 1024:
            raise erreur_api(413, "SKILL_TROP_VOLUMINEUX")
        files.append({"chemin": path, "contenu": data, "type_mime": f.type_mime or mimetypes.guess_type(path)[0] or "application/octet-stream"})
    if "SKILL.md" not in seen:
        text = f"---\nname: {payload.nom}\ndescription: {payload.description}\n---\n\n"
        files.insert(0, {"chemin": "SKILL.md", "contenu": text.encode(), "type_mime": "text/markdown"})
    return files

def _upload(owner: str, skill_id: str, files: list[dict]) -> list[dict]:
    rows = []
    store = stockage_r2.from_(BUCKET)
    for f in files:
        key = f"{owner}/{skill_id}/{f['chemin']}"
        store.upload(key, f["contenu"], {"content-type": f["type_mime"]})
        rows.append({"skill_id": skill_id, "chemin": f["chemin"], "cle_stockage": key, "type_mime": f["type_mime"], "taille_octets": len(f["contenu"]), "updated_at": datetime.now(timezone.utc).isoformat()})
    return rows

def _files(skill_id: str, with_content: bool = False) -> list[dict]:
    try:
        rows = supabase.table("skill_files").select("*").eq("skill_id", skill_id).order("chemin").execute().data or []
    except Exception:
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_FICHIERS_SKILL")
    result = []
    for row in rows:
        item = {"chemin": row["chemin"], "type_mime": row.get("type_mime"), "taille_octets": row.get("taille_octets", 0), "mis_a_jour_le": row.get("updated_at")}
        if with_content:
            try:
                item["contenu"] = stockage_r2.from_(BUCKET).download(row["cle_stockage"]).decode("utf-8")
            except Exception:
                raise erreur_api(500, "IMPOSSIBLE_DE_LIRE_FICHIER_SKILL")
        result.append(item)
    return result

@router.get("")
def lister(utilisateur=Depends(utilisateur_courant)):
    rows = supabase.table("skills").select("id,nom,description,actif,created_at,updated_at").eq("owner_id", utilisateur.id).order("updated_at", desc=True).execute()
    return rows.data or []

@router.post("")
def creer(payload: SkillPayload, utilisateur=Depends(utilisateur_courant)):
    files = _prepare(payload)
    skill_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    row = {"id": skill_id, "owner_id": utilisateur.id, "nom": payload.nom.strip(), "description": payload.description.strip(), "actif": payload.actif, "created_at": now, "updated_at": now}
    try:
        file_rows = _upload(utilisateur.id, skill_id, files)
        supabase.table("skills").insert(row).execute()
        supabase.table("skill_files").insert(file_rows).execute()
    except Exception:
        try:
            stockage_r2.from_(BUCKET).remove([f"{utilisateur.id}/{skill_id}/{f['chemin']}" for f in files])
        except Exception:
            pass
        try:
            supabase.table("skills").delete().eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
        except Exception:
            pass
        raise erreur_api(500, "IMPOSSIBLE_DE_CREER_SKILL")
    return {**row, "fichiers": [{"chemin": f["chemin"], "type_mime": f["type_mime"], "taille_octets": len(f["contenu"])} for f in files]}

@router.get("/{skill_id}")
def obtenir(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    return {**_owned(skill_id, utilisateur.id), "fichiers": _files(skill_id, True)}

@router.put("/{skill_id}")
def modifier(skill_id: str, payload: SkillPayload, utilisateur=Depends(utilisateur_courant)):
    old = _owned(skill_id, utilisateur.id)
    files = _prepare(payload)
    store = stockage_r2.from_(BUCKET)
    old_rows = supabase.table("skill_files").select("cle_stockage").eq("skill_id", skill_id).execute().data or []
    new_rows = _upload(utilisateur.id, skill_id, files)
    try:
        supabase.table("skill_files").delete().eq("skill_id", skill_id).execute()
        supabase.table("skill_files").insert(new_rows).execute()
        changes = {"nom": payload.nom.strip(), "description": payload.description.strip(), "actif": payload.actif, "updated_at": datetime.now(timezone.utc).isoformat()}
        supabase.table("skills").update(changes).eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
    except Exception:
        for row in new_rows:
            try: store.remove([row["cle_stockage"]])
            except Exception: pass
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_SKILL")
    for row in old_rows:
        try: store.remove([row["cle_stockage"]])
        except Exception: pass
    return {**old, "nom": payload.nom.strip(), "description": payload.description.strip(), "actif": payload.actif, "fichiers": [{"chemin": f["chemin"], "type_mime": f["type_mime"], "taille_octets": len(f["contenu"])} for f in files]}

@router.delete("/{skill_id}")
def supprimer(skill_id: str, utilisateur=Depends(utilisateur_courant)):
    _owned(skill_id, utilisateur.id)
    rows = supabase.table("skill_files").select("cle_stockage").eq("skill_id", skill_id).execute().data or []
    supabase.table("skills").delete().eq("id", skill_id).eq("owner_id", utilisateur.id).execute()
    for row in rows:
        try: stockage_r2.from_(BUCKET).remove([row["cle_stockage"]])
        except Exception: pass
    return {"supprime": True, "id": skill_id}
