"""Tests hors ligne du dossier bambara-traduction : aucun modèle téléchargé, PyTorch inutile.

Lancer depuis ce dossier : python3 -m unittest test_app
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.pop("PRECHARGER_MOTEURS", None)
os.environ.pop("TEST_ACCESS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

import app as application  # noqa: E402
import moteurs  # noqa: E402


class _Sortie(list):
    pass


class _FauxTokenizer:
    def __init__(self):
        self.src_lang = None
        self.entrees = []

    def __call__(self, texte, **kw):
        self.entrees.append(texte)
        return {"input_ids": [1, 2, 3]}

    def convert_tokens_to_ids(self, code):
        return {"fra_Latn": 11, "eng_Latn": 22, "bam_Latn": 33}[code]

    def decode(self, sortie, skip_special_tokens=True):
        return "résultat"


class _FauxModele:
    def __init__(self):
        self.appels = []

    def generate(self, **kw):
        self.appels.append(kw)
        return _Sortie([[0]])


class TestMoteurs(unittest.TestCase):
    def setUp(self):
        moteurs._charges.clear()
        moteurs._echecs.clear()
        self.tok, self.mod = _FauxTokenizer(), _FauxModele()
        patch = mock.patch.object(moteurs, "charger", lambda i: (self.tok, self.mod))
        patch.start()
        self.addCleanup(patch.stop)

    def test_balise_madlad_vers_bambara(self):
        r = moteurs.traduire("madlad", "fra", "bam", "Bonjour")
        self.assertEqual(self.tok.entrees[-1], "<2bm> Bonjour")
        self.assertEqual(r["sortie"], "résultat")
        self.assertEqual(r["sens"], "fra-bam")

    def test_balise_localenlp_bambara_vers_anglais(self):
        moteurs.traduire("localenlp_bam_eng", "bam", "eng", "I ni ce")
        self.assertEqual(self.tok.entrees[-1], ">>eng<< I ni ce")

    def test_nllb_force_la_langue_cible(self):
        moteurs.traduire("nllb_bambara", "bam", "fra", "I ni ce")
        self.assertEqual(self.tok.src_lang, "bam_Latn")
        self.assertEqual(self.mod.appels[-1]["forced_bos_token_id"], 11)
        self.assertEqual(self.tok.entrees[-1], "I ni ce")

    def test_refus_sens_non_gere(self):
        with self.assertRaises(moteurs.ErreurTraduction) as c:
            moteurs.traduire("localenlp_eng_bam", "bam", "eng", "x")
        self.assertEqual(c.exception.code, "sens_non_gere")

    def test_refus_moteur_inconnu_vide_et_trop_long(self):
        for args, code in [(("zzz", "fra", "bam", "a"), "moteur_inconnu"), (("madlad", "fra", "bam", "  "), "texte_vide"),
                           (("madlad", "fra", "bam", "a" * (moteurs.texte_max() + 1)), "texte_trop_long")]:
            with self.assertRaises(moteurs.ErreurTraduction) as c:
                moteurs.traduire(*args)
            self.assertEqual(c.exception.code, code)

    def test_echec_modele_devient_erreur_claire(self):
        self.mod.generate = mock.Mock(side_effect=RuntimeError("mémoire"))
        with self.assertRaises(moteurs.ErreurTraduction) as c:
            moteurs.traduire("madlad", "fra", "bam", "Bonjour")
        self.assertEqual((c.exception.code, c.exception.statut), ("echec_modele", 500))


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(application.app)

    def test_page_etat_et_liste(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn("moteurs", self.client.get("/etat").json())
        self.assertEqual(set(self.client.get("/moteurs").json()["moteurs"]), set(moteurs.MOTEURS))

    def test_jeton_exige_quand_defini(self):
        with mock.patch.dict(os.environ, {"TEST_ACCESS_TOKEN": "abc"}):
            corps = {"moteur": "madlad", "source": "fra", "cible": "bam", "texte": "Bonjour"}
            self.assertEqual(self.client.get("/moteurs").status_code, 401)
            self.assertEqual(self.client.post("/traduire", json=corps).status_code, 401)
            self.assertEqual(self.client.get("/moteurs", headers={"X-Test-Token": "abc"}).status_code, 200)

    def test_erreur_metier_renvoie_le_code(self):
        r = self.client.post("/traduire", json={"moteur": "madlad", "source": "bam", "cible": "bam", "texte": "x"})
        self.assertEqual((r.status_code, r.json()["erreur"]), (400, "sens_non_gere"))


class TestMemoire(unittest.TestCase):
    def test_un_seul_moteur_garde_par_defaut(self):
        moteurs._charges.clear()
        moteurs._charges["madlad"] = ("t", "m")
        self.assertEqual(moteurs.moteurs_gardes(), 1)


if __name__ == "__main__":
    unittest.main()
