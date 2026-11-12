"""Test des voix bambara : serveur et page dans un seul déploiement (dossier isolé).

Même principe que bambara-ecoute : un dossier autonome, sans lien avec le reste du backend,
sans base de données ni compte. Un déploiement Coolify unique sert la page et les voix,
donc une seule origine : pas de CORS, pas de contenu mixte.

Protection facultative : si TEST_ACCESS_TOKEN est défini, /voix et /synthese exigent le
jeton, que la page lit dans l'adresse (?token=VALEUR) et envoie dans l'en-tête X-Test-Token.
"""
import os
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

import voix

DOSSIER = Path(__file__).parent
app = FastAPI(title="Test des voix bambara")


def _precharger() -> None:
    for voix_id in voix.voix_actives():
        voix.charger(voix_id)


if os.environ.get("PRECHARGER", "1") != "0":
    threading.Thread(target=_precharger, daemon=True).start()


def _refus(x_test_token: str | None):
    attendu = os.environ.get("TEST_ACCESS_TOKEN", "")
    if attendu and not secrets.compare_digest(x_test_token or "", attendu):
        return JSONResponse({"erreur": "Accès refusé : ajoute ?token=VALEUR à l'adresse."}, status_code=401)
    return None


class Demande(BaseModel):
    voix: str
    texte: str
    locuteur: int = 0


@app.get("/")
def accueil():
    return FileResponse(DOSSIER / "static" / "index.html")


@app.get("/etat")
def etat():
    return {
        "protege": bool(os.environ.get("TEST_ACCESS_TOKEN")),
        "voix": voix.etat_voix(),
    }


@app.get("/voix")
def lister(x_test_token: str | None = Header(default=None)):
    refus = _refus(x_test_token)
    if refus:
        return refus
    return {"voix": voix.lister_voix(), "texte_max": voix.texte_max()}


@app.post("/synthese")
def synthese(demande: Demande, x_test_token: str | None = Header(default=None)):
    refus = _refus(x_test_token)
    if refus:
        return refus
    try:
        audio = voix.synthetiser(demande.voix, demande.texte, demande.locuteur)
    except voix.ErreurVoix as e:
        return JSONResponse({"erreur": e.message, "detail": e.detail}, status_code=e.statut)
    return Response(content=audio, media_type="audio/wav")
