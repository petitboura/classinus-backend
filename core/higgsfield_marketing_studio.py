"""Generation Marketing Studio (presets Higgsfield) par le compte partage Classinus (MCP).

Pourquoi le MCP et pas l'API : les 649 presets de Classinus viennent du MCP et aucun n'existe
dans la liste de l'API (verifie le 07/11/2026 : 0 sur 649). Trois outils sont utilises :
media_import_url (image du produit vers un media_id), marketing_studio_v2_create (lancement)
et marketing_studio_v2_status (suivi).

Les contrats par type ont ete lus sur le flux reel de 1051 presets (07/11/2026) : un seul
format_slug par type. Ce que le serveur Higgsfield exige exactement n'est pas documente : toute
erreur de validation de sa part est renvoyee telle quelle a l'utilisateur, rien n'est suppose.
Le suivi enregistre l'identifiant du job avec le prefixe "mcp:" dans higgsfield_generations.
"""
import logging
import re

from core.higgsfield_mcp_partage import appeler_outil_marketing_interne
from core.higgsfield_requetes import ErreurHiggsfield

PREFIXE_SUIVI = "mcp:"

# Un seul format_slug par type dans le flux reel. "avatar" : photo de personne (People seulement).
# "url_marque" : adresse du site (SaaS seulement).
TYPES_MARKETING = {
    "product_shots": {"format": "standalone", "avatar": False, "url_marque": False},
    "product_shots_people": {"format": "with-model", "avatar": True, "url_marque": False},
    "hypermotion": {"format": "hypermotion", "avatar": False, "url_marque": False},
    "mixed_media": {"format": "mixed-media", "avatar": False, "url_marque": False},
    "2d_motion": {"format": "2d-product-motion", "avatar": False, "url_marque": False},
    "saas_motion": {"format": "saas", "avatar": False, "url_marque": True},
}

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_FORMAT_IMAGE = re.compile(r"^\d{1,2}:\d{1,2}$")
_EXT_MEDIA = (".mp4", ".webm", ".mov", ".webp", ".png", ".jpg", ".jpeg")
_ETATS_FIN_OK = {"completed", "complete", "succeeded", "success", "done", "finished", "ready"}
_ETATS_ECHEC = {"failed", "error", "canceled", "cancelled", "nsfw", "rejected", "blocked", "expired"}
_CLES_URL = ("url", "result_url", "video_url", "image_url", "output_url", "raw_url", "download_url", "media_url")


def est_uuid(valeur) -> bool:
    return isinstance(valeur, str) and bool(_UUID.match(valeur))


def _parcourir(donnees):
    """Parcourt tout un JSON (dict, liste) et renvoie chaque (cle, valeur) rencontree."""
    if isinstance(donnees, dict):
        for k, v in donnees.items():
            yield k, v
            yield from _parcourir(v)
    elif isinstance(donnees, list):
        for v in donnees:
            yield from _parcourir(v)


def _structure(resultat):
    return (resultat or {}).get("structuredContent") or {}


def _extrait_journal(resultat) -> str:
    return str(resultat)[:1500]


def trouver_uuid(donnees, mots_cle) -> str | None:
    """Premier uuid dont la cle contient un des mots, sinon le premier uuid trouve."""
    premier = None
    for cle, valeur in _parcourir(donnees):
        if est_uuid(valeur):
            if any(m in str(cle).lower() for m in mots_cle):
                return valeur
            if premier is None:
                premier = valeur
    return premier


def construire_creation(preset_id, preset_type, preset_nom, media_produit, media_avatar,
                        url_marque, prompt, format_image) -> dict:
    """Arguments de marketing_studio_v2_create. Leve ErreurHiggsfield si la demande est incoherente."""
    contrat = TYPES_MARKETING.get((preset_type or "").strip())
    if contrat is None:
        raise ErreurHiggsfield(f"Type de preset non pris en charge : {preset_type}.")
    if not est_uuid(preset_id):
        raise ErreurHiggsfield("Identifiant de preset invalide.")
    if not media_produit and not (contrat["url_marque"] and url_marque):
        raise ErreurHiggsfield(
            "Ajoute l'image de ton produit" + (" ou l'adresse de ton site." if contrat["url_marque"] else ".")
        )
    arguments = {
        "preset_id": preset_id,
        "preset_type": preset_type,
        "category_slug": "all",
        "format_slug": contrat["format"],
    }
    if preset_nom:
        arguments["preset_name"] = str(preset_nom)[:200]
    if media_produit:
        if not est_uuid(media_produit):
            raise ErreurHiggsfield("Identifiant de l'image du produit invalide.")
        arguments["product_media_id"] = media_produit
    if media_avatar:
        if not contrat["avatar"]:
            raise ErreurHiggsfield("Ce type de preset n'utilise pas de photo de personne.")
        if not est_uuid(media_avatar):
            raise ErreurHiggsfield("Identifiant de la photo de personne invalide.")
        arguments["avatar_media_id"] = media_avatar
    if url_marque:
        if not contrat["url_marque"]:
            raise ErreurHiggsfield("Ce type de preset n'utilise pas d'adresse de site.")
        if not str(url_marque).lower().startswith("https://") or len(url_marque) > 4096:
            raise ErreurHiggsfield("L'adresse du site doit commencer par https://.")
        arguments["brand_url"] = url_marque
    texte = (prompt or "").strip()
    if texte:
        if len(texte) > 5000:
            raise ErreurHiggsfield("La précision est trop longue (5000 caractères au maximum).")
        arguments["prompt"] = texte
    if format_image:
        if not _FORMAT_IMAGE.match(format_image):
            raise ErreurHiggsfield("Format invalide (exemple attendu : 9:16).")
        arguments["aspect_ratio"] = format_image
    return arguments


def importer_image(url_https: str) -> str:
    """Envoie une image deja hebergee (adresse https) a Higgsfield, renvoie son media_id confirme."""
    if not isinstance(url_https, str) or not url_https.lower().startswith("https://"):
        raise ErreurHiggsfield("L'image doit avoir une adresse https.")
    resultat = appeler_outil_marketing_interne("media_import_url", {"url": url_https, "type": "image"})
    media_id = trouver_uuid(_structure(resultat) or resultat, ("media", "id"))
    if not media_id:
        logging.error("Marketing Studio : media_import_url sans identifiant lisible : %s", _extrait_journal(resultat))
        raise ErreurHiggsfield("Higgsfield n'a pas confirmé l'image, réessaie avec une autre image.")
    return media_id


def creer(arguments: dict) -> str:
    """Lance la generation. Renvoie l'identifiant du job (sans prefixe)."""
    resultat = appeler_outil_marketing_interne("marketing_studio_v2_create", arguments)
    # Le format exact de la reponse n'est pas documente : on cherche le job, et on journalise la
    # reponse brute (sans jeton) pour pouvoir l'ajuster si besoin.
    job_id = trouver_uuid(_structure(resultat) or resultat, ("job",))
    logging.info("Marketing Studio create : %s", _extrait_journal(resultat))
    if not job_id:
        raise ErreurHiggsfield(
            "Higgsfield a répondu sans identifiant de génération. Rien n'a été enregistré, réessaie."
        )
    return job_id


def _bloc_du_job(donnees, job_id):
    """Le plus petit dict qui contient l'identifiant du job (sinon la racine)."""
    meilleur = None

    def visiter(noeud):
        nonlocal meilleur
        if isinstance(noeud, dict):
            if any(v == job_id for v in noeud.values() if isinstance(v, str)):
                meilleur = noeud
            for v in noeud.values():
                visiter(v)
        elif isinstance(noeud, list):
            for v in noeud:
                visiter(v)

    visiter(donnees)
    return meilleur if meilleur is not None else donnees


def interpreter_statut(resultat, job_id) -> dict:
    """Traduit la reponse de marketing_studio_v2_status en {"etat", "url", "erreur"}.
    etat : en_cours | terminee | echec."""
    donnees = _structure(resultat) or resultat or {}
    bloc = _bloc_du_job(donnees, job_id)
    statut = ""
    for cle, valeur in _parcourir(bloc):
        if str(cle).lower() in ("status", "state") and isinstance(valeur, str):
            statut = valeur.strip().lower()
            break
    url = None
    for cle, valeur in _parcourir(bloc):
        if isinstance(valeur, str) and valeur.startswith("https://") and str(cle).lower() in _CLES_URL:
            if valeur.split("?")[0].lower().endswith(_EXT_MEDIA):
                url = valeur
                break
    if statut in _ETATS_ECHEC:
        return {"etat": "echec", "url": None, "erreur": statut}
    if statut in _ETATS_FIN_OK or (url and statut not in ("queued", "pending", "in_progress", "processing", "running")):
        if url:
            return {"etat": "terminee", "url": url, "erreur": None}
        logging.warning("Marketing Studio status terminé sans adresse lisible : %s", _extrait_journal(resultat))
        return {"etat": "en_cours", "url": None, "erreur": None}
    return {"etat": "en_cours", "url": None, "erreur": None}


def lire_statut(job_id: str) -> dict:
    if not est_uuid(job_id):
        raise ErreurHiggsfield("Identifiant de génération invalide.")
    resultat = appeler_outil_marketing_interne("marketing_studio_v2_status", {"job_ids": [job_id]})
    return interpreter_statut(resultat, job_id)
