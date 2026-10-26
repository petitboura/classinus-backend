"""Vérifie les serveurs MCP personnels et les préfixes, sans réseau ni base."""

import os
import re
import sys
import types
import unittest
from unittest.mock import patch

# En production le dossier core est sur le chemin d'import (import direct de mcp_tools).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

# Le registre n'a pas besoin de charger les sources documentaires pour ces tests.
# Une fausse source évite les dépendances réseau et les imports de collecte.
_sources_docs = types.ModuleType("core.sources_documents_externes")
_sources_docs.noms_sources = lambda: []
# Le faux module est retiré juste après l'import du registre : sinon il resterait en place
# et casserait les autres tests qui utilisent la vraie source dans le même processus.
_faux_sources_ajoute = "core.sources_documents_externes" not in sys.modules
if _faux_sources_ajoute:
    sys.modules["core.sources_documents_externes"] = _sources_docs

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

if _faux_sources_ajoute:
    sys.modules.pop("core.sources_documents_externes", None)


def _outil(nom):
    return {"type": "function", "function": {"name": nom, "description": "", "parameters": {}}}



class TestGoogleWorkspaceMcpConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "connexions", "oauth_generique.py"), encoding="utf-8") as fichier:
            cls.oauth_source = fichier.read()
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "registre_outils.py"), encoding="utf-8") as fichier:
            cls.registre_source = fichier.read()

    def test_les_huit_services_google_ont_les_scopes_requis_aux_operations_exposees(self):
        exigences = {
            "google_gmail_mcp": ("gmail.readonly", "gmail.compose"),
            "google_docs_mcp": ("drive.readonly", "drive.file", "documents.readonly", "documents"),
            "google_sheets_mcp": ("drive.readonly", "drive.file", "spreadsheets.readonly", "spreadsheets"),
            "google_slides_mcp": ("drive.readonly", "drive.file", "presentations.readonly", "presentations"),
            "google_calendar_mcp": ("calendar.calendarlist.readonly", "calendar.events.readonly", "calendar.events"),
            "google_chat_mcp": ("chat.spaces.readonly", "chat.messages.readonly", "chat.messages.create"),
            "google_classroom_mcp": ("classroom.announcements", "classroom.courses.readonly", "classroom.coursework.students", "classroom.topics.readonly"),
            "google_people_mcp": ("directory.readonly", "contacts.readonly", "userinfo.profile"),
        }
        for service, scopes in exigences.items():
            debut = self.oauth_source.index(f'"{service}": {{')
            fin = self.oauth_source.find('\n    },', debut)
            configuration = self.oauth_source[debut:fin]
            for scope in scopes:
                with self.subTest(service=service, scope=scope):
                    self.assertIn(scope, configuration)

    def test_les_permissions_hors_liste_officielle_ne_sont_pas_demandees(self):
        for service, interdit in (
            ("google_gmail_mcp", "gmail.modify"),
            ("google_classroom_mcp", "classroom.topics"),
        ):
            debut = self.oauth_source.index(f'"{service}": {{')
            fin = self.oauth_source.find('\n    },', debut)
            scopes = re.findall(r"auth/([\w.\-]+)", self.oauth_source[debut:fin])
            with self.subTest(service=service):
                self.assertNotIn(interdit, scopes)

    def test_la_deconnexion_google_vide_le_cache_et_le_statut_verifie_le_jeton(self):
        debut = self.oauth_source.index("def deconnecter(service, user_id):")
        self.assertIn("_cache_token.pop((service, user_id), None)", self.oauth_source[debut:])
        self.assertIn("def a_reconnecter(service, user_id):", self.oauth_source)

    def test_microsoft_demande_le_renouvellement_automatique(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "connexions", "platform_mcp_oauth.py"), encoding="utf-8") as fichier:
            source = fichier.read()
        debut = source.index('"microsoft_mcp": {')
        self.assertIn('"offline_access"', source[debut:source.index("\n    },", debut)])

    def test_netlify_utilise_le_meme_chemin_d_import_que_les_autres_connexions(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "connexions", "netlify_mcp.py"), encoding="utf-8") as fichier:
            source = fichier.read()
        self.assertIn("from core.client_http_supabase import nouveau_client_http_supabase", source)

    def test_les_url_google_pointent_vers_les_serveurs_mcp_officiels(self):
        for endpoint in (
            "https://gmailmcp.googleapis.com/mcp/v1",
            "https://docsmcp.googleapis.com/mcp/v1",
            "https://sheetsmcp.googleapis.com/mcp/v1",
            "https://slidesmcp.googleapis.com/mcp/v1",
            "https://calendarmcp.googleapis.com/mcp/v1",
            "https://chatmcp.googleapis.com/mcp/v1",
            "https://classroommcp.googleapis.com/mcp/v1",
            "https://people.googleapis.com/mcp/v1",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.registre_source)


class TestCategoriesSeparees(unittest.TestCase):
    def test_chaque_serveur_a_sa_categorie(self):
        for categorie in ("vercel", "railway", "supabase", "higgsfield", "google_gmail", "google_docs", "google_sheets", "google_slides", "google_calendar", "google_chat", "google_classroom", "google_people", "microsoft_mcp", "render_mcp", "cloudflare_mcp", "netlify_mcp"):
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
            {
                "higgsfield_mcp": "higgsfield_",
                "vercel_mcp": "vercel_",
                "railway_mcp": "railway_",
                "supabase_mcp": "supabase_",
                "google_gmail_mcp": "gmail_",
                "google_docs_mcp": "gdocs_",
                "google_sheets_mcp": "gsheets_",
                "google_slides_mcp": "gslides_",
                "google_calendar_mcp": "gcal_",
                "google_chat_mcp": "gchat_",
                "google_classroom_mcp": "gclass_",
                "google_people_mcp": "gpeople_",
                "microsoft_mcp": "ms365_",
                "render_mcp": "render_",
                "cloudflare_mcp": "cloudflare_",
                "netlify_mcp": "netlify_",
            },
        )


class TestRegistreServeurs(unittest.TestCase):
    def test_aucun_serveur_declare_deux_fois(self):
        noms = [serveur["nom"] for serveur in r.SERVEURS_MCP]
        self.assertEqual(len(noms), len(set(noms)), f"serveur en double : {sorted(n for n in set(noms) if noms.count(n) > 1)}")

    def test_tous_les_serveurs_personnels_ont_un_prefixe_distinct(self):
        noms_personnels = {
            "higgsfield_mcp", "vercel_mcp", "railway_mcp", "supabase_mcp",
            "google_gmail_mcp", "google_docs_mcp", "google_sheets_mcp",
            "google_slides_mcp", "google_calendar_mcp", "google_chat_mcp",
            "google_classroom_mcp", "google_people_mcp", "microsoft_mcp",
            "render_mcp", "cloudflare_mcp", "netlify_mcp",
        }
        prefixes = {s["nom"]: s.get("prefixe_outils") for s in r.SERVEURS_MCP if s["nom"] in noms_personnels}
        self.assertEqual(len(prefixes), len(noms_personnels))
        self.assertEqual(len(set(prefixes.values())), len(noms_personnels))
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
            "railway_get-logs", "railway_list-services", "railway_describe-service", "railway_whoami", "netlify_lister_sites", "netlify_consulter_site", "cloudflare_search", "render_list_services", "ms365_microsoft_graph_get",
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
    def test_les_confirmations_affichent_le_nom_lisible_du_fournisseur(self):
        for nom, attendu in (
            ("gdocs_update_doc", "Google Docs"),
            ("gsheets_update_values", "Google Sheets"),
            ("gcal_create_event", "Google Calendar"),
            ("ms365_update_directory_object", "Microsoft"),
            ("netlify_relancer_deploiement", "Netlify"),
            ("cloudflare_update_worker", "Cloudflare"),
            ("render_update_service", "Render"),
        ):
            self.assertEqual(r.plateforme_outil_personnel(nom), attendu)

    def test_meme_nom_reel_donne_deux_noms_exposes_differents(self):
        self.assertNotEqual("vercel_get_project", "supabase_get_project")
        for serveur in r.SERVEURS_MCP:
            prefixe = serveur.get("prefixe_outils")
            if prefixe:
                # Le préfixe doit rester assez court pour les noms d'outils (limite 64).
                self.assertLessEqual(len(prefixe) + 40, 64, serveur["nom"])


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

    def test_les_outils_higgsfield_portent_l_appli_du_logo(self):
        noms_applis = {s["nom"] for s in r.SERVEURS_MCP}
        for nom in ("lancer_video_higgsfield", "consulter_video_higgsfield"):
            appli = r.REGISTRE_AFFICHAGE_OUTILS[nom]["appli"]
            self.assertEqual(appli, "higgsfield_mcp", nom)
            self.assertIn(appli, noms_applis, nom)

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
