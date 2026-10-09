"""Lecture du texte d'un document Internet Archive : aucun accès réseau, tout est simulé."""

import unittest
from unittest.mock import MagicMock, patch

from core import lecture_document_archive as lda

TEXTE = ("Premier chapitre. " * 10 + "\n") * 5 + "Le mot rare : photosynthèse apparaît ici.\n" + ("Fin du livre. " * 5)


def _reponse_json(donnees):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = donnees
    return r


def _reponse_fichier(contenu, statut=200):
    r = MagicMock()
    r.status_code = statut
    r.raise_for_status.return_value = None
    r.iter_content.return_value = [contenu[i:i + 50] for i in range(0, len(contenu), 50)]
    r.__enter__ = lambda self: self
    r.__exit__ = lambda self, *a: False
    return r


def _metadonnees(fichiers, **meta):
    return {"metadata": {"title": "Un livre", **meta}, "files": fichiers}


class Identifiant(unittest.TestCase):
    def test_formes_reconnues(self):
        self.assertEqual(lda.extraire_identifiant("https://archive.org/details/livre_2020"), "livre_2020")
        self.assertEqual(lda.extraire_identifiant("https://archive.org/download/livre_2020/livre_2020.pdf"), "livre_2020")
        self.assertEqual(lda.extraire_identifiant("livre_2020"), "livre_2020")

    def test_refus(self):
        self.assertIsNone(lda.extraire_identifiant("https://exemple.com/x"))
        self.assertIsNone(lda.extraire_identifiant("../../etc/passwd"))
        self.assertIsNone(lda.extraire_identifiant(""))


class Lecture(unittest.TestCase):
    def setUp(self):
        lda._memoire.clear()

    def _simuler(self, metadonnees, contenu=b"", statut=200):
        def faux_get(url, **kw):
            if "/metadata/" in url:
                return _reponse_json(metadonnees)
            return _reponse_fichier(contenu, statut)
        return patch.object(lda.requests, "get", side_effect=faux_get)

    def test_texte_par_tranches(self):
        meta = _metadonnees([{"name": "livre_djvu.txt", "format": "DjVuTXT", "size": "100"}])
        with self._simuler(meta, TEXTE.encode()), patch.dict("os.environ", {"LECTURE_ARCHIVE_LONGUEUR_MAX": "1000"}):
            premiere = lda.lire_document_archive("livre", 0)
            self.assertIn("a_partir_du_caractere=", premiere)
            self.assertIn("archive.org/details/livre", premiere)
            self.assertIn("Premier chapitre", premiere)
            suite = lda.lire_document_archive("livre", 100000)
            self.assertIn("après la fin", suite)

    def test_recherche_de_passage(self):
        meta = _metadonnees([{"name": "livre_djvu.txt", "format": "DjVuTXT"}])
        with self._simuler(meta, TEXTE.encode()):
            reponse = lda.lire_document_archive("livre", 0, "PHOTOSYNTHÈSE")
            self.assertIn("[position", reponse)
            self.assertIn("photosynthèse", reponse)
            vide = lda.lire_document_archive("livre", 0, "inexistant")
            self.assertIn("Aucun passage", vide)

    def test_pret_numerique(self):
        meta = _metadonnees([{"name": "livre_djvu.txt", "format": "DjVuTXT"}], **{"access-restricted-item": "true"})
        with self._simuler(meta):
            reponse = lda.lire_document_archive("livre")
            self.assertIn("prêt numérique", reponse)
            self.assertIn("archive.org/details/livre", reponse)

    def test_acces_refuse_au_telechargement(self):
        meta = _metadonnees([{"name": "livre_djvu.txt", "format": "DjVuTXT"}])
        with self._simuler(meta, b"", statut=403):
            self.assertIn("prêt numérique", lda.lire_document_archive("livre"))

    def test_document_inconnu(self):
        with self._simuler({}):
            self.assertIn("Aucun document trouvé", lda.lire_document_archive("inconnu"))

    def test_fichier_texte_trop_gros(self):
        meta = _metadonnees([{"name": "livre_djvu.txt", "format": "DjVuTXT"}])
        with self._simuler(meta, b"x" * 500), patch.dict("os.environ", {"LECTURE_ARCHIVE_TEXTE_TAILLE_MAX": "100"}):
            self.assertIn("trop gros", lda.lire_document_archive("livre"))

    def test_pdf_trop_gros_sans_texte(self):
        meta = _metadonnees([{"name": "livre.pdf", "format": "Text PDF", "size": str(10**9)}])
        with self._simuler(meta):
            self.assertIn("trop gros", lda.lire_document_archive("livre"))

    def test_aucun_fichier_lisible(self):
        meta = _metadonnees([{"name": "film.mp4", "format": "MPEG4"}])
        with self._simuler(meta):
            self.assertIn("aucun texte lisible", lda.lire_document_archive("film"))

    def test_erreur_reseau_ne_leve_pas(self):
        with patch.object(lda.requests, "get", side_effect=RuntimeError("panne")):
            self.assertIn("a échoué", lda.lire_document_archive("livre"))

    def test_lien_non_reconnu(self):
        self.assertIn("Lien non reconnu", lda.lire_document_archive("https://exemple.com"))

    def test_aucun_double_tiret_affiche(self):
        for texte in (lda._explication_illisible("x", r) for r in ("acces_reserve", "pdf_trop_gros", "trop_gros", "aucun_texte")):
            self.assertNotIn("--", texte)


if __name__ == "__main__":
    unittest.main()
