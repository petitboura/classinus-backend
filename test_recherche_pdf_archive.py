"""Recherche Internet Archive : lien du PDF dans le visionneur, ou mention quand il n'y en a pas."""

import unittest
from unittest.mock import patch

from core import recherche_internet_archive as rech

BASE = "https://api.classinus.com"


def _brut(**champs):
    return {"identifier": "livre_2020", "title": "Un livre", "format": ["Text PDF", "DjVuTXT"], **champs}


class LienPdf(unittest.TestCase):
    def _doc(self, brut):
        with patch.dict("sys.modules", {"core.stockage_r2": type("M", (), {"R2_PUBLIC_BASE_URL": BASE})}):
            return rech._construire_document(brut)

    def test_libre_avec_pdf(self):
        doc = self._doc(_brut())
        self.assertEqual(doc["url_pdf"], f"{BASE}/fichiers/archive/livre_2020.pdf")
        self.assertNotIn("note_pdf", doc)
        self.assertEqual(doc["url"], "https://archive.org/details/livre_2020")

    def test_libre_sans_pdf(self):
        doc = self._doc(_brut(format=["MPEG4", "Metadata"]))
        self.assertNotIn("url_pdf", doc)
        self.assertIn("pas de PDF", doc["note_pdf"])

    def test_format_absent(self):
        brut = _brut()
        del brut["format"]
        self.assertIn("pas de PDF", self._doc(brut)["note_pdf"])

    def test_pret_numerique(self):
        doc = self._doc(_brut(**{"lending___status": "is_lendable"}))
        self.assertNotIn("url_pdf", doc)
        self.assertIn("prêt numérique", doc["note_pdf"])

    def test_restreint(self):
        doc = self._doc(_brut(**{"access-restricted-item": "true"}))
        self.assertNotIn("url_pdf", doc)
        self.assertIn("non consultable", doc["note_pdf"])

    def test_adresse_backend_inconnue(self):
        with patch.dict("sys.modules", {"core.stockage_r2": type("M", (), {"R2_PUBLIC_BASE_URL": None})}):
            doc = rech._construire_document(_brut())
        self.assertNotIn("url_pdf", doc)
        self.assertIn("indisponible", doc["note_pdf"])


if __name__ == "__main__":
    unittest.main()
