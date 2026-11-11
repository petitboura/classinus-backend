"""Relais de la page de test « bouche bambara » (12/11/2026).

Le navigateur ne peut pas porter le jeton interne : il appelle ce relais avec son jeton de
compte, et le relais interroge le service séparé (api/main_bouche.py) avec SUPABASE_SECRET.
Réservé aux administrateurs : c'est un outil de test qui consomme du calcul.

Sans BOUCHE_URL, la page répond « non branchée » et rien d'autre ne change.
Aucune donnée de compte n'est stockée : ni table, ni fichier, donc rien à ajouter à
core/purge_compte.py ni à l'export de api/profiles.py.
"""
import logging
import os

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from api.auth import utilisateur_courant
from api.permissions_hierarchie import _est_admin
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/bouche", tags=["bouche"])

DELAI_DEFAUT_S = 180.0


def _base_url() -> str:
    base = (os.environ.get("BOUCHE_URL") or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise erreur_api(503, "BOUCHE_NON_CONFIGUREE")
    return base


def _delai_s() -> float:
    try:
        valeur = float((os.environ.get("BOUCHE_DELAI_S") or "").strip())
    except ValueError:
        return DELAI_DEFAUT_S
    return valeur if valeur > 0 else DELAI_DEFAUT_S


def _entetes() -> dict:
    secret = os.environ.get("SUPABASE_SECRET", "")
    if not secret:
        raise erreur_api(503, "BOUCHE_NON_CONFIGUREE")
    return {"Authorization": f"Bearer {secret}"}


def _exige_admin(utilisateur) -> None:
    if not _est_admin(utilisateur.id):
        raise erreur_api(403, "PAS_LE_DROIT_ADMIN")


def _relayer_erreur(reponse: httpx.Response):
    """Reprend le code d'erreur du service bouche, sans jamais laisser passer du JSON brut."""
    code = None
    try:
        corps = reponse.json()
    except ValueError:
        corps = None
    detail = corps.get("detail") if isinstance(corps, dict) else None
    if isinstance(detail, dict):
        code = detail.get("code")
    statut = reponse.status_code if reponse.status_code in (400, 404, 500, 503) else 503
    return erreur_api(statut, code if isinstance(code, str) and code.startswith("BOUCHE_") else "BOUCHE_INDISPONIBLE")


class DemandeSynthese(BaseModel):
    voix: str
    texte: str
    locuteur: int = 0


@router.get("/voix")
def lister_voix(utilisateur=Depends(utilisateur_courant)):
    _exige_admin(utilisateur)
    try:
        reponse = httpx.get(f"{_base_url()}/voix", headers=_entetes(), timeout=15.0)
    except httpx.HTTPError:
        logging.exception("Service bouche injoignable (liste des voix)")
        raise erreur_api(503, "BOUCHE_INDISPONIBLE")
    if reponse.status_code != 200:
        raise _relayer_erreur(reponse)
    return reponse.json()


@router.post("/synthese")
def synthetiser(demande: DemandeSynthese, utilisateur=Depends(utilisateur_courant)):
    _exige_admin(utilisateur)
    try:
        reponse = httpx.post(
            f"{_base_url()}/synthese",
            headers=_entetes(),
            json=demande.model_dump(),
            timeout=_delai_s(),
        )
    except httpx.HTTPError:
        logging.exception("Service bouche injoignable (synthèse)")
        raise erreur_api(503, "BOUCHE_INDISPONIBLE")
    if reponse.status_code != 200:
        raise _relayer_erreur(reponse)
    return Response(content=reponse.content, media_type="audio/wav")
