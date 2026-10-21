"""Vérifie les serveurs MCP personnels (Vercel, Railway, Supabase, Higgsfield), sans réseau ni base."""

import os
import sys
import types
import unittest
from unittest.mock import patch

# En production le dossier core est sur le chemin d'import (import direct de mcp_tools).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

# registre_outils importe des modules qui ouvrent une connexion Supabase à
# l'import : on les remplace par des modules vides pour tester sans environnement.
_paquet = types.ModuleType("connexions")
_paquet.__path__ = []
sys.modules.setdefault("connexions", _paquet)
for _nom in ("notion", "higgsfield_mcp", "platform_mcp_oauth"):
    _module = types.ModuleType(f"connexions.{_nom}")
    _module.obtenir_token_valide = lambda *a, **k: None
    sys.modules.setdefault(f"connexions.{_nom}", _module)

# mcp_tools ouvre aussi une connexion Supabase à l'import : même remplacement.
if "supabase" not in sys.modules:
    _supabase = types.ModuleType("supabase")
    _supabase.create_client = lambda *a, **k: None
    _supabase.ClientOptions = lambda *a, **k: None
    sys.modules["supabase"] = _supabase

from core import registre_outils as r  # noqa: E402


def _outil(nom):
    return {"type": "function", "function": {"name": nom, "description": "", "parameters": {}}}


class TestCategoriesSeparees(unittest.TestCase):
    def test_chaque_serveur_a_sa_categorie(self):
        for categorie in ("vercel", "railway", "supabase", "higgsfield"):
            self.assertIn(categorie, r.NOMS_CATEGORIES_OUTILS)
            self.assertIn(categorie, r.INDEX_CATEGORIES_OUTILS)

    def test_une_categorie_ne_renvoie_que_ses_outils(self):
        candidats = [_outil(n) for n in (
            "vercel_get_project", "supabase_get_project", "railway_list-projects",
            "notion-search", "tavily_search",
        )]
        noms = lambda cat: [o["function"]["name"] for o in r.outils_de_la_categorie(cat, candidats)]
        self.assertEqual(noms("vercel"), ["vercel_get_project"])
        self.assertEqual(noms("supabase"), ["supabase_get_project"])
        self.assertEqual(noms("railway"), ["railway_list-projects"])
        self.assertEqual(noms("notion"), ["notion-search"])

    def test_chaque_serveur_prefixe_a_une_categorie_au_meme_prefixe(self):
        for serveur in r.SERVEURS_MCP:
            prefixe = serveur.get("prefixe_outils")
            if prefixe:
                self.assertIn(prefixe, r.CATEGORIES_OUTILS_PAR_PREFIXE.values(), serveur["nom"])


class TestCategorieHiggsfield(unittest.TestCase):
    def test_la_categorie_reunit_serveur_mcp_et_outils_api_sans_doublon_de_nom(self):
        self.assertEqual(r.NOMS_CATEGORIES_OUTILS.count("higgsfield"), 1)
        candidats = [_outil(n) for n in ("higgsfield_generate_image", "lancer_video_higgsfield", "consulter_video_higgsfield", "generer_image")]
        noms = [o["function"]["name"] for o in r.outils_de_la_categorie("higgsfield", candidats)]
        self.assertEqual(noms, ["higgsfield_generate_image", "lancer_video_higgsfield", "consulter_video_higgsfield"])


class TestPrefixesPourLeFrontend(unittest.TestCase):
    def test_le_registre_sert_le_prefixe_de_chaque_appli(self):
        try:
            from api import outils_registre
        except Exception as erreur:
            self.skipTest(f"api.outils_registre non importable ici : {erreur}")
        prefixes = outils_registre.lister_registre_affichage_outils()["prefixes_applis"]
        self.assertEqual(
            prefixes,
            {"higgsfield_mcp": "higgsfield_", "vercel_mcp": "vercel_", "railway_mcp": "railway_", "supabase_mcp": "supabase_"},
        )


class TestRegistreServeurs(unittest.TestCase):
    def test_aucun_serveur_declare_deux_fois(self):
        noms = [serveur["nom"] for serveur in r.SERVEURS_MCP]
        self.assertEqual(len(noms), len(set(noms)), f"serveur en double : {sorted(n for n in set(noms) if noms.count(n) > 1)}")

    def test_les_quatre_serveurs_personnels_ont_un_prefixe_distinct(self):
        prefixes = {s["nom"]: s.get("prefixe_outils") for s in r.SERVEURS_MCP if s["nom"] in ("higgsfield_mcp", "vercel_mcp", "railway_mcp", "supabase_mcp")}
        self.assertEqual(len(prefixes), 4)
        self.assertEqual(len(set(prefixes.values())), 4)
        self.assertNotIn(None, prefixes.values())


class TestConfirmation(unittest.TestCase):
    def test_actions_qui_modifient_sont_confirmees(self):
        for nom in (
            "supabase_execute_sql", "supabase_apply_migration", "supabase_pause_project",
            "vercel_create_project", "vercel_update_project", "vercel_cancel_deployment",
            "railway_delete-service", "railway_accept-deploy", "railway_set-variables",
            "railway_generate-domain", "railway_railway-agent", "higgsfield_generate_video",
        ):
            self.assertTrue(r.est_outil_sensible_serveur_personnel(nom), nom)

    def test_lectures_simples_passent_sans_confirmation(self):
        for nom in (
            "supabase_list_tables", "supabase_get_project", "supabase_query_logs",
            "vercel_list_projects", "vercel_get_deployment", "vercel_search_vercel_documentation",
            "railway_get-logs", "railway_list-services", "railway_describe-service", "railway_whoami",
        ):
            self.assertFalse(r.est_outil_sensible_serveur_personnel(nom), nom)

    def test_lectures_qui_exposent_un_secret_sont_confirmees(self):
        for nom in (
            "vercel_get_shared_env_var", "vercel_get_project_env", "vercel_get_access_to_vercel_url",
            "railway_list-variables", "railway_get-bucket-credentials",
        ):
            self.assertTrue(r.est_outil_sensible_serveur_personnel(nom), nom)

    def test_autres_outils_ne_sont_pas_touches(self):
        self.assertFalse(r.est_outil_sensible_serveur_personnel("notion-search"))
        self.assertFalse(r.est_outil_sensible_serveur_personnel("tavily_search"))


class TestNomsSansCollision(unittest.TestCase):
    def test_meme_nom_reel_donne_deux_noms_exposes_differents(self):
        self.assertNotEqual("vercel_get_project", "supabase_get_project")
        for serveur in r.SERVEURS_MCP:
            prefixe = serveur.get("prefixe_outils")
            if prefixe:
                # 64 caracteres : limite des noms de fonction chez les fournisseurs d'IA.
                # Le plus long nom reel connu (Vercel) fait 51 caracteres.
                self.assertLessEqual(len(prefixe) + 51, 64, serveur["nom"])


class TestAppelAvecVraiNom(unittest.TestCase):
    def test_appeler_outil_envoie_le_nom_reel_au_serveur(self):
        try:
            from core import mcp_tools
        except Exception as erreur:  # bibliothèque MCP absente de cet environnement
            self.skipTest(f"mcp_tools non importable ici : {erreur}")
        table = {"vercel_get_project": {"url": "https://mcp.vercel.com", "headers": {}, "nom_reel": "get_project"}}
        appels = []

        async def faux(url, nom, arguments, headers=None):
            appels.append(nom)
            return "ok"

        with patch.object(mcp_tools, "_appeler_outil_async", faux):
            mcp_tools.appeler_outil("vercel_get_project", {}, table)
        self.assertEqual(appels, ["get_project"])


class TestLibelleOutilPlateforme(unittest.TestCase):
    def test_le_nom_devient_un_texte_sans_nom_de_plateforme(self):
        self.assertEqual(r.libelle_outil_plateforme("vercel_list_projects"), "List projects")
        self.assertEqual(r.libelle_outil_plateforme("railway_list-services"), "List services")
        self.assertEqual(r.libelle_outil_plateforme("supabase_execute_sql"), "Execute sql")
        self.assertEqual(r.libelle_outil_plateforme("higgsfield_generate_image"), "Generate image")

    def test_hors_plateformes_ou_nom_vide_renvoie_none(self):
        for nom in ("notion-search", "tavily_search", "lire_page", "vercel_", "railway__", None, 42):
            self.assertIsNone(r.libelle_outil_plateforme(nom), repr(nom))

    def test_aucun_libelle_compose_ne_contient_un_tiret_double(self):
        double = "-" * 2
        for nom in ("vercel_get-project", "railway_get" + double + "logs"):
            self.assertNotIn(double, r.libelle_outil_plateforme(nom))


class TestLibellesManuelsAjoutes(unittest.TestCase):
    OUTILS = (
        "lancer_video_higgsfield", "consulter_video_higgsfield", "gerer_programme_catalogue_public",
        "ajouter_commentaire_catalogue_public", "supprimer_commentaire_catalogue_public",
    )

    def test_chaque_outil_a_un_libelle_et_une_icone(self):
        for nom in self.OUTILS:
            entree = r.REGISTRE_AFFICHAGE_OUTILS[nom]
            self.assertTrue(entree["label"], nom)
            self.assertTrue(entree["icone"], nom)

    def test_aucun_libelle_ne_nomme_la_plateforme_ni_ne_contient_de_tiret_double(self):
        for nom in self.OUTILS:
            label = r.REGISTRE_AFFICHAGE_OUTILS[nom]["label"]
            self.assertNotIn("higgsfield", label.lower(), nom)
            self.assertNotIn("-" * 2, label, nom)

    def test_les_deux_outils_video_ont_des_libelles_distincts(self):
        self.assertNotEqual(
            r.REGISTRE_AFFICHAGE_OUTILS["lancer_video_higgsfield"]["label"],
            r.REGISTRE_AFFICHAGE_OUTILS["consulter_video_higgsfield"]["label"],
        )

    def test_chaque_libelle_a_sa_traduction_anglaise(self):
        from core.libelles_outils_anglais import LIBELLES_OUTILS_EN
        for nom in self.OUTILS:
            self.assertIn(r.REGISTRE_AFFICHAGE_OUTILS[nom]["label"], LIBELLES_OUTILS_EN, nom)


if __name__ == "__main__":
    unittest.main()
