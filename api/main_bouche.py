"""Service bouche séparé : synthèse vocale bambara de test (12/11/2026).

Même modèle que le montage vidéo (api/main_montage.py) : un service à part, construit par
Dockerfile.bouche, pour que PyTorch et les voix ne pèsent jamais sur le backend principal.
Il ne dépend ni de Supabase ni d'api/auth.py : seul le jeton interne est vérifié.

Le backend principal le relaie vers la page de test (api/bouche.py) quand sa variable
BOUCHE_URL est définie. Aucune donnée de compte n'est stockée ici.
"""
import os
import secrets

from fastapi import FastAPI, Header
from fastapi.responses import Response
from pydantic import BaseModel

from core import bouche_bambara
from core.erreurs import erreur_api

app = FastAPI(title="Classinus bouche bambara")


def _verifier_jeton(authorization: str | None) -> None:
    attendu = os.environ.get("SUPABASE_SECRET", "")
    recu = (authorization or "").removeprefix("Bearer ").strip()
    if not attendu or not secrets.compare_digest(recu, attendu):
        raise erreur_api(401, "TOKEN_MANQUANT")


class DemandeSynthese(BaseModel):
    voix: str
    texte: str
    locuteur: int = 0


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "service": "bouche-bambara"}


@app.get("/voix")
def voix(authorization: str | None = Header(default=None)) -> dict:
    _verifier_jeton(authorization)
    return {"voix": bouche_bambara.lister_voix(), "texte_max": bouche_bambara.texte_max()}


@app.post("/synthese")
def synthese(demande: DemandeSynthese, authorization: str | None = Header(default=None)) -> Response:
    _verifier_jeton(authorization)
    try:
        audio = bouche_bambara.synthetiser(demande.voix, demande.texte, demande.locuteur)
    except bouche_bambara.BoucheErreur as e:
        raise erreur_api(e.statut, e.code)
    return Response(content=audio, media_type="audio/wav")
