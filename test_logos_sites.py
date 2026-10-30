"""Vérifie le logo d'un site côté serveur (globe de Google jamais pris pour un vrai logo), sans réseau."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import logos_sites  # noqa: E402
from core.logos_sites import ABSENT, INDISPONIBLE, TROUVE, logo_du_site, normaliser_site  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40


class _Reponse:
    def __init__(self, statut, contenu=b"", type_contenu="image/png", hote="t3.gstatic.com"):
        self.status_code = statut
        self.content = contenu
        self.headers = {"content-type": type_contenu}
        self.url = mock.Mock(host=hote)


class _Client:
    def __init__(self, reponse=None, erreur=None):
        self._reponse, self._erreur = reponse, erreur
        self.appels = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params=None):
        self.appels.append((url, params))
        if self._erreur:
            raise self._erreur
        return self._reponse


def _avec_client(client):
    return mock.patch.object(logos_sites.httpx, "Client", return_value=client)


class TestNormaliserSite(unittest.TestCase):
    def test_minuscules_et_sans_www(self):
        self.assertEqual(normaliser_site(" WWW.Linear.APP "), "linear.app")

    def test_garde_les_sous_domaines(self):
        self.assertEqual(normaliser_site("netlify-mcp.netlify.app"), "netlify-mcp.netlify.app")

    def test_refuse_ce_qui_n_est_pas_un_nom_de_site(self):
        for valeur in (None, "", "localhost", "127.0.0.1", "a b.com", "http://x.com", "x.com/chemin", "x.com:8080", "-x.com", 42):
            self.assertIsNone(normaliser_site(valeur), repr(valeur))


class TestLogoDuSite(unittest.TestCase):
    def setUp(self):
        logos_sites.vider_memoire()

    def test_vraie_icone_renvoyee(self):
        with _avec_client(_Client(_Reponse(200, PNG))):
            statut, octets, type_contenu, nom = logo_du_site("Linear.app")
        self.assertEqual((statut, octets, type_contenu, nom), (TROUVE, PNG, "image/png", "linear.app"))

    def test_globe_de_google_avec_404_n_est_jamais_un_logo(self):
        # Google envoie une image de globe AVEC le statut 404 : on doit répondre "absent" sans l'image.
        with _avec_client(_Client(_Reponse(404, PNG))):
            statut, octets, _type, _nom = logo_du_site("netlify-mcp.netlify.app")
        self.assertEqual(statut, ABSENT)
        self.assertIsNone(octets)

    def test_panne_ou_reponse_inattendue(self):
        with _avec_client(_Client(erreur=logos_sites.httpx.ConnectTimeout("lent"))):
            self.assertEqual(logo_du_site("a.com")[0], INDISPONIBLE)
        logos_sites.vider_memoire()
        with _avec_client(_Client(_Reponse(500))):
            self.assertEqual(logo_du_site("a.com")[0], INDISPONIBLE)

    def test_refuse_une_reponse_qui_n_est_pas_une_image(self):
        with _avec_client(_Client(_Reponse(200, b"<html>", "text/html"))):
            self.assertEqual(logo_du_site("a.com")[0], INDISPONIBLE)

    def test_refuse_une_redirection_vers_un_autre_hote(self):
        with _avec_client(_Client(_Reponse(200, PNG, hote="exemple-pirate.net"))):
            self.assertEqual(logo_du_site("a.com")[0], INDISPONIBLE)

    def test_nom_invalide_n_appelle_pas_google(self):
        client = _Client(_Reponse(200, PNG))
        with _avec_client(client):
            self.assertEqual(logo_du_site("pas un site")[0], INDISPONIBLE)
        self.assertEqual(client.appels, [])

    def test_reponse_gardee_en_memoire(self):
        client = _Client(_Reponse(200, PNG))
        with _avec_client(client):
            logo_du_site("linear.app")
            logo_du_site("www.linear.app")
        self.assertEqual(len(client.appels), 1)

    def test_absent_est_aussi_garde_et_expire(self):
        client = _Client(_Reponse(404, PNG))
        with _avec_client(client):
            logo_du_site("a.com")
            logo_du_site("a.com")
            self.assertEqual(len(client.appels), 1)
            with mock.patch.object(logos_sites.time, "time", return_value=10**10):
                logo_du_site("a.com")
        self.assertEqual(len(client.appels), 2)

    def test_memoire_bornee(self):
        with mock.patch.object(logos_sites, "MAX_ENTREES_MEMOIRE", 3), _avec_client(_Client(_Reponse(404))):
            for i in range(10):
                logo_du_site(f"site{i}.com")
        self.assertLessEqual(len(logos_sites._memoire), 3)


class TestRoute(unittest.TestCase):
    def setUp(self):
        logos_sites.vider_memoire()
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from slowapi.middleware import SlowAPIMiddleware

            from api.logos_sites import router
            from core.limitation_debit import limiteur
        except Exception as erreur:  # dépendance absente de cet environnement
            raise unittest.SkipTest(f"route non importable ici : {erreur}")
        app = FastAPI()
        app.state.limiter = limiteur
        app.add_middleware(SlowAPIMiddleware)
        app.include_router(router)
        self.client = TestClient(app)

    def test_trouve_renvoie_l_image_avec_cache(self):
        with _avec_client(_Client(_Reponse(200, PNG))):
            reponse = self.client.get("/api/logos-sites/linear.app")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.content, PNG)
        self.assertEqual(reponse.headers["content-type"], "image/png")
        self.assertIn("max-age=86400", reponse.headers["cache-control"])

    def test_absent_renvoie_404_sans_image(self):
        with _avec_client(_Client(_Reponse(404, PNG))):
            reponse = self.client.get("/api/logos-sites/netlify-mcp.netlify.app")
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.content, b"")

    def test_nom_invalide_renvoie_404(self):
        self.assertEqual(self.client.get("/api/logos-sites/localhost").status_code, 404)


if __name__ == "__main__":
    unittest.main()
