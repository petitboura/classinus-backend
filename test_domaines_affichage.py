"""Vérifie les sites visés par un appel d'outil (logo du site dans le chat), sans réseau ni base."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.domaines_affichage import domaine_de_adresse, domaine_site_serveur, domaines_de_l_appel, langage_de_l_appel  # noqa: E402


def _sources():
    try:
        from core import sources_documents_externes as sources
    except Exception as erreur:  # bibliothèque absente de cet environnement
        raise unittest.SkipTest(f"sources_documents_externes non importable ici : {erreur}")
    return sources


class TestDomaineDeAdresse(unittest.TestCase):
    def test_retire_www_et_met_en_minuscules(self):
        self.assertEqual(domaine_de_adresse("https://www.Wikipedia.org/wiki/Pi"), "wikipedia.org")

    def test_garde_les_sous_domaines_utiles(self):
        self.assertEqual(domaine_de_adresse("https://fr.wikipedia.org/wiki/Pi"), "fr.wikipedia.org")

    def test_accepte_une_adresse_sans_protocole(self):
        self.assertEqual(domaine_de_adresse("arxiv.org/abs/1234.5678"), "arxiv.org")

    def test_valeurs_inutilisables(self):
        for valeur in (None, "", "   ", 42, "pas une adresse", "http://localhost/x"):
            self.assertIsNone(domaine_de_adresse(valeur), repr(valeur))


class TestDomaineSiteServeur(unittest.TestCase):
    def test_retire_les_sous_domaines_du_serveur(self):
        self.assertEqual(domaine_site_serveur("https://mcp.linear.app/mcp"), "linear.app")
        self.assertEqual(domaine_site_serveur("https://www.huggingface.co/mcp"), "huggingface.co")

    def test_domaine_public_a_deux_niveaux(self):
        self.assertEqual(domaine_site_serveur("https://mcp.exemple.co.uk/sse"), "exemple.co.uk")

    def test_plateforme_d_hebergement_garde_le_sous_domaine(self):
        self.assertEqual(domaine_site_serveur("https://mon-serveur.onrender.com/mcp"), "mon-serveur.onrender.com")

    def test_rien_d_exploitable(self):
        for valeur in (None, "", "https://192.168.1.5/mcp", "https://[::1]/mcp", "pas une adresse"):
            self.assertIsNone(domaine_site_serveur(valeur), repr(valeur))


class TestDomainesParOutil(unittest.TestCase):
    def test_outil_d_un_serveur_mcp_personnalise(self):
        try:
            from connexions import mcp_personnalises as mcp
        except Exception as erreur:  # dépendances absentes de cet environnement
            raise unittest.SkipTest(f"mcp_personnalises non importable ici : {erreur}")
        mcp._URLS_SERVEURS_PAR_OUTIL["custommcp_test_logo"] = "https://mcp.linear.app/mcp"
        try:
            self.assertEqual(domaines_de_l_appel("custommcp_test_logo", {}), ["linear.app"])
            self.assertEqual(domaines_de_l_appel("custommcp_inconnu", {}), [])
        finally:
            mcp._URLS_SERVEURS_PAR_OUTIL.pop("custommcp_test_logo", None)

    def test_youtube(self):
        self.assertEqual(domaines_de_l_appel("rechercher_video", {"requete": "pi"}), ["youtube.com"])
        self.assertEqual(domaines_de_l_appel("lire_video", {}), ["youtube.com"])

    def test_internet_archive(self):
        self.assertEqual(domaines_de_l_appel("lire_document_internet_archive", {}), ["archive.org"])

    def test_lecture_fichier_externe_prend_le_site_du_lien(self):
        self.assertEqual(
            domaines_de_l_appel("lire_document_externe", {"url": "https://hal.science/hal-1/document"}),
            ["hal.science"],
        )
        self.assertEqual(domaines_de_l_appel("lire_document_externe", {"url": ""}), [])

    def test_tavily_agit_sur_le_site_vise(self):
        self.assertEqual(
            domaines_de_l_appel("tavily_extract", {"urls": ["https://fr.wikipedia.org/wiki/Pi", "https://example.com/a"]}),
            ["fr.wikipedia.org", "example.com"],
        )
        self.assertEqual(domaines_de_l_appel("tavily_extract", {"urls": "https://example.com/a"}), ["example.com"])
        self.assertEqual(domaines_de_l_appel("tavily_crawl", {"url": "https://docs.python.org"}), ["docs.python.org"])
        self.assertEqual(domaines_de_l_appel("tavily_map", {"url": "https://example.com"}), ["example.com"])

    def test_tavily_sans_site_precis_ne_montre_rien(self):
        for nom in ("tavily_search", "tavily_research"):
            self.assertEqual(domaines_de_l_appel(nom, {"query": "pi", "url": "https://example.com"}), [], nom)

    def test_jamais_le_logo_de_tavily_lui_meme(self):
        for nom in ("tavily_search", "tavily_extract", "tavily_crawl", "tavily_map", "tavily_research"):
            self.assertNotIn("tavily.com", domaines_de_l_appel(nom, {}), nom)

    def test_arguments_invalides_ou_outil_inconnu(self):
        self.assertEqual(domaines_de_l_appel("tavily_extract", None), [])
        self.assertEqual(domaines_de_l_appel("tavily_extract", {"urls": [None, 3, {}]}), [])
        self.assertEqual(domaines_de_l_appel("outil_inconnu", {"url": "https://example.com"}), [])
        self.assertEqual(domaines_de_l_appel("lire_page", {}), [])


class TestDomainesRechercheDocument(unittest.TestCase):
    def test_chaque_source_active_a_un_domaine(self):
        sources = _sources()
        for cle, infos in sources.SOURCES.items():
            self.assertTrue(infos.get("domaine"), cle)

    def test_source_nommee_donne_son_seul_domaine(self):
        sources = _sources()
        attendu = sources.SOURCES["gallica"]["domaine"] if "gallica" in sources.SOURCES else None
        if attendu is None:
            self.skipTest("Gallica désactivée")
        self.assertEqual(domaines_de_l_appel("rechercher_document_externe", {"source": "Gallica"}), [attendu])
        self.assertEqual(domaines_de_l_appel("rechercher_document_externe", {"source": "bnf"}), [attendu])

    def test_sans_source_toutes_les_sources_interrogees(self):
        sources = _sources()
        if not sources.recherche_melangee_active():
            self.skipTest("recherche mélangée désactivée")
        attendu = [infos["domaine"] for infos in sources.SOURCES.values()]
        self.assertEqual(domaines_de_l_appel("rechercher_document_externe", {}), attendu)
        self.assertEqual(domaines_de_l_appel("rechercher_document_externe", {"source": "  "}), attendu)

    def test_source_inconnue_ne_montre_rien(self):
        _sources()
        self.assertEqual(domaines_de_l_appel("rechercher_document_externe", {"source": "bibliotheque imaginaire"}), [])


class TestLangageDeLAppel(unittest.TestCase):
    """Langage lancé par l'outil Exécution de code (badge sur l'icône Play, 24/10/2026)."""

    def test_run_code_donne_son_langage(self):
        for langage in ("python", "javascript", "typescript", "bash"):
            self.assertEqual(
                langage_de_l_appel("gerer_execution_code", {"action": "run_code", "language": langage}),
                langage,
            )

    def test_langage_absent_donne_le_defaut_de_l_outil(self):
        self.assertEqual(langage_de_l_appel("gerer_execution_code", {"action": "run_code"}), "python")

    def test_langage_inconnu_ne_donne_rien(self):
        self.assertIsNone(langage_de_l_appel("gerer_execution_code", {"action": "run_code", "language": "cobol"}))

    def test_autres_actions_et_autres_outils_ne_donnent_rien(self):
        self.assertIsNone(langage_de_l_appel("gerer_execution_code", {"action": "run_command", "language": "bash"}))
        self.assertIsNone(langage_de_l_appel("gerer_execution_code", {"action": "write_file"}))
        self.assertIsNone(langage_de_l_appel("generer_code", {"action": "run_code", "language": "python"}))

    def test_arguments_invalides_ne_font_jamais_echouer(self):
        self.assertIsNone(langage_de_l_appel("gerer_execution_code", None))
        self.assertIsNone(langage_de_l_appel("gerer_execution_code", "pas un dictionnaire"))


if __name__ == "__main__":
    unittest.main()
