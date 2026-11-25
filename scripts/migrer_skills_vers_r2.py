"""Copie des skills historiques vers R2 et les tables dédiées (skills, skill_files).

Sources, jamais modifiées ni supprimées :
  - comportements_etudiants (categorie nulle) : skills privés, visibilite 'prive'
  - comportements_publics : skills publiés, visibilite 'public' ou 'retire' selon
    leur statut, avec leurs compteurs. Une seule ligne par skill public, pas de
    copie privée en plus.

Par défaut c'est une SIMULATION : rien n'est écrit. Pour écrire :
    python -m scripts.migrer_skills_vers_r2 --executer
Le SKILL.md de chaque skill est rangé dans un dossier qui porte son nom exact, avec
le nom et la description actuels dans l'en-tête.
Avant d'écrire, les lignes sources sont sauvegardées dans un fichier JSON.
Après l'écriture, les comptages avant et après sont comparés et chaque fichier
R2 est relu. Relançable sans risque : une ligne déjà migrée est ignorée.

Variables : SUPABASE_URL, SUPABASE_SECRET, R2_* (comme le backend).
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from supabase import create_client

from core import config_skills, stockage_r2
from core.skills_entete import appliquer_entete

logging.basicConfig(level=logging.INFO, format="%(message)s")


def dossier_du_skill(nom: str) -> str:
    """Dossier du skill dans R2 : son nom exact. Seuls les caractères qui casseraient
    la clé (séparateurs de chemin, caractères de contrôle) sont remplacés par une espace."""
    propre = "".join(" " if (c in "/\\" or ord(c) < 32) else c for c in nom).strip(" .")
    return propre or "Skill"


def _contenu(row: dict, nom: str, description: str) -> str:
    brut = row.get("skill_md") or ""
    if not brut.strip():
        brut = row.get("texte") or ""
    return appliquer_entete(brut, nom, description)


def preparer(row: dict, public: bool) -> dict | None:
    """Transforme une ligne historique en ligne `skills`. None si elle est inutilisable."""
    owner = row.get("auteur_id") if public else row.get("etudiant_id")
    if not owner:
        return None
    nom = (row.get("nom") or "Skill").strip().replace("\n", " ")[:120] or "Skill"
    description = (row.get("description") or "").strip().replace("\n", " ")[:1000]
    donnees = {
        "id": row["id"],
        "owner_id": owner,
        "nom": nom,
        "description": description,
        "actif": True,
        "visibilite": "prive",
        "legacy_public_id" if public else "legacy_behavior_id": row["id"],
        "created_at": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if public:
        publie = row.get("statut") == "publie"
        donnees.update({
            "visibilite": "public" if publie else "retire",
            "actif": publie,
            "publie_le": row.get("created_at"),
            "retire_le": row.get("retire_le"),
            "activations_count": row.get("activations_count") or 0,
            "etoiles_count": row.get("etoiles_count") or 0,
            "cta_count": row.get("cta_count") or 0,
            "partages_count": row.get("partages_count") or 0,
        })
    else:
        donnees["actif"] = bool(row.get("actif", True))
    return {"skill": donnees, "contenu": _contenu(row, nom, description)}


def deja_migre(db, colonne: str, valeur: str) -> bool:
    res = db.table("skills").select("id").eq(colonne, valeur).limit(1).execute()
    return bool(res and res.data)


def ecrire(db, bucket, plan: dict) -> None:
    skill, contenu = plan["skill"], plan["contenu"].encode("utf-8")
    cle = f"{skill['owner_id']}/{skill['id']}/{dossier_du_skill(skill['nom'])}/SKILL.md"
    bucket.upload(cle, contenu, {"content-type": "text/markdown"})
    try:
        db.table("skills").insert(skill).execute()
        db.table("skill_files").insert({"skill_id": skill["id"], "chemin": "SKILL.md", "cle_stockage": cle,
                                        "type_mime": "text/markdown", "taille_octets": len(contenu)}).execute()
        if bucket.download(cle) != contenu:
            raise RuntimeError("relecture R2 différente de l'original")
    except Exception:
        try:
            db.table("skills").delete().eq("id", skill["id"]).execute()
        except Exception:
            pass
        try:
            bucket.remove([cle])
        except Exception:
            pass
        raise


def lier_activations(db, executer: bool) -> dict:
    """Recrée dans skill_activations le lien des ajouts faits avant la migration.

    Source : comportement_public_activations (jamais modifiée). Une activation relie le skill public
    (même id avant et après migration) à la copie de l'utilisateur, qui est un skill migré dont
    legacy_behavior_id vaut l'ancien comportement. Sans ce lien, l'IA ne saurait pas que la copie vient
    du catalogue et ne préviendrait pas d'une mise à jour. Une activation dont la source ou la copie n'est
    pas (encore) dans skills est ignorée et comptée : relancer le script après les avoir migrées les relie.
    Relançable : une copie déjà reliée est ignorée.
    """
    bilan = {"a_lier": 0, "deja_lies": 0, "ignores": 0, "lies": 0}
    for a in db.table("comportement_public_activations").select("*").execute().data or []:
        if not a.get("comportement_etudiant_id") or not a.get("comportement_public_id") or not a.get("active_par"):
            bilan["ignores"] += 1
            continue
        copie = db.table("skills").select("id").eq("legacy_behavior_id", a["comportement_etudiant_id"]).maybe_single().execute()
        source = db.table("skills").select("id").eq("id", a["comportement_public_id"]).maybe_single().execute()
        if not (copie and copie.data) or not (source and source.data):
            bilan["ignores"] += 1
            continue
        if db.table("skill_activations").select("id").eq("copie_id", copie.data["id"]).maybe_single().execute().data:
            bilan["deja_lies"] += 1
            continue
        bilan["a_lier"] += 1
        if executer:
            maintenant = datetime.now(timezone.utc).isoformat()
            db.table("skill_activations").insert({
                "skill_source_id": source.data["id"], "copie_id": copie.data["id"], "active_par": a["active_par"],
                "version_copiee": 1, "synchronise_le": maintenant,
            }).execute()
            bilan["lies"] += 1
    return bilan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executer", action="store_true", help="écrit vraiment (sinon simulation)")
    parser.add_argument("--sauvegarde", default="sauvegardes_skills", help="dossier de la sauvegarde JSON")
    args = parser.parse_args()

    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET"])
    bucket = stockage_r2.from_(config_skills.BUCKET)
    classiques = db.table("comportements_etudiants").select("*").is_("categorie", "null").execute().data or []
    publics = db.table("comportements_publics").select("*").execute().data or []
    avant = db.table("skills").select("id", count="exact").limit(1).execute().count or 0

    taches = [(r, False) for r in classiques] + [(r, True) for r in publics]
    bilan = {"a_migrer": 0, "deja_migres": 0, "ignores": 0, "ecrits": 0, "erreurs": 0}
    plans = []
    for row, public in taches:
        colonne = "legacy_public_id" if public else "legacy_behavior_id"
        if deja_migre(db, colonne, row["id"]):
            bilan["deja_migres"] += 1
            continue
        plan = preparer(row, public)
        if plan is None:
            logging.warning("Ignoré (propriétaire absent) : %s %s", "public" if public else "classique", row["id"])
            bilan["ignores"] += 1
            continue
        plans.append(plan)
        bilan["a_migrer"] += 1

    # Doublons probables : un auteur qui a déjà un skill privé de même nom que son skill public.
    noms_prives = {(p["skill"]["owner_id"], p["skill"]["nom"].lower()) for p in plans if p["skill"]["visibilite"] == "prive"}
    doublons = [p["skill"]["id"] for p in plans if p["skill"]["visibilite"] != "prive" and (p["skill"]["owner_id"], p["skill"]["nom"].lower()) in noms_prives]
    repartition = {}
    for p in plans:
        repartition[p["skill"]["visibilite"]] = repartition.get(p["skill"]["visibilite"], 0) + 1
    logging.info("Sources : %d skills classiques, %d skills publics. Table skills avant : %d ligne(s).", len(classiques), len(publics), avant)
    logging.info("A migrer : %s. Déjà migrés : %d. Ignorés : %d.", repartition or "rien", bilan["deja_migres"], bilan["ignores"])
    if doublons:
        logging.info("A vérifier : %d skill(s) public(s) ont le même nom qu'un skill privé de leur auteur (ids : %s). Ils sont migrés tous les deux, sans fusion.", len(doublons), ", ".join(doublons))

    if not args.executer:
        nb_ajouts = len(db.table("comportement_public_activations").select("id").execute().data or [])
        logging.info("Ajouts existants qui seront reliés une fois les skills migrés : %d.", nb_ajouts)
        logging.info("SIMULATION : rien n'a été écrit. Relance avec --executer pour migrer.")
        return 0

    os.makedirs(args.sauvegarde, exist_ok=True)
    fichier = os.path.join(args.sauvegarde, f"skills_historiques_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump({"comportements_etudiants": classiques, "comportements_publics": publics}, f, ensure_ascii=False, indent=2, default=str)
    logging.info("Sauvegarde des sources écrite : %s", fichier)

    for plan in plans:
        try:
            ecrire(db, bucket, plan)
            bilan["ecrits"] += 1
        except Exception as e:
            bilan["erreurs"] += 1
            logging.error("Echec pour le skill %s : %s", plan["skill"]["id"], e)
    apres = db.table("skills").select("id", count="exact").limit(1).execute().count or 0
    logging.info("Bilan : %s. Table skills : %d avant, %d après (attendu %d).", bilan, avant, apres, avant + bilan["ecrits"])
    try:
        logging.info("Ajouts reliés : %s.", lier_activations(db, executer=True))
    except Exception as e:
        logging.error("Echec du lien des ajouts (relancer le script, il est sans risque) : %s", e)
        return 1
    return 0 if bilan["erreurs"] == 0 and apres == avant + bilan["ecrits"] else 1


if __name__ == "__main__":
    sys.exit(main())
