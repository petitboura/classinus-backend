"""Relais de l'avatar Napster du mode vocal (16/11/2026, demande de Bourama).

L'avatar remplace seulement l'onde du mode vocal (plein écran et mini). La clé de l'API Napster
reste ici : le navigateur ne reçoit qu'un jeton de connexion valable quelques secondes, avec les
textes à donner à l'avatar (core/avatar_napster_config.py). Le cerveau reste celui de Classinus,
l'avatar lui passe les demandes comme le fait la voix Gemini Live.

Interrupteur : variable AVATAR_NAPSTER_ACTIF. Éteint, /etat répond « disponible : faux », le
frontend ne propose pas l'avatar et le mode vocal reste celui d'avant.

Aucun identifiant d'élève n'est envoyé à Napster (ni externalClientId, ni profil) : Napster ne
garde donc aucune mémoire, et aucune donnée n'est stockée ici (ni table, ni fichier). Rien à
ajouter à core/purge_compte.py ni à l'export de api/profiles.py.
"""
import logging
import time

import httpx
from fastapi import APIRouter, Depends

from api.auth import utilisateur_courant
from core import avatar_napster_config as reglages
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/avatar-napster", tags=["avatar-napster"])

DELAI_APPEL_S = 15.0

# Dernier démarrage par compte, en mémoire : évite qu'une boucle côté navigateur épuise les
# crédits Napster. Perdu au redémarrage du serveur, sans conséquence.
_dernier_demarrage: dict[str, float] = {}


def _disponible() -> bool:
    return reglages.est_actif() and reglages.est_configure()


@router.get("/etat")
def etat_avatar_napster(utilisateur=Depends(utilisateur_courant)):
    """Dit si l'avatar peut être proposé. Éteint ou non branché : « disponible : faux »."""
    return {"disponible": _disponible()}


@router.post("/jeton")
def creer_jeton_avatar_napster(utilisateur=Depends(utilisateur_courant)):
    """Demande à Napster un jeton de connexion à usage unique et renvoie les textes de l'avatar."""
    if not reglages.est_actif() or not reglages.est_configure():
        raise erreur_api(503, "AVATAR_NAPSTER_NON_CONFIGURE")

    maintenant = time.monotonic()
    precedent = _dernier_demarrage.get(utilisateur.id)
    if precedent is not None and maintenant - precedent < reglages.delai_minimum_s():
        raise erreur_api(429, "AVATAR_NAPSTER_TROP_RAPIDE")
    _dernier_demarrage[utilisateur.id] = maintenant
    # Le dictionnaire ne grossit pas sans fin : on oublie les comptes silencieux depuis longtemps.
    if len(_dernier_demarrage) > 5000:
        limite = maintenant - 3600
        for cle in [k for k, v in _dernier_demarrage.items() if v < limite]:
            _dernier_demarrage.pop(cle, None)

    url = f"{reglages.adresse_api()}/public/agents/{reglages.identifiant_agent()}/connections"
    try:
        reponse = httpx.post(
            url,
            headers={"X-Api-Key": reglages.cle_api(), "Content-Type": "application/json"},
            json={"channelType": "webrtc"},
            timeout=DELAI_APPEL_S,
        )
    except httpx.HTTPError as e:
        logging.error("Avatar Napster : appel impossible (%s)", type(e).__name__)
        raise erreur_api(503, "AVATAR_NAPSTER_INDISPONIBLE") from e
    if reponse.status_code != 200 and reponse.status_code != 201:
        # Le corps n'est pas journalisé en entier : il peut citer la configuration de l'agent.
        logging.error("Avatar Napster : réponse %s à la création de la connexion", reponse.status_code)
        raise erreur_api(503, "AVATAR_NAPSTER_INDISPONIBLE")
    try:
        jeton = reponse.json().get("token")
    except ValueError:
        jeton = None
    if not isinstance(jeton, str) or not jeton:
        logging.error("Avatar Napster : réponse sans jeton")
        raise erreur_api(503, "AVATAR_NAPSTER_INDISPONIBLE")
    return {"token": jeton, **reglages.reglages_avatar_napster()}
