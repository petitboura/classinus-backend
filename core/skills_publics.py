"""Skills publics : publier, retirer, chercher, ajouter chez soi, mettre à jour une copie.

Un skill public est un skill ordinaire (table skills, fichiers dans R2) dont la colonne
visibilite vaut 'public'. Aucune copie de contenu n'est faite à la publication : le skill de
l'auteur EST la version publique, donc une modification de l'auteur est visible tout de suite.

Ajouter un skill public chez soi crée une copie indépendante (ses propres fichiers dans R2),
reliée à l'original par la table skill_activations. Quand l'auteur modifie son skill,
version_publique augmente (voir api/skills.py::modifier). La copie, elle, ne change jamais
toute seule : l'IA signale qu'une nouvelle version existe et ne la remplace qu'avec l'accord de
l'utilisateur, car le texte d'un skill devient des consignes pour l'IA de celui qui l'a ajouté.

Toutes les erreurs sont des HTTPException créées par erreur_api (code stable, message français
et anglais dans core/erreurs.py) : l'API les laisse passer, l'outil de l'IA les met en phrase.
Ce module ne dépend pas du serveur MCP, pour pouvoir être testé seul.
"""
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api import skills as _api
from core import config_skills
from core.erreurs import erreur_api

COLONNES_LISTE = "id,nom,description,owner_id,activations_count,etoiles_count,version_publique,publie_le,updated_at"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instant(valeur) -> datetime | None:
    """Lit un horodatage ISO renvoyé par la base. Renvoie None s'il est absent ou illisible."""
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError:
        return None


def _est_uuid(valeur: str) -> bool:
    try:
        uuid.UUID(str(valeur))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _mots_de_recherche(mot_cle: str) -> list[str]:
    """Découpe la recherche en mots sûrs pour un filtre PostgREST (pas de virgule, parenthèse, %, *)."""
    propre = re.sub(r"[,()%*\\\"']", " ", (mot_cle or ""))
    mots, vus = [], set()
    for mot in propre.split():
        bas = mot.lower()
        if len(bas) < 2 or bas in vus:
            continue
        vus.add(bas)
        mots.append(mot[:60])
        if len(mots) >= config_skills.PUBLICS_RECHERCHE_MOTS_MAX:
            break
    return mots


def _ligne_publique(identifiant: str) -> dict | None:
    """Ligne d'un skill PUBLIC par son id, ou par l'ancien id du catalogue (legacy_public_id).

    Un skill retiré ou privé n'est jamais renvoyé : son id ne doit rien révéler.
    """
    identifiant = (identifiant or "").strip()
    if not _est_uuid(identifiant):
        return None
    for colonne in ("id", "legacy_public_id"):
        try:
            res = (
                _api.supabase.table("skills").select("*")
                .eq(colonne, identifiant).eq("visibilite", "public").maybe_single().execute()
            )
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (skill public {identifiant}) : {e}")
            raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_SKILLS_PUBLICS")
        if res and res.data:
            return res.data
    return None


def _ligne_publique_ou_404(identifiant: str) -> dict:
    ligne = _ligne_publique(identifiant)
    if ligne is None:
        raise erreur_api(404, "SKILL_PUBLIC_INTROUVABLE")
    return ligne


# --- Publier et retirer -------------------------------------------------------------------------

def publier(skill_id: str, user_id: str) -> dict:
    """Rend un skill de l'utilisateur public. Sans effet s'il l'est déjà."""
    ligne = _api._owned(skill_id, user_id)
    if ligne.get("visibilite") == "public":
        return ligne
    if not (ligne.get("description") or "").strip():
        raise erreur_api(422, "SKILL_DESCRIPTION_REQUISE_POUR_PUBLIER")
    maintenant = _maintenant()
    changements = {"visibilite": "public", "publie_le": maintenant, "retire_le": None}
    try:
        _api.supabase.table("skills").update(changements).eq("id", skill_id).eq("owner_id", user_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (publication skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_PUBLIER_SKILL")
    return {**ligne, **changements}


def retirer(skill_id: str, user_id: str) -> dict:
    """Retire un skill public du catalogue. Les copies déjà ajoutées par d'autres ne sont pas touchées."""
    ligne = _api._owned(skill_id, user_id)
    if ligne.get("visibilite") != "public":
        raise erreur_api(409, "SKILL_PAS_PUBLIC")
    changements = {"visibilite": "retire", "retire_le": _maintenant()}
    try:
        _api.supabase.table("skills").update(changements).eq("id", skill_id).eq("owner_id", user_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (retrait skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_RETIRER_SKILL")
    return {**ligne, **changements}


# --- Chercher et lire ---------------------------------------------------------------------------

def chercher(mot_cle: str = "") -> list[dict]:
    """Skills publics, les plus pertinents puis les plus ajoutés en premier.

    Chaque mot de la recherche est cherché dans le nom et la description. Un skill qui contient
    plus de mots passe devant. Sans recherche, ce sont les plus ajoutés.
    """
    mots = _mots_de_recherche(mot_cle)
    requete = (
        _api.supabase.table("skills").select(COLONNES_LISTE)
        .eq("visibilite", "public").eq("portee", "compte")
    )
    if mots:
        requete = requete.or_(",".join(f"nom.ilike.%{m}%,description.ilike.%{m}%" for m in mots))
    try:
        lignes = requete.order("activations_count", desc=True).limit(config_skills.PUBLICS_RECHERCHE_LIGNES).execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (recherche skills publics q={mot_cle!r}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_SKILLS_PUBLICS")

    def pertinence(ligne: dict) -> int:
        texte = f"{ligne.get('nom') or ''} {ligne.get('description') or ''}".lower()
        return sum(1 for m in mots if m.lower() in texte)

    # sorted est stable : à pertinence égale, l'ordre de la base (les plus ajoutés) est gardé.
    lignes = sorted(lignes, key=pertinence, reverse=True)
    return lignes[: config_skills.PUBLICS_RECHERCHE_RESULTATS]


def obtenir(identifiant: str) -> dict:
    """Détail d'un skill public : la ligne et la liste de ses fichiers (sans leur contenu)."""
    ligne = _ligne_publique_ou_404(identifiant)
    return {**ligne, "fichiers": _api._files(ligne["id"], False)}


def lire_fichier(identifiant: str, chemin: str = "") -> dict:
    """Lit un fichier d'un skill public (le SKILL.md par défaut). Renvoie la ligne, le chemin, le texte."""
    ligne = _ligne_publique_ou_404(identifiant)
    cible = _api._path(chemin) if (chemin or "").strip() else "SKILL.md"
    try:
        lignes = _api.supabase.table("skill_files").select("*").eq("skill_id", ligne["id"]).order("chemin").execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fichiers skill public {ligne['id']}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_FICHIERS_SKILL")
    trouve = next((r for r in lignes if r["chemin"] == cible), None)
    if trouve is None:
        raise erreur_api(404, "SKILL_FICHIER_INTROUVABLE", chemin=cible)
    item = _api._lire(trouve)
    autres = [{"chemin": r["chemin"], "taille_octets": r.get("taille_octets", 0)} for r in lignes if r["chemin"] != cible]
    return {"skill": ligne, "chemin": cible, "contenu": item.get("contenu"), "binaire": item.get("binaire", False), "autres_fichiers": autres}


# --- Copier des fichiers (ajout et mise à jour) --------------------------------------------------

def _fichiers_de(skill_id: str) -> list[dict]:
    """Tous les fichiers d'un skill, contenu en octets : [{chemin, contenu, type_mime}]."""
    try:
        lignes = _api.supabase.table("skill_files").select("*").eq("skill_id", skill_id).execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fichiers à copier du skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_FICHIERS_SKILL")
    magasin = _api.stockage_r2.from_(_api.BUCKET)

    def lire(r: dict) -> dict:
        return {"chemin": r["chemin"], "contenu": magasin.download(r["cle_stockage"]), "type_mime": r.get("type_mime") or "text/plain"}

    try:
        with ThreadPoolExecutor(max_workers=_api.TELECHARGEMENTS_PARALLELES) as pool:
            return list(pool.map(lire, lignes))
    except Exception as e:
        logging.error(f"ERREUR R2 (lecture des fichiers du skill {skill_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_LIRE_FICHIER_SKILL")


def _activation_existante(source_id: str, user_id: str) -> dict | None:
    res = (
        _api.supabase.table("skill_activations").select("*")
        .eq("skill_source_id", source_id).eq("active_par", user_id).maybe_single().execute()
    )
    return res.data if res and res.data else None


# --- Ajouter chez soi ---------------------------------------------------------------------------

def activer(identifiant: str, user_id: str) -> dict:
    """Ajoute un skill public aux skills de l'utilisateur, sous forme de copie indépendante.

    Déjà ajouté : renvoie la copie existante au lieu d'en créer une seconde.
    Renvoie {"copie": ligne, "deja_ajoute": bool}.
    """
    source = _ligne_publique_ou_404(identifiant)
    if source.get("owner_id") == user_id:
        raise erreur_api(409, "SKILL_PUBLIC_C_EST_LE_TIEN")
    try:
        existante = _activation_existante(source["id"], user_id)
        if existante:
            copie = _api.supabase.table("skills").select("*").eq("id", existante["copie_id"]).maybe_single().execute()
            if copie and copie.data:
                return {"copie": copie.data, "deja_ajoute": True}
        nb = _api.supabase.table("skills").select("id", count="exact").eq("owner_id", user_id).limit(1).execute().count or 0
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (ajout skill public {source['id']}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_D_AJOUTER_SKILL_PUBLIC")
    if nb >= _api.NB_SKILLS_MAX:
        raise erreur_api(409, "SKILLS_LIMITE_ATTEINTE", maximum=_api.NB_SKILLS_MAX)

    fichiers = _fichiers_de(source["id"])
    copie_id, maintenant = str(uuid.uuid4()), _maintenant()
    ligne = {
        "id": copie_id, "owner_id": user_id, "nom": source["nom"], "description": source.get("description") or "",
        "actif": True, "created_at": maintenant, "updated_at": maintenant,
    }
    activation = {
        "skill_source_id": source["id"], "copie_id": copie_id, "active_par": user_id,
        "version_copiee": source.get("version_publique") or 1, "synchronise_le": maintenant,
    }
    lignes_fichiers: list[dict] = []
    try:
        lignes_fichiers = _api._upload(user_id, copie_id, fichiers)
        _api.supabase.table("skills").insert(ligne).execute()
        _api.supabase.table("skill_files").insert(lignes_fichiers).execute()
        _api.supabase.table("skill_activations").insert(activation).execute()
    except Exception as e:
        logging.error(f"ERREUR ajout skill public {source['id']} pour {user_id} : {e}")
        _api._supprimer_cles([r["cle_stockage"] for r in lignes_fichiers], "annulation ajout skill public")
        try:
            _api.supabase.table("skills").delete().eq("id", copie_id).eq("owner_id", user_id).execute()
        except Exception as e2:
            logging.error(f"ERREUR SUPABASE (nettoyage copie {copie_id}) : {e2}")
        # Deux ajouts en même temps : le second échoue sur la contrainte d'unicité, la copie du premier existe.
        try:
            existante = _activation_existante(source["id"], user_id)
            if existante:
                copie = _api.supabase.table("skills").select("*").eq("id", existante["copie_id"]).maybe_single().execute()
                if copie and copie.data:
                    return {"copie": copie.data, "deja_ajoute": True}
        except Exception as e3:
            logging.error(f"ERREUR SUPABASE (relecture ajout skill public) : {e3}")
        raise erreur_api(500, "IMPOSSIBLE_D_AJOUTER_SKILL_PUBLIC")

    try:
        _api.supabase.table("skills").update({"activations_count": (source.get("activations_count") or 0) + 1}).eq("id", source["id"]).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (compteur d'ajouts du skill {source['id']}) : {e}")
    return {"copie": ligne, "deja_ajoute": False}


# --- Mises à jour -------------------------------------------------------------------------------

def mises_a_jour_disponibles(user_id: str | None) -> list[dict]:
    """Copies de l'utilisateur dont l'original public a une version plus récente.

    Renvoie [{copie_id, source_id, nom, modifiee_localement}]. Une erreur donne une liste vide :
    le chat ne doit jamais échouer à cause de cette lecture.
    """
    if not user_id:
        return []
    try:
        activations = (
            _api.supabase.table("skill_activations").select("copie_id,skill_source_id,version_copiee,synchronise_le")
            .eq("active_par", user_id).execute().data or []
        )
        activations = [a for a in activations if a.get("skill_source_id")]
        if not activations:
            return []
        ids = list({a["skill_source_id"] for a in activations} | {a["copie_id"] for a in activations})
        lignes = {r["id"]: r for r in (
            _api.supabase.table("skills").select("id,nom,version_publique,visibilite,updated_at").in_("id", ids).execute().data or []
        )}
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (mises à jour de skills publics {user_id}) : {e}")
        return []
    resultat = []
    for a in activations:
        source, copie = lignes.get(a["skill_source_id"]), lignes.get(a["copie_id"])
        if not source or not copie or source.get("visibilite") != "public":
            continue
        if (source.get("version_publique") or 1) <= (a.get("version_copiee") or 1):
            continue
        modifiee, reference = _instant(copie.get("updated_at")), _instant(a.get("synchronise_le"))
        resultat.append({
            "copie_id": a["copie_id"], "source_id": a["skill_source_id"], "nom": copie.get("nom") or source.get("nom") or "",
            "modifiee_localement": bool(modifiee and reference and modifiee > reference),
        })
    return resultat


def mettre_a_jour_copie(copie_id: str, user_id: str) -> dict:
    """Remplace le contenu d'une copie par la version publique actuelle de son original.

    Ne se fait que sur demande de l'utilisateur. Les changements que l'utilisateur a faits
    lui-même sur sa copie sont remplacés. Même ordre que api/skills.py::modifier : les nouveaux
    fichiers sont envoyés sous de nouvelles clés, la base bascule, puis les anciennes clés sont
    supprimées. Un échec avant la bascule laisse l'ancienne version intacte.
    """
    copie = _api._owned(copie_id, user_id)
    try:
        activation = (
            _api.supabase.table("skill_activations").select("*")
            .eq("copie_id", copie_id).eq("active_par", user_id).maybe_single().execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (activation de la copie {copie_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_METTRE_A_JOUR_SKILL")
    if not activation or not activation.data:
        raise erreur_api(404, "SKILL_PAS_UNE_COPIE")
    activation = activation.data
    source = _ligne_publique(activation.get("skill_source_id") or "")
    if source is None:
        raise erreur_api(404, "SKILL_SOURCE_INDISPONIBLE")
    version = source.get("version_publique") or 1
    if version <= (activation.get("version_copiee") or 1):
        raise erreur_api(409, "SKILL_DEJA_A_JOUR")

    fichiers = _fichiers_de(source["id"])
    try:
        anciennes = _api.supabase.table("skill_files").select("chemin,cle_stockage").eq("skill_id", copie_id).execute().data or []
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (anciens fichiers de la copie {copie_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_METTRE_A_JOUR_SKILL")
    try:
        nouvelles = _api._upload(user_id, copie_id, fichiers)
    except Exception as e:
        logging.error(f"ERREUR R2 (envoi mise à jour de la copie {copie_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_METTRE_A_JOUR_SKILL")
    try:
        _api.supabase.table("skill_files").upsert(nouvelles, on_conflict="skill_id,chemin").execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (bascule des fichiers de la copie {copie_id}) : {e}")
        _api._supprimer_cles([r["cle_stockage"] for r in nouvelles], "annulation mise à jour de copie")
        raise erreur_api(500, "IMPOSSIBLE_DE_METTRE_A_JOUR_SKILL")
    # À partir d'ici la base pointe vers les nouvelles clés : on ne les supprime plus jamais.
    maintenant = _maintenant()
    conserves = {r["chemin"] for r in nouvelles}
    try:
        retires = [r["chemin"] for r in anciennes if r["chemin"] not in conserves]
        if retires:
            _api.supabase.table("skill_files").delete().eq("skill_id", copie_id).in_("chemin", retires).execute()
        _api.supabase.table("skills").update(
            {"nom": source["nom"], "description": source.get("description") or "", "updated_at": maintenant}
        ).eq("id", copie_id).eq("owner_id", user_id).execute()
        _api.supabase.table("skill_activations").update(
            {"version_copiee": version, "synchronise_le": maintenant}
        ).eq("copie_id", copie_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (fin de la mise à jour de la copie {copie_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_METTRE_A_JOUR_SKILL")
    _api._supprimer_cles([r["cle_stockage"] for r in anciennes], "anciens fichiers de la copie")
    return {"copie_id": copie_id, "nom": source["nom"], "version": version, "ancien_nom": copie.get("nom")}
