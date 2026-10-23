"""Copie idempotente des skills historiques vers R2 et les tables dédiées.
À exécuter après la migration SQL avec les variables SUPABASE_* et R2_*.
Aucune ligne historique n'est supprimée ni modifiée.
"""
import logging, os, re, unicodedata
from datetime import datetime, timezone
from supabase import create_client
from core import stockage_r2

logging.basicConfig(level=logging.INFO)
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET"])
bucket = stockage_r2.from_("skills")

def slug(nom):
    s = unicodedata.normalize("NFKD", nom or "skill").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-")[:100] or "skill"

def migrer(row, public=False):
    legacy_id = row["id"]
    colonne = "legacy_public_id" if public else "legacy_behavior_id"
    existing = db.table("skills").select("id").eq(colonne, legacy_id).maybe_single().execute()
    if existing.data:
        return "deja_migre"
    owner = row.get("auteur_id") if public else row.get("etudiant_id")
    if not owner:
        logging.warning("Skill historique %s ignoré, propriétaire absent", legacy_id)
        return "ignore"
    nom = (row.get("nom") or "Skill").strip()[:120] or "Skill"
    description = row.get("description") or ""
    contenu = row.get("skill_md") or f"---\nname: {slug(nom)}\ndescription: {description}\n---\n\n{row.get('texte') or ''}\n"
    cle = f"{owner}/{legacy_id}/SKILL.md"
    bucket.upload(cle, contenu.encode("utf-8"), {"content-type": "text/markdown"})
    donnees = {"id": legacy_id, "owner_id": owner, "nom": nom, "description": description,
      "actif": bool(row.get("actif", True)) if not public else True, colonne: legacy_id,
      "created_at": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
      "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        db.table("skills").insert(donnees).execute()
        db.table("skill_files").insert({"skill_id": legacy_id, "chemin": "SKILL.md", "cle_stockage": cle,
          "type_mime": "text/markdown", "taille_octets": len(contenu.encode("utf-8"))}).execute()
    except Exception:
        bucket.remove([cle])
        raise
    return "migre"

def main():
    stats = {"migre": 0, "deja_migre": 0, "ignore": 0}
    classiques = db.table("comportements_etudiants").select("*").is_("categorie", "null").execute().data or []
    publics = db.table("comportements_publics").select("*").execute().data or []
    for row in classiques:
        stats[migrer(row)] += 1
    for row in publics:
        stats[migrer(row, True)] += 1
    logging.info("Migration skills terminée : %s", stats)

if __name__ == "__main__":
    main()
