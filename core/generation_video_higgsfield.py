"""Client de l'API Higgsfield (clé partagée), pour la vidéo et l'image.

Indépendant du flux fal.ai existant. Les demandes sont construites dans
core/higgsfield_requetes.py. Ici : envoi, suivi, estimation du coût, annulation.
Docs : https://docs.higgsfield.ai (adresse de base, authentification, statuts).
"""
import logging
import os
import re
import uuid

import requests

from core.higgsfield_requetes import ErreurHiggsfield

BASE_URL = "https://api.higgsfield.ai"
DELAI_SECONDES = 30

# Statuts renvoyés par Higgsfield, ramenés à cinq états simples pour l'IA.
_ETATS = {
    "queued": "en_cours",
    "in_progress": "en_cours",
    "processing": "en_cours",
    "running": "en_cours",
    "pending": "en_cours",
    "completed": "terminee",
    "complete": "terminee",
    "succeeded": "terminee",
    "success": "terminee",
    "failed": "echec",
    "nsfw": "bloquee",
    "canceled": "annulee",
    "cancelled": "annulee",
}


def _credential():
    cle = os.environ.get("HIGGSFIELD_API_KEY")
    if cle:
        return cle
    cle_id = os.environ.get("HIGGSFIELD_API_KEY_ID")
    cle_secret = os.environ.get("HIGGSFIELD_API_KEY_SECRET")
    if not cle_id or not cle_secret:
        return None
    return f"{cle_id}:{cle_secret}"


def higgsfield_api_disponible() -> bool:
    return _credential() is not None


def _entetes(extra=None) -> dict:
    credential = _credential()
    if not credential:
        raise ErreurHiggsfield("La clé API Higgsfield n'est pas configurée.")
    entetes = {"Authorization": f"Key {credential}", "Content-Type": "application/json"}
    if extra:
        entetes.update(extra)
    return entetes


def _message_refus(reponse) -> str:
    """Phrase lisible pour un refus de Higgsfield, sans détail technique inutile."""
    code = reponse.status_code
    if code in (401, 402, 403):
        return "Higgsfield a refusé la demande (clé invalide ou crédits insuffisants)."
    if code == 429:
        return "Trop de demandes en même temps, réessaie dans un instant."
    if code >= 500:
        return "Higgsfield est indisponible pour le moment, réessaie plus tard."
    detail = ""
    try:
        donnees = reponse.json()
        if isinstance(donnees, dict):
            detail = str(donnees.get("detail") or donnees.get("error") or donnees.get("message") or "")
    except ValueError:
        detail = ""
    detail = detail.strip()[:200]
    return f"Higgsfield a refusé cette demande : {detail}" if detail else "Higgsfield a refusé cette demande."


def _verifier(reponse, contexte: str):
    if reponse.ok:
        return
    logging.error("ERREUR Higgsfield (%s) : code %s, %s", contexte, reponse.status_code, (reponse.text or "")[:500])
    raise ErreurHiggsfield(_message_refus(reponse))


def _post(chemin: str, corps=None, avec_idempotence: bool = False):
    """Envoie une demande. Avec idempotence, un nouvel essai après une coupure ne crée pas de doublon facturé."""
    cle = str(uuid.uuid4())
    extra = {"Idempotency-Key": cle} if avec_idempotence else None
    for tentative in (1, 2):
        try:
            return requests.post(
                f"{BASE_URL}/{chemin}",
                headers=_entetes(extra),
                json=corps if corps is not None else {},
                timeout=DELAI_SECONDES,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            logging.error("ERREUR Higgsfield (envoi %s, essai %s) : %s", chemin, tentative, e)
            if tentative == 2 or not avec_idempotence:
                raise ErreurHiggsfield("Higgsfield ne répond pas, réessaie plus tard.")


def lancer_generation(adresse_modele: str, corps: dict) -> dict:
    reponse = _post(adresse_modele, corps, avec_idempotence=True)
    _verifier(reponse, "lancement")
    donnees = reponse.json()
    request_id = donnees.get("request_id") or donnees.get("id")
    if not request_id:
        raise ErreurHiggsfield("Higgsfield n'a pas renvoyé d'identifiant de génération.")
    return {"request_id": request_id, "statut": donnees.get("status", "queued")}


def estimer_cout(adresse_modele: str, corps: dict) -> dict:
    """Coût annoncé avant de lancer (aucun crédit consommé)."""
    reponse = _post(f"estimate/{adresse_modele}", corps)
    _verifier(reponse, "estimation")
    donnees = reponse.json()
    return {"credits": donnees.get("credits"), "usd": donnees.get("usd")}


def _identifiant_valide(request_id: str) -> str:
    # L'identifiant est placé dans l'adresse appelée : on refuse tout ce qui n'est pas un identifiant simple.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_id or ""):
        raise ErreurHiggsfield("Identifiant de génération Higgsfield invalide.")
    return request_id


def _extraire_url(donnees):
    for bloc in (donnees, donnees.get("result"), donnees.get("output")):
        if not isinstance(bloc, dict):
            continue
        video = bloc.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        images = bloc.get("images")
        if isinstance(images, list) and images and isinstance(images[0], dict) and images[0].get("url"):
            return images[0]["url"]
        if bloc.get("video_url"):
            return bloc["video_url"]
    return None


def statut_generation(request_id: str) -> dict:
    """Renvoie {"etat": en_cours|terminee|echec|bloquee|annulee, "url": ..., "erreur": ...}."""
    identifiant = _identifiant_valide(request_id)
    reponse = requests.get(f"{BASE_URL}/requests/{identifiant}/status", headers=_entetes(), timeout=DELAI_SECONDES)
    _verifier(reponse, "suivi")
    donnees = reponse.json()
    brut = str(donnees.get("status", "")).lower()
    etat = _ETATS.get(brut, "en_cours")
    url = _extraire_url(donnees)
    if etat == "terminee" and not url:
        detail = requests.get(f"{BASE_URL}/requests/{identifiant}", headers=_entetes(), timeout=DELAI_SECONDES)
        _verifier(detail, "suivi détaillé")
        url = _extraire_url(detail.json())
    erreur = donnees.get("error") if isinstance(donnees.get("error"), str) else None
    return {"etat": etat, "url": url, "erreur": erreur}


def annuler_generation(request_id: str) -> bool:
    """True si annulée. False si elle a déjà commencé (Higgsfield répond 400)."""
    identifiant = _identifiant_valide(request_id)
    reponse = _post(f"requests/{identifiant}/cancel")
    if reponse.status_code == 400:
        return False
    _verifier(reponse, "annulation")
    return True
