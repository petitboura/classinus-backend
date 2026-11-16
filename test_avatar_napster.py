"""Avatar Napster du mode vocal (16/11/2026) : interrupteur, relais du jeton, aucun identifiant d'élève envoyé."""
import logging
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import avatar_napster
from api.auth import utilisateur_courant
from core.erreurs import MESSAGES_EN, MESSAGES_FR

VARIABLES = ("AVATAR_NAPSTER_ACTIF", "NAPSTER_API_KEY", "NAPSTER_AGENT_ID", "NAPSTER_API_URL", "AVATAR_NAPSTER_DELAI_MIN_S",
             "AVATAR_NAPSTER_ACCUEIL", "AVATAR_NAPSTER_CONSIGNES")


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)
    avatar_napster._dernier_demarrage.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(avatar_napster.router)
    app.dependency_overrides[utilisateur_courant] = lambda: SimpleNamespace(id="u1")
    return TestClient(app)


def allumer(monkeypatch):
    monkeypatch.setenv("AVATAR_NAPSTER_ACTIF", "1")
    monkeypatch.setenv("NAPSTER_API_KEY", "cle")
    monkeypatch.setenv("NAPSTER_AGENT_ID", "agent_1")
    monkeypatch.setenv("AVATAR_NAPSTER_DELAI_MIN_S", "0")


def reponse_napster(code=200, corps=None):
    return httpx.Response(code, json=corps if corps is not None else {"token": "jeton-court", "connection": {"id": "c1"}},
                          request=httpx.Request("POST", "https://x"))


def test_eteint_par_defaut(client):
    assert client.get("/api/avatar-napster/etat").json() == {"disponible": False}
    assert client.post("/api/avatar-napster/jeton").status_code == 503


def test_interrupteur_eteint_meme_avec_les_cles(client, monkeypatch):
    allumer(monkeypatch)
    monkeypatch.setenv("AVATAR_NAPSTER_ACTIF", "0")
    assert client.get("/api/avatar-napster/etat").json() == {"disponible": False}


def test_allume_sans_cles_reste_indisponible(client, monkeypatch):
    monkeypatch.setenv("AVATAR_NAPSTER_ACTIF", "1")
    assert client.get("/api/avatar-napster/etat").json() == {"disponible": False}


def test_allume_et_configure(client, monkeypatch):
    allumer(monkeypatch)
    assert client.get("/api/avatar-napster/etat").json() == {"disponible": True}


def test_jeton_aucun_identifiant_eleve_envoye(client, monkeypatch):
    allumer(monkeypatch)
    with patch("api.avatar_napster.httpx.post", return_value=reponse_napster()) as appel:
        r = client.post("/api/avatar-napster/jeton")
    assert r.status_code == 200
    donnees = r.json()
    assert donnees["token"] == "jeton-court"
    assert donnees["nom_outil"] == "demander_a_classinus"
    assert donnees["consignes"].strip()
    url = appel.call_args.args[0]
    assert url == "https://companion-api.napster.com/public/agents/agent_1/connections"
    assert appel.call_args.kwargs["headers"]["X-Api-Key"] == "cle"
    assert appel.call_args.kwargs["json"] == {"channelType": "webrtc"}  # ni externalClientId ni profil
    assert "cle" not in str(donnees)


def test_erreur_napster_devient_indisponible(client, monkeypatch):
    allumer(monkeypatch)
    with patch("api.avatar_napster.httpx.post", return_value=reponse_napster(401, {"error": "x"})):
        r = client.post("/api/avatar-napster/jeton")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "AVATAR_NAPSTER_INDISPONIBLE"


def test_reseau_en_panne(client, monkeypatch):
    allumer(monkeypatch)
    with patch("api.avatar_napster.httpx.post", side_effect=httpx.ConnectError("x")):
        assert client.post("/api/avatar-napster/jeton").status_code == 503


def test_reponse_sans_jeton(client, monkeypatch):
    allumer(monkeypatch)
    with patch("api.avatar_napster.httpx.post", return_value=reponse_napster(200, {"connection": {}})):
        assert client.post("/api/avatar-napster/jeton").status_code == 503


def test_delai_minimum_entre_deux_demarrages(client, monkeypatch):
    allumer(monkeypatch)
    monkeypatch.setenv("AVATAR_NAPSTER_DELAI_MIN_S", "60")
    with patch("api.avatar_napster.httpx.post", return_value=reponse_napster()):
        assert client.post("/api/avatar-napster/jeton").status_code == 200
        r = client.post("/api/avatar-napster/jeton")
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "AVATAR_NAPSTER_TROP_RAPIDE"


def test_texte_vide_supprime_l_accueil(client, monkeypatch):
    allumer(monkeypatch)
    monkeypatch.setenv("AVATAR_NAPSTER_ACCUEIL", "")
    with patch("api.avatar_napster.httpx.post", return_value=reponse_napster()):
        assert client.post("/api/avatar-napster/jeton").json()["accueil"] == ""


def test_codes_d_erreur_en_francais_et_anglais():
    for code in ("AVATAR_NAPSTER_NON_CONFIGURE", "AVATAR_NAPSTER_INDISPONIBLE", "AVATAR_NAPSTER_TROP_RAPIDE"):
        assert code in MESSAGES_FR and code in MESSAGES_EN
