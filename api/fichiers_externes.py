"""
Relais des fichiers de sites externes (10/10/2026, demande de Bourama).
Toute la logique est dans core/relais_fichier_externe.py.

Deux routes :
- POST /api/fichiers-externes/lien : utilisateur connecte. Verifie l'adresse (anti-SSRF,
  taille, type reconnu sur les octets) et renvoie un lien de relais signe qui expire.
- GET/HEAD /fichiers/externe/{jeton}/{nom} : sert le fichier en flux avec les requetes
  partielles (Range). Pas d'authentification, un lecteur PDF ne peut pas joindre le
  jeton de connexion a ses requetes de pages (meme principe que /fichiers/archive).
  Ce n'est pas un proxy ouvert : seul un lien signe par l'etape precedente fonctionne.
  Le nom se termine par l'extension du fichier, ce qui suffit au chat pour choisir
  le bon lecteur.
"""

import os

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.relais_fichier_externe import ErreurRelais, creer_jeton, inspecter, ouvrir_fichier_externe

router = APIRouter(tags=["fichiers"])

_LIMITE_LIEN = os.environ.get("RELAIS_EXTERNE_LIMITE_LIEN") or "60/minute"
_LIMITE_FLUX = os.environ.get("RELAIS_EXTERNE_LIMITE") or "240/minute"

_EXTENSION_PAR_TYPE = {
    "ole": "doc",
    "texte": "txt",
}


class LienExternePayload(BaseModel):
    url: str


def _base_publique():
    try:
        from core.stockage_r2 import R2_PUBLIC_BASE_URL

        return (R2_PUBLIC_BASE_URL or "").rstrip("/")
    except Exception:
        return ""


@router.post("/api/fichiers-externes/lien")
@limiteur.limit(_LIMITE_LIEN)
def creer_lien_relais(request: Request, payload: LienExternePayload, utilisateur=Depends(utilisateur_courant)):
    url = (payload.url or "").strip()
    if not url or len(url) > 2048:
        raise erreur_api(400, "LIEN_EXTERNE_NON_AUTORISE")
    base = _base_publique()
    if not base:
        raise erreur_api(503, "RELAIS_EXTERNE_INDISPONIBLE")
    try:
        infos = inspecter(url)
        jeton = creer_jeton(url, infos["type"])
    except ErreurRelais as e:
        raise erreur_api(e.statut, e.code)

    nom = infos["nom"]
    extension = _EXTENSION_PAR_TYPE.get(infos["type"], infos["type"])
    if "." not in nom or nom.rsplit(".", 1)[-1].lower() != extension:
        nom = f"{nom}.{extension}"
    from urllib.parse import quote

    return {
        "url": f"{base}/fichiers/externe/{jeton}/{quote(nom, safe='')}",
        "type": infos["type"],
        "nom": nom,
        "taille": infos["taille"],
    }


@router.api_route("/fichiers/externe/{jeton}/{nom_fichier}", methods=["GET", "HEAD"])
@limiteur.limit(_LIMITE_FLUX)
def servir_fichier_externe(request: Request, jeton: str, nom_fichier: str):
    try:
        relais = ouvrir_fichier_externe(
            jeton,
            nom_fichier,
            request.method,
            request.headers.get("range"),
            telechargement=request.query_params.get("telecharger") == "1",
        )
    except ErreurRelais as e:
        raise erreur_api(e.statut, e.code)

    if request.method == "HEAD" or relais.statut == 416:
        return Response(status_code=relais.statut, headers=relais.entetes)

    entetes = dict(relais.entetes)
    type_contenu = entetes.pop("Content-Type")
    return StreamingResponse(relais.flux, status_code=relais.statut, headers=entetes, media_type=type_contenu)
