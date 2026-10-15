"""
Tests (10/10/2026) du diagnostic des refus 4xx et de l'en-tête propre à Gallica.
Aucun accès réseau : requests.get est simulé. Ils ne prouvent PAS que Gallica
accepte le nouvel en-tête, seulement que le code l'envoie et trace les refus.
"""

import logging

import pytest
import requests

import core.recherche_documents_commun as commun
import core.recherche_gallica as gallica


class Reponse:
    def __init__(self, statut, texte="", entetes=None, contenu=b""):
        self.status_code = statut
        self.text = texte
        self.headers = entetes or {}
        self.content = contenu

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: Forbidden for url: https://x.test", response=self)


@pytest.fixture(autouse=True)
def _sans_attente(monkeypatch):
    monkeypatch.setattr(commun.time, "sleep", lambda s: None)


def _installer(monkeypatch, reponses):
    appels = []

    def faux(url, params=None, headers=None, timeout=None):
        appels.append({"url": url, "headers": headers})
        return reponses.pop(0)

    monkeypatch.setattr(commun.requests, "get", faux)
    return appels


def test_en_tetes_par_defaut_inchanges_pour_les_autres_sources(monkeypatch):
    appels = _installer(monkeypatch, [Reponse(200)])
    commun.appeler_service("https://x.test", {}, "HAL")
    assert appels[0]["headers"] == commun._EN_TETES


def test_en_tetes_propres_a_une_source(monkeypatch):
    appels = _installer(monkeypatch, [Reponse(200)])
    commun.appeler_service("https://x.test", {}, "Gallica", en_tetes={"User-Agent": "Test/1"})
    assert appels[0]["headers"] == {"User-Agent": "Test/1"}


def test_refus_403_trace_la_reponse_du_service(monkeypatch, caplog):
    page = "<html>\n  <body>Access   denied  by security rules</body></html>"
    _installer(monkeypatch, [Reponse(403, page, {"Server": "nginx", "Content-Type": "text/html"})] * 2)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(commun.ErreurRechercheSource) as erreur:
            commun.appeler_service("https://x.test", {}, "Gallica")
    assert "403" in str(erreur.value)  # le message renvoyé au modèle ne change pas
    trace = [m for m in caplog.messages if "refus 403" in m]
    assert len(trace) == 1  # une seule trace, pas une par essai
    assert "nginx" in trace[0] and "Access denied by security rules" in trace[0] and "\n" not in trace[0]


def test_refus_cloudflare_titre_code_et_en_tetes(monkeypatch, caplog):
    page = (
        "<!DOCTYPE html><html><head><title>Access denied | gallica.bnf.fr used Cloudflare to restrict access</title>"
        "<script>var x = 'secret-script';</script><style>.a{color:red}</style></head>"
        "<body><h1>Error 1020</h1><p>You do not have access to gallica.bnf.fr.</p></body></html>"
    )
    entetes = {"Server": "cloudflare", "Content-Type": "text/html", "cf-mitigated": "challenge", "cf-ray": "abc123-CDG"}
    _installer(monkeypatch, [Reponse(403, page, entetes)] * 2)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(commun.ErreurRechercheSource):
            commun.appeler_service("https://x.test", {}, "Gallica")
    trace = next(m for m in caplog.messages if "refus 403" in m)
    assert "cf-mitigated='challenge'" in trace and "cf-ray='abc123-CDG'" in trace
    assert "used Cloudflare to restrict access" in trace and "code erreur='1020'" in trace
    assert "You do not have access" in trace
    assert "secret-script" not in trace and "color:red" not in trace and "<" not in trace.split("texte de la page")[1]


def test_refus_sans_titre_ni_en_tetes_cloudflare(monkeypatch, caplog):
    _installer(monkeypatch, [Reponse(403, "Forbidden")] * 2)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(commun.ErreurRechercheSource):
            commun.appeler_service("https://x.test", {}, "HAL")
    trace = next(m for m in caplog.messages if "refus 403" in m)
    assert "titre=None" in trace and "code erreur=None" in trace and "cf-mitigated=None" in trace


def test_trace_coupee_a_300_caracteres(monkeypatch, caplog):
    _installer(monkeypatch, [Reponse(403, "a" * 5000)] * 2)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(commun.ErreurRechercheSource):
            commun.appeler_service("https://x.test", {}, "Gallica")
    trace = next(m for m in caplog.messages if "refus 403" in m)
    assert len(trace) < 800


def test_panne_5xx_et_succes_sans_trace_de_refus(monkeypatch, caplog):
    _installer(monkeypatch, [Reponse(503)] * 2)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(commun.ErreurRechercheSource):
            commun.appeler_service("https://x.test", {}, "HAL")
    assert not any("refus" in m for m in caplog.messages)
    _installer(monkeypatch, [Reponse(200)])
    assert commun.appeler_service("https://x.test", {}, "HAL").status_code == 200


def test_gallica_envoie_son_en_tete_ascii(monkeypatch):
    xml = (b'<?xml version="1.0"?><searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">'
           b"<numberOfRecords>0</numberOfRecords></searchRetrieveResponse>")
    appels = _installer(monkeypatch, [Reponse(200, contenu=xml)])
    monkeypatch.delenv("RECHERCHE_GALLICA_USER_AGENT", raising=False)
    gallica.rechercher_documents("analyse de Fourier", 3)
    agent = appels[0]["headers"]["User-Agent"]
    assert agent == gallica._USER_AGENT_PAR_DEFAUT and "Classinus" in agent
    agent.encode("ascii")  # aucun caractère accentué


def test_en_tete_gallica_modifiable_par_variable(monkeypatch):
    monkeypatch.setenv("RECHERCHE_GALLICA_USER_AGENT", "  Autre/2.0  ")
    assert gallica._en_tetes()["User-Agent"] == "Autre/2.0"
    monkeypatch.setenv("RECHERCHE_GALLICA_USER_AGENT", "   ")
    assert gallica._en_tetes()["User-Agent"] == gallica._USER_AGENT_PAR_DEFAUT
