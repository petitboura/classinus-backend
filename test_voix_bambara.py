"""Mode vocal bambara (13/11/2026) : relais vers Soloni et la voix Gemini, consignes à l'IA."""
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

import construction_system_prompt as csp
import prompt_voix_bambara
from api import voix_bambara
from api.auth import utilisateur_courant
from core.erreurs import MESSAGES_EN, MESSAGES_FR

ECOUTE = "http://soloni.exemple:8000"
BOUCHE = "http://voix.exemple:8000"
VARIABLES = ("VOIX_BAMBARA_ECOUTE_URL", "VOIX_BAMBARA_BOUCHE_URL", "VOIX_BAMBARA_BOUCHE_TOKEN", "VOIX_BAMBARA_VOIX",
             "VOIX_BAMBARA_TEXTE_MAX", "VOIX_BAMBARA_AUDIO_MAX_MO", "VOIX_BAMBARA_DELAI_S")


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(voix_bambara.router)
    app.dependency_overrides[utilisateur_courant] = lambda: SimpleNamespace(id="u1")
    return TestClient(app)


def _brancher(monkeypatch):
    monkeypatch.setenv("VOIX_BAMBARA_ECOUTE_URL", ECOUTE + "/")
    monkeypatch.setenv("VOIX_BAMBARA_BOUCHE_URL", BOUCHE)


def _reponse(statut=200, **kwargs):
    return httpx.Response(statut, request=httpx.Request("POST", "http://x"), **kwargs)


# --- /etat -----------------------------------------------------------------------------------------

def test_etat_sans_adresses_bambara_non_disponible(client):
    assert client.get("/api/voix-bambara/etat").json() == {"disponible": False, "texte_max": 600}


def test_etat_une_seule_adresse_non_disponible(client, monkeypatch):
    monkeypatch.setenv("VOIX_BAMBARA_ECOUTE_URL", ECOUTE)
    assert client.get("/api/voix-bambara/etat").json()["disponible"] is False


def test_etat_disponible_et_taille_des_morceaux_configurable(client, monkeypatch):
    _brancher(monkeypatch)
    monkeypatch.setenv("VOIX_BAMBARA_TEXTE_MAX", "300")
    assert client.get("/api/voix-bambara/etat").json() == {"disponible": True, "texte_max": 300}


def test_etat_adresse_sans_protocole_ignoree(client, monkeypatch):
    monkeypatch.setenv("VOIX_BAMBARA_ECOUTE_URL", "soloni.exemple")
    monkeypatch.setenv("VOIX_BAMBARA_BOUCHE_URL", BOUCHE)
    assert client.get("/api/voix-bambara/etat").json()["disponible"] is False


# --- /transcrire -----------------------------------------------------------------------------------

def _envoyer_audio(client, contenu=b"RIFFaudio"):
    return client.post("/api/voix-bambara/transcrire", files={"fichier": ("voix.webm", contenu, "audio/webm")})


def test_transcrire_non_configure(client):
    reponse = _envoyer_audio(client)
    assert reponse.status_code == 503
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_NON_CONFIGUREE"


def test_transcrire_envoie_a_soloni_seulement_et_renvoie_le_texte(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(json={"texte": "  i ni ce  ", "moteur": "soloni"})) as faux:
        reponse = _envoyer_audio(client)
    assert reponse.status_code == 200
    assert reponse.json() == {"texte": "i ni ce"}
    assert faux.call_args.args[0] == ECOUTE + "/transcrire"
    assert faux.call_args.kwargs["params"] == {"moteur": "soloni"}
    assert faux.call_args.kwargs["files"]["fichier"][1] == b"RIFFaudio"


def test_transcrire_audio_vide_refuse_sans_appeler_soloni(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post") as faux:
        reponse = _envoyer_audio(client, b"")
    assert reponse.status_code == 400
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_AUDIO_INVALIDE"
    faux.assert_not_called()


def test_transcrire_audio_trop_gros_refuse(client, monkeypatch):
    _brancher(monkeypatch)
    monkeypatch.setenv("VOIX_BAMBARA_AUDIO_MAX_MO", "0.001")
    with patch.object(voix_bambara.httpx, "post") as faux:
        reponse = _envoyer_audio(client, b"x" * 2000)
    assert reponse.status_code == 400
    faux.assert_not_called()


def test_transcrire_soloni_injoignable(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", side_effect=httpx.ConnectError("coupé")):
        reponse = _envoyer_audio(client)
    assert reponse.status_code == 503
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_INDISPONIBLE"


def test_transcrire_soloni_charge_encore_ne_fuit_pas_de_json_brut(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(503, json={"erreur": "Le modèle charge encore"})):
        reponse = _envoyer_audio(client)
    assert reponse.status_code == 503
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_INDISPONIBLE"


def test_transcrire_reponse_sans_texte(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(json={"autre": 1})):
        reponse = _envoyer_audio(client)
    assert reponse.status_code == 503


# --- /synthese -------------------------------------------------------------------------------------

def test_synthese_non_configuree(client):
    reponse = client.post("/api/voix-bambara/synthese", json={"texte": "i ni ce"})
    assert reponse.status_code == 503
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_NON_CONFIGUREE"


def test_synthese_voix_gemini_par_defaut_et_wav_renvoye(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(content=b"RIFFwav")) as faux:
        reponse = client.post("/api/voix-bambara/synthese", json={"texte": "  i ni ce  "})
    assert reponse.status_code == 200
    assert reponse.headers["content-type"] == "audio/wav"
    assert reponse.content == b"RIFFwav"
    assert faux.call_args.args[0] == BOUCHE + "/synthese"
    assert faux.call_args.kwargs["json"] == {"voix": "gemini_tts", "texte": "i ni ce", "locuteur": 0}
    assert faux.call_args.kwargs["headers"] == {}


def test_synthese_voix_et_jeton_viennent_des_variables(client, monkeypatch):
    _brancher(monkeypatch)
    monkeypatch.setenv("VOIX_BAMBARA_VOIX", "autre_voix")
    monkeypatch.setenv("VOIX_BAMBARA_BOUCHE_TOKEN", "secret")
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(content=b"w")) as faux:
        client.post("/api/voix-bambara/synthese", json={"texte": "a"})
    assert faux.call_args.kwargs["json"]["voix"] == "autre_voix"
    assert faux.call_args.kwargs["headers"] == {"X-Test-Token": "secret"}


@pytest.mark.parametrize("texte", ["", "   ", "a" * 601])
def test_synthese_texte_invalide_refuse(client, monkeypatch, texte):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post") as faux:
        reponse = client.post("/api/voix-bambara/synthese", json={"texte": texte})
    assert reponse.status_code == 400
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_TEXTE_INVALIDE"
    faux.assert_not_called()


def test_synthese_service_en_erreur(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", return_value=_reponse(401, json={"erreur": "Accès refusé"})):
        reponse = client.post("/api/voix-bambara/synthese", json={"texte": "a"})
    assert reponse.status_code == 503
    assert reponse.json()["detail"]["code"] == "VOIX_BAMBARA_INDISPONIBLE"


def test_synthese_service_injoignable(client, monkeypatch):
    _brancher(monkeypatch)
    with patch.object(voix_bambara.httpx, "post", side_effect=httpx.ReadTimeout("trop long")):
        reponse = client.post("/api/voix-bambara/synthese", json={"texte": "a"})
    assert reponse.status_code == 503


def test_routes_exigent_un_compte():
    app = FastAPI()
    app.include_router(voix_bambara.router)
    sans_compte = TestClient(app)
    assert sans_compte.get("/api/voix-bambara/etat").status_code in (401, 403)
    assert sans_compte.post("/api/voix-bambara/synthese", json={"texte": "a"}).status_code in (401, 403)


# --- consignes à l'IA ------------------------------------------------------------------------------

def _prompt(**kwargs):
    with patch.object(csp, "get_system_prompt", return_value="IDENTITE_AGENT"):
        return csp._construire_system_prompt("bonjour", "agent-test", user_id="u1", **kwargs)


def test_client_voix_bambara_recoit_les_deux_notes():
    prompt = _prompt(client="voix_bambara")
    assert prompt_voix_bambara.NOTE_TEXTE_SIMPLE in prompt
    assert prompt_voix_bambara.NOTE_BAMBARA_ORAL in prompt
    for mot in ("fichier", "lien", "code", "diagramme", "fiche", "QCM", "image", "tableau"):
        assert mot in prompt_voix_bambara.NOTE_TEXTE_SIMPLE
    assert "ni lire ni écrire" in prompt_voix_bambara.NOTE_BAMBARA_ORAL
    assert "bambara" in prompt_voix_bambara.NOTE_BAMBARA_ORAL


def test_notes_dans_la_partie_variable_la_partie_stable_ne_change_pas():
    avec = _prompt(client="voix_bambara")
    sans = _prompt()
    tete_avec, _, queue_avec = avec.partition(csp.MARQUEUR_PARTIE_VARIABLE)
    tete_sans, _, queue_sans = sans.partition(csp.MARQUEUR_PARTIE_VARIABLE)
    assert tete_avec == tete_sans
    assert "MODE VOCAL BAMBARA" in queue_avec
    assert queue_avec.endswith(queue_sans) or queue_sans in queue_avec


def test_autres_clients_inchanges():
    for client in (None, "thonny", "web", "VOIX_BAMBARA_AUTRE", ""):
        assert "MODE VOCAL BAMBARA" not in _prompt(client=client)


def test_valeur_du_client_insensible_a_la_casse_et_aux_espaces():
    assert prompt_voix_bambara.est_client_voix_bambara(" Voix_Bambara ")
    assert not prompt_voix_bambara.est_client_voix_bambara(None)
    assert not prompt_voix_bambara.est_client_voix_bambara(3)


# --- messages d'erreur ------------------------------------------------------------------------------

def test_codes_d_erreur_traduits():
    codes = [c for c in MESSAGES_FR if c.startswith("VOIX_BAMBARA_")]
    assert len(codes) == 4
    assert all(c in MESSAGES_EN for c in codes)
