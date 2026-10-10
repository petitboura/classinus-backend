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


# Tous les formats (10/10/2026, demande Bourama) : echantillons d'octets de debut de fichier.
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 4000
SANS_EXTENSION = "https://a.org/fichier"


def _riff(sous_type):
    return b"RIFF\x24\x00\x00\x00" + sous_type + b"fmt " + b"\x00" * 40


FORMATS_RECONNUS = [
    # (octets, adresse, type attendu)
    (MP4, SANS_EXTENSION, "mp4"),
    (b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 40, SANS_EXTENSION, "mov"),
    (b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 40, SANS_EXTENSION, "m4a"),
    (b"\x00\x00\x00\x1cftypavif" + b"\x00" * 40, SANS_EXTENSION, "avif"),
    (b"\x00\x00\x00\x1cftypheic" + b"\x00" * 40, SANS_EXTENSION, "heic"),
    (b"\x00\x00\x00\x1cftypmif1" + b"\x00" * 40, SANS_EXTENSION, "heic"),
    (b"\x00\x00\x00\x1cftypmif1" + b"\x00" * 40, "https://a.org/photo.avif", "avif"),
    (b"\x00\x00\x00\x1cftyp3gp4" + b"\x00" * 40, SANS_EXTENSION, "3gp"),
    (b"\x1a\x45\xdf\xa3" + b"\x00" * 40, "https://a.org/film.webm", "webm"),
    (b"\x1a\x45\xdf\xa3" + b"\x00" * 40, "https://a.org/film.mkv", "mkv"),
    (b"\x1a\x45\xdf\xa3" + b"\x00" * 40, SANS_EXTENSION, "mkv"),
    (b"OggS\x00\x02" + b"\x00" * 40, SANS_EXTENSION, "ogg"),
    (b"OggS\x00\x02" + b"\x00" * 40, "https://a.org/film.ogv", "ogv"),
    (b"ID3\x04\x00\x00" + b"\x00" * 40, SANS_EXTENSION, "mp3"),
    (b"\xff\xfb\x90\x00" + b"\x00" * 40, SANS_EXTENSION, "mp3"),
    (b"\xff\xf1\x50\x80" + b"\x00" * 40, SANS_EXTENSION, "aac"),
    (_riff(b"WAVE"), SANS_EXTENSION, "wav"),
    (_riff(b"AVI "), SANS_EXTENSION, "avi"),
    (_riff(b"WEBP"), SANS_EXTENSION, "webp"),
    (b"fLaC\x00\x00\x00\x22" + b"\x00" * 40, SANS_EXTENSION, "flac"),
    (b"FORM\x00\x00\x00\x00AIFF" + b"\x00" * 40, SANS_EXTENSION, "aiff"),
    (b"MThd\x00\x00\x00\x06" + b"\x00" * 40, SANS_EXTENSION, "mid"),
    (b"FLV\x01\x05" + b"\x00" * 40, SANS_EXTENSION, "flv"),
    (b"\x30\x26\xb2\x75\x8e\x66\xcf\x11" + b"\x00" * 40, SANS_EXTENSION, "asf"),
    (b"\x00\x00\x01\xba" + b"\x00" * 40, SANS_EXTENSION, "mpeg"),
    (b"PK\x03\x04" + b"0" * 40, "https://a.org/livre.epub", "epub"),
    (b"PK\x03\x04" + b"0" * 40, "https://a.org/cours.odt", "odt"),
    (b"PK\x03\x04" + b"0" * 40, SANS_EXTENSION, "zip"),
    (b"{\\rtf1\\ansi bonjour}", SANS_EXTENSION, "rtf"),
    (b"AT&TFORM\x00\x00\x00\x00DJVM" + b"\x00" * 40, SANS_EXTENSION, "djvu"),
    (b"\x00" * 60 + b"BOOKMOBI" + b"\x00" * 40, SANS_EXTENSION, "mobi"),
    (b"II*\x00" + b"\x00" * 40, SANS_EXTENSION, "tiff"),
    (b"MM\x00*" + b"\x00" * 40, SANS_EXTENSION, "tiff"),
    (b"BM" + b"\x00" * 12 + b"\x28\x00\x00\x00" + b"\x00" * 40, SANS_EXTENSION, "bmp"),
    (b"7z\xbc\xaf\x27\x1c" + b"\x00" * 40, SANS_EXTENSION, "7z"),
    (b"Rar!\x1a\x07\x00" + b"\x00" * 40, SANS_EXTENSION, "rar"),
    (b"\x1f\x8b\x08\x00" + b"\x00" * 40, SANS_EXTENSION, "gz"),
    (b"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n", "https://a.org/sous_titres.srt", "texte"),
]


class TousLesFormats(unittest.TestCase):
    def test_formats_reconnus_sur_les_octets(self):
        for octets, adresse, attendu in FORMATS_RECONNUS:
            with self.subTest(attendu=attendu, adresse=adresse):
                self.assertEqual(rel.type_depuis_octets(octets, adresse), attendu)

    def test_chaque_type_reconnu_a_un_type_mime_impose(self):
        for octets, adresse, attendu in FORMATS_RECONNUS:
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, rel.TYPES_AUTORISES)
        for famille in (rel.TYPES_IMAGE, rel.TYPES_AUDIO, rel.TYPES_VIDEO):
            self.assertTrue(famille <= set(rel.TYPES_AUTORISES))
        self.assertEqual(rel.TYPES_MEDIA, rel.TYPES_IMAGE | rel.TYPES_AUDIO | rel.TYPES_VIDEO)

    def test_contenus_dangereux_toujours_refuses(self):
        dangereux = [
            (HTML, "https://a.org/page.html"),
            (HTML, "https://a.org/faux.mp4"),
            (HTML, "https://a.org/faux.epub"),
            (SVG, "https://a.org/image.svg"),
            (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>', "https://a.org/image.xml"),
            (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>', "https://a.org/faux.txt"),
            (b"MZ\x90\x00" + b"\x00" * 60, "https://a.org/programme.exe"),
            (b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 60, "https://a.org/programme"),
            (b"\xcf\xfa\xed\xfe" + b"\x00" * 60, "https://a.org/programme"),
            (b"#!/bin/sh\nrm -rf /\n", "https://a.org/script.sh"),
            (b"alert(1);\n", "https://a.org/script.js"),
            (b"<?php echo 1;", "https://a.org/page.php"),
            (b"BMW est une marque de voiture, pas une image.", SANS_EXTENSION),
            (_riff(b"XXXX"), SANS_EXTENSION),
        ]
        for octets, adresse in dangereux:
            with self.subTest(adresse=adresse):
                self.assertIsNone(rel.type_depuis_octets(octets, adresse))


class PlafondEtVideo(unittest.TestCase):
    def _app(self):
        from api import fichiers_externes as api_fe

        app = FastAPI()
        app.include_router(api_fe.router)
        return TestClient(app)

    def test_plafond_par_defaut_500_mo(self):
        with patch.dict(os.environ):
            os.environ.pop("RELAIS_EXTERNE_TAILLE_MAX", None)
            self.assertEqual(rel.plafond_octets(), 500 * 1024 * 1024)

    def test_plafond_reglable_par_variable(self):
        with patch.dict(os.environ, {"RELAIS_EXTERNE_TAILLE_MAX": "1234"}):
            self.assertEqual(rel.plafond_octets(), 1234)

    def test_plafond_propre_a_un_appel(self):
        amont = _amont(contenu=MP4, entetes={"Content-Length": "5000"}, url="https://exemple.org/clip.mp4")
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            with self.assertRaises(rel.ErreurRelais) as c:
                rel.inspecter("https://exemple.org/clip.mp4", plafond=1000)
        self.assertEqual(c.exception.statut, 413)

    def test_video_de_150_mo_acceptee_par_le_relais(self):
        amont = _amont(contenu=MP4, entetes={"Content-Length": str(150 * 1024 * 1024)}, url="https://exemple.org/clip.mp4")
        with patch.dict(os.environ), _sans_ssrf(), patch("requests.request", return_value=amont):
            os.environ.pop("RELAIS_EXTERNE_TAILLE_MAX", None)
            infos = rel.inspecter("https://exemple.org/clip.mp4")
        self.assertEqual(infos["type"], "mp4")

    def test_creation_du_lien_video_sans_extension(self):
        amont = _amont(contenu=MP4, entetes={"Content-Length": str(len(MP4))}, url="https://exemple.org/video")
        with _sans_ssrf(), patch("requests.request", return_value=amont), patch("api.fichiers_externes._base_publique", return_value="https://api.test"):
            r = self._app().post("/api/fichiers-externes/lien", json={"url": "https://exemple.org/video"})
        self.assertEqual(r.status_code, 200)
        corps = r.json()
        self.assertEqual((corps["type"], corps["nom"]), ("mp4", "video.mp4"))
        self.assertTrue(corps["url"].endswith("/video.mp4"))

    def test_video_servie_avec_type_impose_et_plages(self):
        jeton = rel.creer_jeton("https://exemple.org/clip.mp4", "mp4")
        morceau = MP4[100:200]
        amont = _amont(
            statut=206,
            contenu=morceau,
            entetes={"Content-Type": "text/html", "Content-Range": f"bytes 100-199/{len(MP4)}", "Content-Length": "100"},
            url="https://exemple.org/clip.mp4",
        )
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/clip.mp4", headers={"Range": "bytes=100-199"})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.headers["content-type"], "video/mp4")
        self.assertEqual(r.headers["content-range"], f"bytes 100-199/{len(MP4)}")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", r.headers["content-security-policy"])
        self.assertEqual(r.content, morceau)

    def test_debut_de_video_servi_en_entier(self):
        jeton = rel.creer_jeton("https://exemple.org/clip.mp4", "mp4")
        amont = _amont(contenu=MP4, url="https://exemple.org/clip.mp4")
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/clip.mp4")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, MP4)

    def test_page_html_a_la_place_de_la_video_coupee(self):
        jeton = rel.creer_jeton("https://exemple.org/clip.mp4", "mp4")
        amont = _amont(contenu=HTML, url="https://exemple.org/clip.mp4")
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/clip.mp4")
        self.assertEqual(r.content, b"")

    def test_epub_servi_avec_son_type(self):
        contenu = b"PK\x03\x04" + b"0" * 4000
        jeton = rel.creer_jeton("https://exemple.org/livre.epub", "epub")
        amont = _amont(contenu=contenu, url="https://exemple.org/livre.epub")
        with _sans_ssrf(), patch("requests.request", return_value=amont):
            r = self._app().get(f"/fichiers/externe/{jeton}/livre.epub")
        self.assertEqual(r.headers["content-type"], "application/epub+zip")
        self.assertEqual(r.content, contenu)


if __name__ == "__main__":
    unittest.main()
