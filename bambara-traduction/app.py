"""Test des traducteurs bambara : serveur et page dans un seul déploiement (dossier isolé).

Même principe que bambara-ecoute et bambara-bouche : un dossier autonome, sans lien avec le
reste du backend, sans base de données ni compte. Un déploiement Coolify unique sert la page
et les traducteurs, donc une seule origine : pas de CORS, pas de contenu mixte.

Protection facultative : si TEST_ACCESS_TOKEN est défini, /traduire exige le jeton, que la
page lit dans l'adresse (?token=VALEUR) et envoie dans l'en-tête X-Test-Token.
"""
import os
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import moteurs

DOSSIER = Path(__file__).parent
app = FastAPI(title="Test des traducteurs bambara")


def _precharger() -> None:
    for moteur_id in os.environ.get("PRECHARGER_MOTEURS", "").split(","):
        moteur_id = moteur_id.strip()
        if moteur_id in moteurs.MOTEURS:
            try:
                moteurs.charger(moteur_id)
            except Exception:  # l'échec est gardé dans /etat, la page l'affiche
                pass


if os.environ.get("PRECHARGER_MOTEURS"):
    threading.Thread(target=_precharger, daemon=True).start()


def _refus(x_test_token):
    attendu = os.environ.get("TEST_ACCESS_TOKEN", "")
    if attendu and not secrets.compare_digest(x_test_token or "", attendu):
        return JSONResponse({"erreur": "acces_refuse"}, status_code=401)
    return None


class Demande(BaseModel):
    moteur: str
    source: str
    cible: str
    texte: str


@app.get("/")
def accueil():
    return FileResponse(DOSSIER / "static" / "index.html")


@app.get("/etat")
def etat():
    return {
        "protege": bool(os.environ.get("TEST_ACCESS_TOKEN")),
        "moteurs": moteurs.etat_moteurs(),
        "moteurs_gardes": moteurs.moteurs_gardes(),
    }


@app.get("/moteurs")
def lister(x_test_token: str | None = Header(default=None)):
    refus = _refus(x_test_token)
    if refus:
        return refus
    return {"moteurs": moteurs.lister_moteurs(), "texte_max": moteurs.texte_max()}


@app.post("/traduire")
def traduire(demande: Demande, x_test_token: str | None = Header(default=None)):
    refus = _refus(x_test_token)
    if refus:
        return refus
    try:
        return moteurs.traduire(demande.moteur, demande.source, demande.cible, demande.texte)
    except moteurs.ErreurTraduction as e:
        return JSONResponse({"erreur": e.code, "detail": e.detail}, status_code=e.statut)
