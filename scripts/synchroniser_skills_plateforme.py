"""Synchronise les skills officiels de Classinus depuis le dossier skills_plateforme/ du dépôt.

Un dossier par skill : skills_plateforme/<slug>/SKILL.md (avec name et description dans l'en-tête),
plus d'éventuels autres fichiers texte (references/, scripts/, assets/). Le nom du dossier est le
slug du skill : il ne change jamais, c'est lui qui relie le dossier à la base.

Deux modes, donnés en argument (le premier est le défaut) :
    python -m scripts.synchroniser_skills_plateforme simuler
    python -m scripts.synchroniser_skills_plateforme appliquer

Simuler n'écrit rien : le script dit seulement ce qu'il créerait, mettrait à jour ou laisserait.
Relançable sans risque : un skill dont le contenu n'a pas changé est laissé tel quel.
Un skill présent en base mais absent du dossier est SIGNALÉ, jamais supprimé ni désactivé tout seul.

Mêmes règles que les skills des utilisateurs (validation des chemins, plafonds de taille, en-tête du
SKILL.md qui suit le nom et la description, envoi tout ou rien vers R2, ancienne version gardée tant
que la base n'a pas basculé).

Variables : SUPABASE_URL, SUPABASE_SECRET, R2_* (comme le backend).
SKILLS_PLATEFORME_DOSSIER change le dossier lu (par défaut skills_plateforme/ à la racine du dépôt).
"""
import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api import skills as _api
from core import skills_catalogue
from core.skills_entete import lire_entete

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Segment de clé R2 réservé aux skills de plateforme (les skills des comptes utilisent l'id du compte).
PROPRIETAIRE_R2 = "plateforme"


def dossier_source() -> Path:
    brut = os.environ.get("SKILLS_PLATEFORME_DOSSIER")
    return Path(brut) if brut else Path(__file__).resolve().parent.parent / "skills_plateforme"


def lire_dossier_skill(dossier: Path) -> tuple[_api.SkillPayload, str]:
    """Lit un dossier de skill. Lève ValueError avec une phrase claire si le dossier est inutilisable."""
    slug = dossier.name
    skill_md = dossier / "SKILL.md"
    if not skill_md.is_file():
        raise ValueError(f"{slug} : le fichier SKILL.md est absent.")
    fichiers = []
    for chemin in sorted(p for p in dossier.rglob("*") if p.is_file()):
        relatif = chemin.relative_to(dossier).as_posix()
        try:
            texte = chemin.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"{slug} : {relatif} n'est pas un fichier texte (les skills ne portent que du texte).")
        fichiers.append(_api.Fichier(chemin=relatif, contenu=texte))
    entete = lire_entete(skill_md.read_text(encoding="utf-8"))
    nom, description = (entete.get("name") or "").strip(), (entete.get("description") or "").strip()
    if not nom or not description:
        raise ValueError(f"{slug} : l'en-tête du SKILL.md doit contenir name et description.")
    return _api.SkillPayload(nom=nom, description=description, actif=True, fichiers=fichiers), slug


def contenus_en_base(skill_id: str) -> dict[str, str]:
    """Contenus actuellement publiés d'un skill, par chemin. Un fichier illisible compte comme différent."""
    try:
        return {f["chemin"]: f["contenu"] for f in _api._files(skill_id, True) if not f.get("binaire")}
    except Exception as e:
        logging.warning(f"  lecture de l'existant impossible ({type(e).__name__}), il sera mis à jour par prudence.")
        return {}


def _lignes_skills_plateforme() -> dict[str, dict]:
    res = _api.supabase.table("skills").select("*").eq("portee", "plateforme").execute()
    return {l["slug"]: l for l in (res.data or []) if l.get("slug")}


def creer(slug: str, payload: _api.SkillPayload, fichiers: list[dict]) -> None:
    skill_id = str(uuid.uuid4())
    maintenant = datetime.now(timezone.utc).isoformat()
    ligne = {
        "id": skill_id, "owner_id": None, "portee": "plateforme", "slug": slug,
        "nom": payload.nom.strip(), "description": payload.description.strip(), "actif": True,
        "created_at": maintenant, "updated_at": maintenant,
    }
    lignes_fichiers: list[dict] = []
    try:
        lignes_fichiers = _api._upload(PROPRIETAIRE_R2, skill_id, fichiers)
        _api.supabase.table("skills").insert(ligne).execute()
        _api.supabase.table("skill_files").insert(lignes_fichiers).execute()
    except Exception:
        _api._supprimer_cles([l["cle_stockage"] for l in lignes_fichiers], f"annulation création skill plateforme {slug}")
        try:
            _api.supabase.table("skills").delete().eq("id", skill_id).execute()
        except Exception as e:
            logging.error(f"  nettoyage de la ligne {skill_id} impossible : {e}")
        raise


def mettre_a_jour(existant: dict, payload: _api.SkillPayload, fichiers: list[dict]) -> None:
    skill_id = existant["id"]
    anciennes = _api.supabase.table("skill_files").select("chemin,cle_stockage").eq("skill_id", skill_id).execute().data or []
    # 1. Nouveaux contenus sous de nouvelles clés : l'ancienne version n'est pas touchée.
    nouvelles = _api._upload(PROPRIETAIRE_R2, skill_id, fichiers)
    nouveaux_chemins = {l["chemin"] for l in nouvelles}
    # 2. Bascule des lignes vers les nouvelles clés.
    try:
        _api.supabase.table("skill_files").upsert(nouvelles, on_conflict="skill_id,chemin").execute()
    except Exception:
        _api._supprimer_cles([l["cle_stockage"] for l in nouvelles], f"annulation mise à jour skill plateforme {existant.get('slug')}")
        raise
    # À partir d'ici la base pointe vers les nouvelles clés : on ne les supprime plus jamais.
    retires = [l["chemin"] for l in anciennes if l["chemin"] not in nouveaux_chemins]
    if retires:
        _api.supabase.table("skill_files").delete().eq("skill_id", skill_id).in_("chemin", retires).execute()
    _api.supabase.table("skills").update({
        "nom": payload.nom.strip(), "description": payload.description.strip(), "actif": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", skill_id).eq("portee", "plateforme").execute()
    # 3. Seulement maintenant, les anciennes clés sont supprimées.
    _api._supprimer_cles([l["cle_stockage"] for l in anciennes], f"anciens fichiers skill plateforme {existant.get('slug')}")


def synchroniser(appliquer: bool, dossier: Path | None = None) -> dict:
    """Renvoie {"crees": [...], "mis_a_jour": [...], "inchanges": [...], "absents": [...], "erreurs": [...]}."""
    dossier = dossier or dossier_source()
    bilan = {"crees": [], "mis_a_jour": [], "inchanges": [], "absents": [], "erreurs": []}
    if not dossier.is_dir():
        bilan["erreurs"].append(f"Dossier introuvable : {dossier}")
        return bilan
    en_base = _lignes_skills_plateforme()
    vus = set()
    for sous in sorted(p for p in dossier.iterdir() if p.is_dir() and not p.name.startswith(".")):
        try:
            payload, slug = lire_dossier_skill(sous)
            fichiers = _api._prepare(payload)
        except ValueError as e:
            bilan["erreurs"].append(str(e))
            continue
        except Exception as e:
            bilan["erreurs"].append(f"{sous.name} : {getattr(e, 'detail', e)}")
            continue
        vus.add(slug)
        existant = en_base.get(slug)
        if existant is None:
            action = "crees"
        else:
            voulus = {f["chemin"]: f["contenu"].decode("utf-8") for f in fichiers}
            identique = (
                voulus == contenus_en_base(existant["id"])
                and existant.get("nom") == payload.nom.strip()
                and (existant.get("description") or "") == payload.description.strip()
                and existant.get("actif", True)
            )
            action = "inchanges" if identique else "mis_a_jour"
        if appliquer and action != "inchanges":
            try:
                creer(slug, payload, fichiers) if action == "crees" else mettre_a_jour(existant, payload, fichiers)
            except Exception as e:
                logging.error(f"ERREUR synchronisation {slug} : {e}")
                bilan["erreurs"].append(f"{slug} : l'écriture a échoué (voir les logs).")
                continue
        bilan[action].append(slug)
    bilan["absents"] = sorted(set(en_base) - vus)
    if appliquer:
        skills_catalogue.vider_cache_officiels()
    return bilan


def afficher(bilan: dict, appliquer: bool) -> None:
    verbe = {"crees": "créés", "mis_a_jour": "mis à jour", "inchanges": "inchangés"}
    futur = "" if appliquer else " (simulation, rien n'a été écrit)"
    for cle, libelle in verbe.items():
        logging.info(f"{libelle.capitalize()}{futur} : {', '.join(bilan[cle]) or 'aucun'}")
    if bilan["absents"]:
        logging.info("Présents en base mais absents du dossier (laissés tels quels, à décider par toi) : " + ", ".join(bilan["absents"]))
    for erreur in bilan["erreurs"]:
        logging.error(f"Erreur : {erreur}")


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Synchronise les skills officiels de Classinus.")
    parseur.add_argument("mode", nargs="?", choices=["simuler", "appliquer"], default="simuler")
    mode = parseur.parse_args(argv).mode
    appliquer = mode == "appliquer"
    bilan = synchroniser(appliquer)
    afficher(bilan, appliquer)
    return 1 if bilan["erreurs"] else 0


if __name__ == "__main__":
    sys.exit(main())
