"""Tests hors ligne de la page bambara : outils proposes, consignes a l'IA et effort de reflexion."""
import os
import sys
import unittest

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)

from core import prompt_voix_bambara
from core.outils_page_bambara import (
    OUTILS_GENERATION_VISUELLE,
    effort_reflexion_page,
    filtrer_catalogue_par_client,
    noms_outils_autorises,
)
from registre_outils import CATEGORIES_OUTILS


def _catalogue(noms):
    outils = [{"type": "function", "function": {"name": n}} for n in noms]
    return outils, {n: {"url": "http://x"} for n in noms}


class TestOutilsPageBambara(unittest.TestCase):
    def test_garde_recherche_memoire_et_generation_visuelle(self):
        autorises = noms_outils_autorises()
        for nom in CATEGORIES_OUTILS["recherche_web"] + CATEGORIES_OUTILS["memoire"]:
            self.assertIn(nom, autorises)
        for nom in OUTILS_GENERATION_VISUELLE:
            self.assertIn(nom, autorises)

    def test_filtre_retire_les_autres_outils_pour_la_page(self):
        noms = ["tavily_search", "rechercher_video", "memoire_lire", "generer_image", "generer_code", "gerer_navigateur", "cliquer_ecran"]
        outils, table = filtrer_catalogue_par_client(*_catalogue(noms), "page_bambara")
        self.assertEqual(
            sorted(o["function"]["name"] for o in outils),
            ["generer_image", "memoire_lire", "rechercher_video", "tavily_search"],
        )
        self.assertEqual(sorted(table), ["generer_image", "memoire_lire", "rechercher_video", "tavily_search"])

    def test_autres_clients_gardent_tout(self):
        noms = ["tavily_search", "generer_code", "gerer_navigateur"]
        for client in (None, "", "thonny", "voix_bambara", "inconnu"):
            outils, table = filtrer_catalogue_par_client(*_catalogue(noms), client)
            self.assertEqual(len(outils), 3, client)
            self.assertEqual(len(table), 3, client)

    def test_client_reconnu_sans_tenir_compte_de_la_casse(self):
        outils, _ = filtrer_catalogue_par_client(*_catalogue(["generer_code"]), " Page_Bambara ")
        self.assertEqual(outils, [])


class TestConsignesPageBambara(unittest.TestCase):
    def test_client_page_reconnu_et_distinct_du_mode_vocal(self):
        self.assertTrue(prompt_voix_bambara.est_client_page_bambara("page_bambara"))
        self.assertFalse(prompt_voix_bambara.est_client_page_bambara("voix_bambara"))
        self.assertFalse(prompt_voix_bambara.est_client_voix_bambara("page_bambara"))
        self.assertFalse(prompt_voix_bambara.est_client_page_bambara(None))

    def test_consignes_page_disent_bambara_videos_images_et_outils(self):
        texte = prompt_voix_bambara.consignes_page()
        self.assertIn("bambara", texte)
        self.assertIn("vidéo", texte)
        self.assertIn("![description](lien)", texte)
        self.assertIn("outils", texte)
        self.assertNotIn("--", texte)

    def test_consignes_page_disent_comment_ecrire_un_lien(self):
        texte = prompt_voix_bambara.consignes_page()
        self.assertIn("note D", texte)
        self.assertIn("jamais de titre entre guillemets", texte)
        self.assertIn("extension", texte)
        self.assertIn("ne les imite pas", texte)
        self.assertNotIn("\u2014", texte)


class TestEffortPageBambara(unittest.TestCase):
    def test_effort_au_plus_faible_sans_modele_impose(self):
        self.assertEqual(effort_reflexion_page("page_bambara", None, "high"), "none")
        self.assertEqual(effort_reflexion_page("page_bambara", None, None), "none")

    def test_modele_impose_ou_autre_client_gardent_l_effort_demande(self):
        self.assertEqual(effort_reflexion_page("page_bambara", "claude-sonnet-5-5", "low"), "low")
        self.assertEqual(effort_reflexion_page("voix_bambara", None, "high"), "high")
        self.assertIsNone(effort_reflexion_page(None, None, None))


if __name__ == "__main__":
    unittest.main()
