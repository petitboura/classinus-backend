"""Ajout a la bibliotheque depuis un lien externe : aucun acces reseau, le site distant est simule."""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("RELAIS_EXTERNE_SECRET", "secret-de-test")
# Les modules de bibliotheque creent un client Supabase a l'import (sans se connecter).
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.test")
os.environ.setdefault("SUPABASE_KEY", os.environ["SUPABASE_SECRET"])
for cle in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
    os.environ.setdefault(cle, "https://r2.test" if cle == "R2_ENDPOINT" else "test")

# api.auth se connecte a Supabase a l'import : on le remplace, la connexion n'est pas l'objet du test.
_faux_auth = types.ModuleType("api.auth")
_faux_auth.utilisateur_courant = lambda: {"id": "test"}
_faux_auth.utilisateur_optionnel = lambda: None
_faux_auth.supabase = MagicMock()
_faux_auth.get_secret = lambda cle: os.environ.get(cle)
sys.modules["api.auth"] = _faux_auth

# Vectorisation et depliage de zip : dependances lourdes (PDF, IA), hors sujet ici.
_faux_vectorisation = types.ModuleType("file_attente_vectorisation")
for _nom in ("necessite_vectorisation_fichier_privee", "necessite_vectorisation_note", "reinitialiser_pour_reessai", "vectoriser_maintenant_privee"):
    setattr(_faux_vectorisation, _nom, MagicMock())
sys.modules["file_attente_vectorisation"] = _faux_vectorisation
_faux_zip = types.ModuleType("import_zip")
_faux_zip.deplier_zip_bibliotheque = MagicMock()
_faux_zip.est_zip = MagicMock(return_value=False)
sys.modules["import_zip"] = _faux_zip

from api import bibliotheque_utilisateur as biblio
from core.relais_fichier_externe import ErreurRelais

PDF = b"%PDF-1.4 " + b"x" * 3000
HTML = b"<!doctype html><html><script>alert(1)</script></html>"


def _amont(statut=200, contenu=PDF, entetes=None, url="https://exemple.org/cours.pdf"):
    r = MagicMock()
    r.status_code = statut
    r.headers = entetes if entetes is not None else {"Content-Length": str(len(contenu))}
    r.url = url
    r.iter_content.side_effect = lambda n: iter([contenu[i:i + n] for i in range(0, len(contenu), n)])
    return r


def _site(contenu=PDF, entetes=None):
    return patch(
        "core.relais_fichier_externe._requete_amont",
        lambda url, methode, plage: (_amont(contenu=contenu, entetes=entetes), url),
    )


class RecupererFichierExterne(unittest.TestCase):
    def test_pdf_recupere_en_entier(self):
        with _site():
            contenu, nom, mime = biblio._recuperer_fichier_externe("https://exemple.org/cours.pdf", None)
        self.assertEqual(contenu, PDF)
        self.assertEqual(nom, "cours.pdf")
        self.assertEqual(mime, "application/pdf")

    def test_titre_donne_le_nom_avec_extension(self):
        with _site():
            _, nom, _ = biblio._recuperer_fichier_externe("https://exemple.org/dl?id=12", "Cours de topologie")
        self.assertEqual(nom, "Cours de topologie.pdf")

    def test_titre_avec_chemin_garde_le_dernier_segment(self):
        with _site():
            _, nom, _ = biblio._recuperer_fichier_externe("https://exemple.org/dl?id=12", "../../etc/Cours.pdf")
        self.assertEqual(nom, "Cours.pdf")

    def test_page_html_deguisee_refusee(self):
        with _site(contenu=HTML):
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/faux.pdf", None)
        self.assertEqual(c.exception.statut, 415)

    def test_fichier_incomplet_refuse(self):
        # Le site annonce plus d'octets qu'il n'en livre : le fichier est incomplet.
        with _site(entetes={"Content-Length": str(len(PDF) + 500)}):
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/cours.pdf", None)
        self.assertEqual(c.exception.statut, 502)

    def test_zip_refuse(self):
        zip_ = b"PK\x03\x04" + b"0" * 4000
        with _site(contenu=zip_):
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/archive.zip", None)
        self.assertEqual(c.exception.statut, 415)


class ImportGardeSesLimitesApresElargissementDuRelais(unittest.TestCase):
    """Le relais accepte maintenant tous les formats et 500 Mo : l'import dans la bibliotheque, non."""

    MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 4000

    def test_video_refusee_alors_que_le_relais_l_accepte(self):
        from core import relais_fichier_externe as rel

        with _site(contenu=self.MP4):
            self.assertEqual(rel.inspecter("https://exemple.org/clip.mp4")["type"], "mp4")
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/clip.mp4", None)
        self.assertEqual(c.exception.statut, 415)

    def test_epub_et_son_refuses(self):
        for contenu, adresse in (
            (b"PK\x03\x04" + b"0" * 4000, "https://exemple.org/livre.epub"),
            (b"ID3\x04\x00\x00" + b"\x00" * 4000, "https://exemple.org/cours"),
        ):
            with self.subTest(adresse=adresse), _site(contenu=contenu):
                with self.assertRaises(ErreurRelais) as c:
                    biblio._recuperer_fichier_externe(adresse, None)
            self.assertEqual(c.exception.statut, 415)

    def test_plafond_de_100_mo_conserve_par_defaut(self):
        trop_gros = {"Content-Length": str(150 * 1024 * 1024)}
        with patch.dict(os.environ), _site(entetes=trop_gros):
            os.environ.pop("BIBLIOTHEQUE_DEPUIS_URL_TAILLE_MAX", None)
            os.environ.pop("RELAIS_EXTERNE_TAILLE_MAX", None)
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/cours.pdf", None)
        self.assertEqual(c.exception.statut, 413)

    def test_plafond_reglable_par_variable(self):
        annonce = {"Content-Length": str(150 * 1024 * 1024)}
        with patch.dict(os.environ, {"BIBLIOTHEQUE_DEPUIS_URL_TAILLE_MAX": str(200 * 1024 * 1024)}), _site(entetes=annonce):
            with self.assertRaises(ErreurRelais) as c:
                biblio._recuperer_fichier_externe("https://exemple.org/cours.pdf", None)
        # Le plafond est passe ; le fichier livre est plus petit que l'annonce : incomplet, pas trop gros.
        self.assertEqual(c.exception.statut, 502)

    def test_types_acceptes_inchanges(self):
        self.assertEqual(
            biblio._TYPES_IMPORT_DEPUIS_URL,
            frozenset({"pdf", "docx", "xlsx", "pptx", "ole", "png", "jpg", "gif", "webp", "texte"}),
        )


class RouteDepuisUrl(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from core.limitation_debit import limiteur

        app = FastAPI()
        app.state.limiter = limiteur
        app.include_router(biblio.router)
        app.dependency_overrides[biblio.utilisateur_courant] = lambda: SimpleNamespace(id="u1")
        self.client = TestClient(app)

    def test_ajout_reussi(self):
        enregistrer = MagicMock(return_value={"id": "f1", "statut_vectorisation": "pret"})
        with _site(), patch.object(biblio, "enregistrer_fichier", enregistrer), patch.object(biblio, "journaliser"):
            r = self.client.post("/api/bibliotheque/depuis-url", json={"url": "https://exemple.org/cours.pdf", "titre": "Cours"})
        self.assertEqual(r.status_code, 201)
        champs = enregistrer.call_args.kwargs
        self.assertEqual(champs["nom_fichier"], "Cours.pdf")
        self.assertEqual(champs["type_mime"], "application/pdf")
        self.assertEqual(champs["niveau"], "utilisateur")
        self.assertEqual(champs["user_id"], "u1")
        self.assertEqual(champs["contenu"], PDF)

    def test_adresse_vide_refusee(self):
        r = self.client.post("/api/bibliotheque/depuis-url", json={"url": "  "})
        self.assertEqual(r.status_code, 400)

    def test_page_html_refusee(self):
        with _site(contenu=HTML):
            r = self.client.post("/api/bibliotheque/depuis-url", json={"url": "https://exemple.org/faux.pdf"})
        self.assertEqual(r.status_code, 415)

    def test_nom_deja_pris(self):
        from postgrest.exceptions import APIError

        erreur = APIError({"message": "doublon", "code": "23505", "details": "", "hint": ""})
        with _site(), patch.object(biblio, "enregistrer_fichier", MagicMock(side_effect=erreur)):
            r = self.client.post("/api/bibliotheque/depuis-url", json={"url": "https://exemple.org/cours.pdf"})
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
