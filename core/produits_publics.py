"""Produits publics : publier, modifier, retirer, lister (28/11/2026, demande de Bourama).

Un produit est un site, une appli ou une plateforme présenté sur une page publique indexée par
Google. N'importe quel compte connecté peut en publier un, il est visible tout de suite. Le
retrait se fait après signalement (api/signalements.py) ou par un administrateur.

Les images sont dans R2 (bucket images-publiques, dossier produits/<id du compte>/). La table ne
garde que les chemins ; l'adresse publique est calculée à la lecture. Toutes les erreurs sont des
HTTPException créées par erreur_api (code stable, message français et anglais dans core/erreurs.py).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from api.auth import supabase
from core import config_produits_publics as cfg
from core import stockage_r2
from core.erreurs import erreur_api

COLONNES_LISTE = (
    "id,auteur_id,nom,accroche,type_produit,url,logo_chemin,images,etiquettes,publie_le,updated_at"
)


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _est_uuid(valeur: str) -> bool:
    try:
        uuid.UUID(str(valeur))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def dossier_images(auteur_id: str) -> str:
    return f"{cfg.DOSSIER_IMAGES}/{auteur_id}/"


def url_image(chemin: str | None) -> str | None:
    if not chemin:
        return None
    return stockage_r2.from_(cfg.BUCKET_IMAGES).get_public_url(chemin)


def normaliser_url(brut: str) -> str:
    """Ajoute https:// si besoin et refuse tout ce qui n'est pas une adresse web publique plausible."""
    url = (brut or "").strip()
    if not url:
        raise erreur_api(400, "PRODUIT_URL_INVALIDE")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    if len(url) > cfg.URL_MAX:
        raise erreur_api(400, "PRODUIT_URL_INVALIDE")
    morceaux = urlparse(url)
    hote = (morceaux.hostname or "").lower()
    if morceaux.scheme not in ("http", "https") or "." not in hote or hote.endswith(".local"):
        raise erreur_api(400, "PRODUIT_URL_INVALIDE")
    return url


def _texte(valeur, minimum: int, maximum: int, code: str, obligatoire: bool = True) -> str:
    texte = re.sub(r"[ \t]+", " ", (valeur or "").strip())
    if not texte and not obligatoire:
        return ""
    if len(texte) < minimum or len(texte) > maximum:
        raise erreur_api(400, code)
    return texte


def _etiquettes(valeurs) -> list[str]:
    propres, vues = [], set()
    for v in valeurs or []:
        e = re.sub(r"\s+", " ", str(v).strip().lower())
        if not e or e in vues:
            continue
        if len(e) < cfg.ETIQUETTE_MIN or len(e) > cfg.ETIQUETTE_MAX:
            raise erreur_api(400, "PRODUIT_ETIQUETTE_INVALIDE")
        vues.add(e)
        propres.append(e)
    if len(propres) > cfg.ETIQUETTES_MAX:
        raise erreur_api(400, "PRODUIT_ETIQUETTE_INVALIDE")
    return propres


def _chemin_a_moi(chemin: str, auteur_id: str) -> bool:
    return bool(chemin) and ".." not in chemin and chemin.startswith(dossier_images(auteur_id))


def _images(valeurs, auteur_id: str) -> list[dict]:
    images, vus = [], set()
    for v in valeurs or []:
        chemin = (v.get("chemin") if isinstance(v, dict) else v) or ""
        if not _chemin_a_moi(chemin, auteur_id):
            raise erreur_api(400, "PRODUIT_IMAGE_INVALIDE")
        if chemin in vus:
            continue
        vus.add(chemin)
        alt = (v.get("alt") if isinstance(v, dict) else "") or ""
        images.append({"chemin": chemin, "alt": alt.strip()[:160]})
    if len(images) > cfg.IMAGES_MAX:
        raise erreur_api(400, "PRODUIT_TROP_D_IMAGES", maximum=cfg.IMAGES_MAX)
    return images


def valider(donnees: dict, auteur_id: str) -> dict:
    """Vérifie et nettoie les champs envoyés. Renvoie la ligne prête pour la base."""
    type_produit = (donnees.get("type_produit") or "").strip().lower()
    if type_produit not in cfg.TYPES_PRODUIT:
        raise erreur_api(400, "PRODUIT_TYPE_INVALIDE")
    logo = donnees.get("logo_chemin") or None
    if logo and not _chemin_a_moi(logo, auteur_id):
        raise erreur_api(400, "PRODUIT_IMAGE_INVALIDE")
    return {
        "nom": _texte(donnees.get("nom"), cfg.NOM_MIN, cfg.NOM_MAX, "PRODUIT_NOM_INVALIDE"),
        "accroche": _texte(donnees.get("accroche"), cfg.ACCROCHE_MIN, cfg.ACCROCHE_MAX, "PRODUIT_ACCROCHE_INVALIDE"),
        "description": _texte(donnees.get("description"), 0, cfg.DESCRIPTION_MAX, "PRODUIT_DESCRIPTION_INVALIDE", obligatoire=False),
        "type_produit": type_produit,
        "url": normaliser_url(donnees.get("url")),
        "logo_chemin": logo,
        "images": _images(donnees.get("images"), auteur_id),
        "etiquettes": _etiquettes(donnees.get("etiquettes")),
    }


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
        if len(mots) >= cfg.RECHERCHE_MOTS_MAX:
            break
    return mots


def _noms_createurs(ids: list[str]) -> dict[str, str]:
    """Nom affiché des créateurs qui ont un profil public. Les autres restent anonymes sur la page."""
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    try:
        res = (
            supabase.table("profiles").select("user_id,nom_affiche,profil_public")
            .in_("user_id", ids).execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (noms des créateurs de produits) : {e}")
        return {}
    return {
        p["user_id"]: (p.get("nom_affiche") or "").strip()
        for p in (res.data or []) if p.get("profil_public") and (p.get("nom_affiche") or "").strip()
    }


def presenter(ligne: dict, noms: dict[str, str], mon_id: str | None) -> dict:
    """Ligne de base vers la forme renvoyée à l'écran : adresses d'images calculées, auteur nommé ou non."""
    images = [
        {"chemin": i["chemin"], "alt": i.get("alt") or "", "url": url_image(i["chemin"])}
        for i in (ligne.get("images") or [])
    ]
    return {
        "id": ligne["id"],
        "nom": ligne["nom"],
        "accroche": ligne.get("accroche") or "",
        "description": ligne.get("description") or "",
        "type_produit": ligne["type_produit"],
        "url": ligne["url"],
        "logo_chemin": ligne.get("logo_chemin"),
        "logo_url": url_image(ligne.get("logo_chemin")),
        "images": images,
        "etiquettes": ligne.get("etiquettes") or [],
        "createur_nom": noms.get(ligne["auteur_id"]) or None,
        "publie_le": ligne.get("publie_le"),
        "modifie_le": ligne.get("updated_at"),
        "est_a_moi": mon_id is not None and ligne["auteur_id"] == mon_id,
    }


def lister(q: str = "", type_produit: str = "", etiquette: str = "", decalage: int = 0, limite: int = 0, mon_id: str | None = None) -> list[dict]:
    limite = max(1, min(limite or cfg.LISTE_LIMITE_DEFAUT, cfg.LISTE_LIMITE_MAX))
    decalage = max(0, decalage)
    try:
        requete = supabase.table("produits_publics").select("*").eq("statut", "publie")
        if type_produit in cfg.TYPES_PRODUIT:
            requete = requete.eq("type_produit", type_produit)
        if etiquette.strip():
            requete = requete.contains("etiquettes", [etiquette.strip().lower()])
        mots = _mots_de_recherche(q)
        if mots:
            filtre = ",".join(f"{c}.ilike.%{m}%" for m in mots for c in ("nom", "accroche", "description"))
            requete = requete.or_(filtre)
        res = requete.order("publie_le", desc=True).range(decalage, decalage + limite - 1).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (liste des produits publics) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_PRODUITS")
    lignes = res.data or []
    noms = _noms_createurs([l["auteur_id"] for l in lignes])
    return [presenter(l, noms, mon_id) for l in lignes]


def _ligne_publiee(produit_id: str) -> dict | None:
    if not _est_uuid(produit_id):
        return None
    try:
        res = (
            supabase.table("produits_publics").select("*")
            .eq("id", produit_id).eq("statut", "publie").maybe_single().execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (produit public {produit_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_PRODUITS")
    return res.data if res and res.data else None


def obtenir(produit_id: str, mon_id: str | None = None) -> dict:
    """Détail d'un produit publié. Un produit retiré ou inconnu donne toujours 404, sans rien révéler."""
    ligne = _ligne_publiee(produit_id)
    if not ligne:
        raise erreur_api(404, "PRODUIT_INTROUVABLE")
    return presenter(ligne, _noms_createurs([ligne["auteur_id"]]), mon_id)


def lister_mes_produits(auteur_id: str) -> list[dict]:
    try:
        res = (
            supabase.table("produits_publics").select("*")
            .eq("auteur_id", auteur_id).eq("statut", "publie").order("publie_le", desc=True).execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (mes produits publics) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_PRODUITS")
    return [presenter(l, {}, auteur_id) for l in (res.data or [])]


def _nombre_de_mes_produits(auteur_id: str) -> int:
    res = supabase.table("produits_publics").select("id").eq("auteur_id", auteur_id).eq("statut", "publie").execute()
    return len(res.data or [])


def publier(donnees: dict, auteur_id: str) -> dict:
    ligne = valider(donnees, auteur_id)
    try:
        if _nombre_de_mes_produits(auteur_id) >= cfg.PRODUITS_PAR_COMPTE_MAX:
            raise erreur_api(409, "PRODUIT_LIMITE_ATTEINTE", maximum=cfg.PRODUITS_PAR_COMPTE_MAX)
        doublon = (
            supabase.table("produits_publics").select("id")
            .eq("auteur_id", auteur_id).eq("url", ligne["url"]).eq("statut", "publie").execute()
        )
        if doublon.data:
            raise erreur_api(409, "PRODUIT_DEJA_PUBLIE")
        maintenant = _maintenant()
        res = supabase.table("produits_publics").insert({
            **ligne, "auteur_id": auteur_id, "statut": "publie", "publie_le": maintenant, "updated_at": maintenant,
        }).execute()
    except Exception as e:
        if hasattr(e, "status_code") and hasattr(e, "detail"):
            raise
        logging.error(f"ERREUR SUPABASE (publication produit) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_PUBLIER_PRODUIT")
    return presenter(res.data[0], {}, auteur_id)


def _ma_ligne(produit_id: str, auteur_id: str) -> dict:
    ligne = _ligne_publiee(produit_id)
    if not ligne or ligne["auteur_id"] != auteur_id:
        raise erreur_api(404, "PRODUIT_INTROUVABLE")
    return ligne


def _chemins_images(ligne: dict) -> set[str]:
    chemins = {i["chemin"] for i in (ligne.get("images") or [])}
    if ligne.get("logo_chemin"):
        chemins.add(ligne["logo_chemin"])
    return chemins


def supprimer_fichiers(chemins) -> None:
    """Efface des images dans R2. Une image qui ne part pas est loguée, jamais bloquante."""
    stockage = stockage_r2.from_(cfg.BUCKET_IMAGES)
    for chemin in chemins:
        try:
            stockage.remove([chemin])
        except Exception as e:
            logging.warning(f"PRODUIT : image {chemin} non supprimée : {e}")


def modifier(produit_id: str, donnees: dict, auteur_id: str) -> dict:
    ancienne = _ma_ligne(produit_id, auteur_id)
    ligne = valider(donnees, auteur_id)
    try:
        if ligne["url"] != ancienne["url"]:
            doublon = (
                supabase.table("produits_publics").select("id")
                .eq("auteur_id", auteur_id).eq("url", ligne["url"]).eq("statut", "publie").neq("id", produit_id).execute()
            )
            if doublon.data:
                raise erreur_api(409, "PRODUIT_DEJA_PUBLIE")
        res = supabase.table("produits_publics").update({**ligne, "updated_at": _maintenant()}).eq("id", produit_id).execute()
    except Exception as e:
        if hasattr(e, "status_code") and hasattr(e, "detail"):
            raise
        logging.error(f"ERREUR SUPABASE (modification produit {produit_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_MODIFIER_PRODUIT")
    supprimer_fichiers(_chemins_images(ancienne) - _chemins_images(res.data[0]))
    return presenter(res.data[0], {}, auteur_id)


def supprimer(produit_id: str, auteur_id: str) -> None:
    ligne = _ma_ligne(produit_id, auteur_id)
    try:
        supabase.table("produits_publics").delete().eq("id", produit_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (suppression produit {produit_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_RETIRER_PRODUIT")
    supprimer_fichiers(_chemins_images(ligne))


def retirer_par_admin(produit_id: str, motif: str) -> None:
    """Retrait par un administrateur : le produit disparaît du public mais la ligne reste, avec le motif."""
    try:
        supabase.table("produits_publics").update({
            "statut": "retire", "retire_motif": (motif or "").strip()[:500] or None, "retire_le": _maintenant(),
        }).eq("id", produit_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (retrait admin produit {produit_id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_RETIRER_PRODUIT")
