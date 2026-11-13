"""Relais du mode vocal bambara (13/11/2026, demande de Bourama).

Chaîne : l'utilisateur parle, Soloni transcrit seulement (service `bambara-ecoute`), le texte part à
l'IA de Classinus par le chat, et sa réponse est lue à voix haute par la voix Gemini (service
`bambara-bouche`). Le navigateur ne connaît ni l'adresse des deux services ni leur jeton : il
appelle ces trois routes avec son jeton de compte, et le relais interroge les services.

Rien n'est écrit en dur : tout vient de variables d'environnement.
  VOIX_BAMBARA_ECOUTE_URL    adresse du service Soloni, sans chemin.
  VOIX_BAMBARA_BOUCHE_URL    adresse du service de la voix Gemini, sans chemin.
  VOIX_BAMBARA_BOUCHE_TOKEN  (facultatif) jeton envoyé dans X-Test-Token, comme TEST_ACCESS_TOKEN du service.
  VOIX_BAMBARA_VOIX          (facultatif) identifiant de la voix, `gemini_tts` par défaut.
  VOIX_BAMBARA_TEXTE_MAX     (facultatif) longueur maximale d'un morceau de texte lu, 600 par défaut
                             (la même que TEXTE_MAX du service de voix).
  VOIX_BAMBARA_AUDIO_MAX_MO  (facultatif) taille maximale d'un enregistrement, 10 Mo par défaut.
  VOIX_BAMBARA_DELAI_S       (facultatif) attente maximale d'un service, 120 secondes par défaut.
Sans les deux adresses, /etat répond « disponible : faux » et le frontend ne propose pas le bambara :
rien d'autre ne change.

Aucune donnée n'est stockée (ni table, ni fichier) : l'audio et le texte ne font que passer. Rien à
ajouter à core/purge_compte.py ni à l'export de api/profiles.py.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from api.auth import get_secret, utilisateur_courant
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/voix-bambara", tags=["voix-bambara"])

VOIX_DEFAUT = "gemini_tts"
TEXTE_MAX_DEFAUT = 600
AUDIO_MAX_MO_DEFAUT = 10
DELAI_DEFAUT_S = 120.0


def _adresse(nom: str) -> str | None:
    base = (get_secret(nom) or "").strip().rstrip("/")
    return base if base.startswith(("http://", "https://")) else None


def _nombre(nom: str, defaut: float) -> float:
    try:
        valeur = float((get_secret(nom) or "").strip())
    except ValueError:
        return defaut
    return valeur if valeur > 0 else defaut


def texte_max() -> int:
    return int(_nombre("VOIX_BAMBARA_TEXTE_MAX", TEXTE_MAX_DEFAUT))


def audio_max_octets() -> int:
    return int(_nombre("VOIX_BAMBARA_AUDIO_MAX_MO", AUDIO_MAX_MO_DEFAUT) * 1024 * 1024)


def _delai_s() -> float:
    return _nombre("VOIX_BAMBARA_DELAI_S", DELAI_DEFAUT_S)


def _voix() -> str:
    return (get_secret("VOIX_BAMBARA_VOIX") or "").strip() or VOIX_DEFAUT


def _entetes_bouche() -> dict:
    jeton = (get_secret("VOIX_BAMBARA_BOUCHE_TOKEN") or "").strip()
    return {"X-Test-Token": jeton} if jeton else {}


def _exige(nom_adresse: str) -> str:
    base = _adresse(nom_adresse)
    if not base:
        raise erreur_api(503, "VOIX_BAMBARA_NON_CONFIGUREE")
    return base


@router.get("/etat")
def etat(utilisateur=Depends(utilisateur_courant)):
    """Dit au frontend si le bambara peut être proposé, et la taille des morceaux à lire."""
    return {
        "disponible": bool(_adresse("VOIX_BAMBARA_ECOUTE_URL") and _adresse("VOIX_BAMBARA_BOUCHE_URL")),
        "texte_max": texte_max(),
    }


@router.post("/transcrire")
def transcrire(fichier: UploadFile = File(...), utilisateur=Depends(utilisateur_courant)):
    """Envoie l'enregistrement à Soloni, qui transcrit seulement. Renvoie {"texte": ...}."""
    base = _exige("VOIX_BAMBARA_ECOUTE_URL")
    contenu = fichier.file.read(audio_max_octets() + 1)
    if not contenu or len(contenu) > audio_max_octets():
        raise erreur_api(400, "VOIX_BAMBARA_AUDIO_INVALIDE")
    try:
        reponse = httpx.post(
            f"{base}/transcrire",
            params={"moteur": "soloni"},
            files={"fichier": (fichier.filename or "voix", contenu, fichier.content_type or "application/octet-stream")},
            timeout=_delai_s(),
        )
    except httpx.HTTPError:
        logging.exception("Service Soloni injoignable")
        raise erreur_api(503, "VOIX_BAMBARA_INDISPONIBLE")
    if reponse.status_code == 400:
        raise erreur_api(400, "VOIX_BAMBARA_AUDIO_INVALIDE")
    if reponse.status_code != 200:
        logging.error("Service Soloni : statut %s", reponse.status_code)
        raise erreur_api(503, "VOIX_BAMBARA_INDISPONIBLE")
    try:
        texte = reponse.json().get("texte")
    except (ValueError, AttributeError):
        texte = None
    if not isinstance(texte, str):
        logging.error("Service Soloni : réponse sans texte")
        raise erreur_api(503, "VOIX_BAMBARA_INDISPONIBLE")
    return {"texte": texte.strip()}


class DemandeSynthese(BaseModel):
    texte: str


@router.post("/synthese")
def synthese(demande: DemandeSynthese, utilisateur=Depends(utilisateur_courant)):
    """Fait lire un morceau de texte par la voix Gemini. Renvoie un fichier WAV."""
    base = _exige("VOIX_BAMBARA_BOUCHE_URL")
    texte = demande.texte.strip()
    if not texte or len(texte) > texte_max():
        raise erreur_api(400, "VOIX_BAMBARA_TEXTE_INVALIDE")
    try:
        reponse = httpx.post(
            f"{base}/synthese",
            headers=_entetes_bouche(),
            json={"voix": _voix(), "texte": texte, "locuteur": 0},
            timeout=_delai_s(),
        )
    except httpx.HTTPError:
        logging.exception("Service de la voix Gemini injoignable")
        raise erreur_api(503, "VOIX_BAMBARA_INDISPONIBLE")
    if reponse.status_code != 200:
        logging.error("Service de la voix Gemini : statut %s", reponse.status_code)
        raise erreur_api(503, "VOIX_BAMBARA_INDISPONIBLE")
    return Response(content=reponse.content, media_type="audio/wav")
