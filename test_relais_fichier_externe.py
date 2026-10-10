"""Relais des fichiers externes : aucun acces reseau, le site distant est simule."""

import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("RELAIS_EXTERNE_SECRET", "secret-de-test")

# api.auth se connecte a Supabase a l'import : on le remplace, la connexion n'est pas l'objet du test.
import sys
import types

_faux_auth = types.ModuleType("api.auth")
_faux_auth.utilisateur_courant = lambda: {"id": "test"}
sys.modules.setdefault("api.auth", _faux_auth)

from core import relais_fichier_externe as rel
from core.securite_url import UrlNonAutorisee

PDF = b"%PDF-1.4 " + b"x" * 3000
HTML = b"<!doctype html><html><script>alert(1)</script></html>"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _amont(statut=200, contenu=PDF, entetes=None, url="https://exemple.org/cours.pdf"):
    r = MagicMock()
    r.status_code = statut
    r.headers = entetes if entetes is not None else {"Content-Length": str(len(contenu))}
    r.url = url
    r.iter_content.side_effect = lambda n: iter([contenu[i:i + n] for i in range(0, len(contenu), n)])
    return r


def _sans_ssrf():
    return patch("core.relais_fichier_externe.valider_url_externe", lambda u: None)


class TypeDepuisOctets(unittest.TestCase):
    def test_types_autorises(self):
        self.assertEqual(rel.type_depuis_octets(PDF, "https://a.org/x"), "pdf")
        self.assertEqual(rel.type_depuis_octets(b"\x89PNG\r\n\x1a\n" + b"0" * 20, "https://a.org/x"), "png")
        self.assertEqual(rel.type_depuis_octets(b"PK\x03\x04" + b"0" * 20, "https://a.org/c.docx"), "docx")
        self.assertEqual(rel.type_depuis_octets(b"bonjour,monde\n1,2\n", "https://a.org/d.csv"), "texte")

    def test_html_svg_et_inconnu_refuses(self):
        self.assertIsNone(rel.type_depuis_octets(HTML, "https://a.org/page.html"))
        self.assertIsNone(rel.type_depuis_octets(SVG, "https://a.org/image.svg"))
        self.assertIsNone(rel.type_depuis_octets(HTML, "https://a.org/faux.pdf"))
        self.assertIsNone(rel.type_depuis_octets(HTML, "https://a.org/faux.txt"))
        self.assertIsNone(rel.type_depuis_octets(b"MZ\x90\x00", "https://a.org/x.exe"))


class Jeton(unittest.TestCase):
    def test_aller_retour(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        self.assertEqual(rel.lire_jeton(jeton), ("https://exemple.org/cours.pdf", "pdf"))

    def test_falsifie_refuse(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        corps, signature = jeton.split(".")
        autre = rel.creer_jeton("https://autre.org/x.pdf", "pdf").split(".")[0]
        for faux in (f"{autre}.{signature}", f"{corps}.AAAA", "n'importe quoi", ""):
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.lire_jeton(faux)
            self.assertEqual(c.exception.statut, 403)

    def test_expire_refuse(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf", maintenant=1000)
        with self.assertRaises(rel.ErreurRelais):
            rel.lire_jeton(jeton)


class Inspection(unittest.TestCase):
    def test_pdf_accepte(self):
        with _sans_ssrf(), patch("requests.request", return_value=_amont()):
            infos = rel.inspecter("https://exemple.org/cours.pdf")
        self.assertEqual((infos["type"], infos["nom"]), ("pdf", "cours.pdf"))

    def test_html_refuse_meme_declare_pdf(self):
        amont = _amont(contenu=HTML, entetes={"Content-Type": "application/pdf", "Content-Length": str(len(HTML))})
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.inspecter("https://exemple.org/faux.pdf")
        self.assertEqual(c.exception.code, "TYPE_FICHIER_NON_AUTORISE")

    def test_trop_gros_refuse(self):
        amont = _amont(entetes={"Content-Length": str(rel.plafond_octets() + 1)})
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.inspecter("https://exemple.org/gros.pdf")
        self.assertEqual(c.exception.statut, 413)

    def test_ssrf_refuse(self):
        def refuse(url):
            raise UrlNonAutorisee("interne")

        with patch("core.relais_fichier_externe.valider_url_externe", refuse), patch("requests.request") as req:
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.inspecter("http://169.254.169.254/x.pdf")
        self.assertEqual(c.exception.code, "LIEN_EXTERNE_NON_AUTORISE")
        req.assert_not_called()

    def test_redirection_vers_adresse_interne_refusee(self):
        validees = []

        def valide(url):
            validees.append(url)
            if "interne" in url:
                raise UrlNonAutorisee("interne")

        redirection = _amont(statut=302, entetes={"Location": "http://interne.local/secret.pdf"})
        with patch("core.relais_fichier_externe.valider_url_externe", valide), patch("requests.request", return_value=redirection):
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.inspecter("https://exemple.org/lien")
        self.assertEqual(c.exception.code, "LIEN_EXTERNE_NON_AUTORISE")
        self.assertEqual(validees, ["https://exemple.org/lien", "http://interne.local/secret.pdf"])

    def test_trop_de_redirections(self):
        boucle = _amont(statut=302, entetes={"Location": "https://exemple.org/encore"})
        with _sans_ssrf(), patch("requests.request", return_value=boucle):
            with self.assertRaises(rel.ErreurRelais):
                rel.inspecter("https://exemple.org/boucle")


class Relais(unittest.TestCase):
    def _app(self):
        from api import fichiers_externes as api_fe

        app = FastAPI()
        app.include_router(api_fe.router)
        return TestClient(app)

    def test_en_tetes_imposes_par_nous(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        amont = _amont(entetes={"Content-Type": "text/html", "Content-Length": str(len(PDF))})
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/cours.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, PDF)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", r.headers["content-security-policy"])
        self.assertTrue(r.headers["content-disposition"].startswith("inline"))

    def test_telechargement_en_piece_jointe(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        with _sans_ssrf(), patch("requests.request", return_value=_amont()):
            r = self._app().get(f"/fichiers/externe/{jeton}/cours.pdf?telecharger=1")
        self.assertTrue(r.headers["content-disposition"].startswith("attachment"))

    def test_creation_du_lien(self):
        with _sans_ssrf(), patch("requests.request", return_value=_amont()), patch("api.fichiers_externes._base_publique", return_value="https://api.test"):
            r = self._app().post("/api/fichiers-externes/lien", json={"url": "https://exemple.org/cours.pdf"})
        self.assertEqual(r.status_code, 200)
        corps = r.json()
        self.assertEqual((corps["type"], corps["nom"]), ("pdf", "cours.pdf"))
        self.assertTrue(corps["url"].startswith("https://api.test/fichiers/externe/"))
        self.assertTrue(corps["url"].endswith("/cours.pdf"))

    def test_creation_du_lien_refuse_html(self):
        amont = _amont(contenu=HTML, entetes={})
        with _sans_ssrf(), patch("requests.request", return_value=amont), patch("api.fichiers_externes._base_publique", return_value="https://api.test"):
            r = self._app().post("/api/fichiers-externes/lien", json={"url": "https://exemple.org/page"})
        self.assertEqual(r.status_code, 415)

    def test_jeton_invalide_403(self):
        r = self._app().get("/fichiers/externe/faux.jeton/cours.pdf")
        self.assertEqual(r.status_code, 403)

    def test_contenu_change_apres_delivrance_coupe(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        amont = _amont(contenu=HTML)
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/cours.pdf")
        self.assertEqual(r.content, b"")

    def test_plage_transmise_et_plage_multiple_ignoree(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        morceau = PDF[100:200]
        amont = _amont(statut=206, contenu=morceau, entetes={"Content-Range": f"bytes 100-199/{len(PDF)}", "Content-Length": "100"})
        with _sans_ssrf(), patch("requests.request", return_value=amont) as req:
            r = self._app().get(f"/fichiers/externe/{jeton}/cours.pdf", headers={"Range": "bytes=100-199"})
            self.assertEqual(req.call_args.kwargs["headers"]["Range"], "bytes=100-199")
            self.assertEqual(r.status_code, 206)
            self._app().get(f"/fichiers/externe/{jeton}/cours.pdf", headers={"Range": "bytes=0-1,5-9"})
            self.assertNotIn("Range", req.call_args.kwargs["headers"])

    def test_aucun_cookie_ni_autorisation_transmis(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        with _sans_ssrf(), patch("requests.request", return_value=_amont()) as req:
            self._app().get(
                f"/fichiers/externe/{jeton}/cours.pdf",
                headers={"Authorization": "Bearer secret", "Cookie": "session=abc"},
            )
        envoyes = {k.lower() for k in req.call_args.kwargs["headers"]}
        self.assertFalse(envoyes & {"authorization", "cookie"})

    def test_plafond_en_cours_de_flux(self):
        jeton = rel.creer_jeton("https://exemple.org/cours.pdf", "pdf")
        with _sans_ssrf(), patch("requests.request", return_value=_amont(entetes={})), patch.object(rel, "plafond_octets", return_value=1000):
            r = self._app().get(f"/fichiers/externe/{jeton}/cours.pdf")
        self.assertLessEqual(len(r.content), 1000)


if __name__ == "__main__":
    unittest.main()
