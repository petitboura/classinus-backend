"""Smoke tests sans réseau pour le module des MCP personnalisés."""

import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))

# Les appels Supabase ne doivent jamais partir pendant ces tests : on injecte
# un faux client avant d'importer le module backend.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "test-only-secret")

class FauxClient:
    def table(self, *_args, **_kwargs):
        raise AssertionError("Ce test ne doit pas appeler Supabase")

supabase = types.ModuleType("supabase")
supabase.create_client = lambda *_args, **_kwargs: FauxClient()
supabase.ClientOptions = lambda **_kwargs: object()
sys.modules["supabase"] = supabase

from connexions import mcp_personnalises as mcp  # noqa: E402


class TestValidationUrl(unittest.TestCase):
    def test_refuse_http(self):
        with self.assertRaises(ValueError):
            mcp.valider_url_mcp("http://example.com/mcp")

    def test_refuse_localhost(self):
        with self.assertRaises(ValueError):
            mcp.valider_url_mcp("https://localhost/mcp")

    def test_refuse_ip_locale(self):
        with self.assertRaises(ValueError):
            mcp.valider_url_mcp("https://127.0.0.1/mcp")

    def test_refuse_jeton_dans_query(self):
        with self.assertRaises(ValueError):
            mcp.valider_url_mcp("https://example.com/mcp?token=ne-pas-conserver")

    def test_refuse_identifiants_dans_url(self):
        with self.assertRaises(ValueError):
            mcp.valider_url_mcp("https://user:pass@example.com/mcp")

    def test_refuse_dns_qui_pointe_vers_ip_privee(self):
        from unittest.mock import patch

        resultat_dns = [(None, None, None, None, ("10.0.0.8", 443))]
        from connexions import mcp_reseau_securise as reseau
        with patch.object(reseau.socket, "getaddrinfo", return_value=resultat_dns):
            with self.assertRaises(ValueError):
                mcp.valider_url_mcp("https://serveur-test.example/mcp")


class TestSerialisationSansSecret(unittest.TestCase):
    def test_n_expose_jamais_le_jeton_bearer(self):
        result = mcp._config_publique({
            "id": "serveur-test",
            "nom": "Serveur de test",
            "url": "https://mcp.example.com/mcp",
            "auth_type": "bearer",
            "bearer_token": "secret-ultra-confidentiel",
            "actif": True,
            "created_at": None,
            "updated_at": None,
        }, "utilisateur-test")
        self.assertNotIn("bearer_token", result)
        self.assertNotIn("secret-ultra-confidentiel", repr(result))
        self.assertEqual(result["nom"], "Serveur de test")

    def test_noms_outils_personnalises_sont_brefs_et_isoles(self):
        serveur = "12345678-abcd-4321-abcd-123456789abc"
        nom = mcp._nom_outil_expose(serveur, "list_tables")
        self.assertTrue(nom.startswith("custommcp_"))
        self.assertLessEqual(len(nom), 64)
        self.assertNotEqual(nom, mcp._nom_outil_expose("87654321-abcd-4321-abcd-123456789abc", "list_tables"))


class FauxOutil:
    def __init__(self, nom):
        self.name = nom
        self.description = f"Outil {nom}"
        self.input_schema = {"type": "object", "properties": {}}


class FauxResultat:
    def __init__(self, outils, next_cursor=None):
        self.tools = outils
        self.next_cursor = next_cursor


class FauxSession:
    """Serveur MCP simulé : `pages` associe un curseur (None pour la première page) à sa réponse."""

    def __init__(self, pages):
        self.pages = pages
        self.curseurs_demandes = []

    async def initialize(self):
        pass

    async def list_tools(self, *, params=None):
        curseur = params.cursor if params else None
        self.curseurs_demandes.append(curseur)
        return self.pages[curseur]


class FauxContexte:
    def __init__(self, valeur):
        self.valeur = valeur

    async def __aenter__(self):
        return self.valeur

    async def __aexit__(self, *_exc):
        return False


def outils_de_test(nombre, prefixe="outil"):
    return [FauxOutil(f"{prefixe}_{i}") for i in range(nombre)]


class TestLectureDesOutilsParPages(unittest.TestCase):
    def lire(self, pages):
        from unittest.mock import patch
        import asyncio

        session = FauxSession(pages)
        with patch.object(mcp, "creer_client_http_mcp", lambda headers=None: FauxContexte(object())), \
                patch.object(mcp, "streamable_http_client", lambda url, http_client=None: FauxContexte((None, None))), \
                patch.object(mcp, "ClientSession", lambda _lecture, _ecriture: FauxContexte(session)):
            outils = asyncio.run(mcp._lister_outils_async("https://mcp.example.com/mcp", {}))
        return outils, session

    def test_une_seule_page_garde_le_meme_appel_qu_avant(self):
        outils, session = self.lire({None: FauxResultat(outils_de_test(3))})
        self.assertEqual(len(outils), 3)
        self.assertEqual(session.curseurs_demandes, [None])

    def test_suit_les_pages_jusqu_a_la_derniere(self):
        pages = {
            None: FauxResultat(outils_de_test(2, "a"), "c1"),
            "c1": FauxResultat(outils_de_test(2, "b"), "c2"),
            "c2": FauxResultat(outils_de_test(1, "c")),
        }
        outils, session = self.lire(pages)
        self.assertEqual([o.name for o in outils], ["a_0", "a_1", "b_0", "b_1", "c_0"])
        self.assertEqual(session.curseurs_demandes, [None, "c1", "c2"])

    def test_un_serveur_qui_repete_son_curseur_ne_fait_pas_boucler(self):
        pages = {
            None: FauxResultat(outils_de_test(1, "a"), "c1"),
            "c1": FauxResultat(outils_de_test(1, "b"), "c1"),
        }
        outils, session = self.lire(pages)
        self.assertEqual(len(outils), 2)
        self.assertEqual(session.curseurs_demandes, [None, "c1"])

    def test_arrete_de_lire_quand_le_plafond_est_atteint(self):
        from unittest.mock import patch

        pages = {
            None: FauxResultat(outils_de_test(3, "a"), "c1"),
            "c1": FauxResultat(outils_de_test(3, "b"), "c2"),
            "c2": FauxResultat(outils_de_test(3, "c")),
        }
        with patch.object(mcp, "TAILLE_MAX_OUTILS_PAR_SERVEUR", 4):
            outils, session = self.lire(pages)
        self.assertEqual(session.curseurs_demandes, [None, "c1"])
        self.assertEqual(len(outils), 6)

    def test_nombre_de_pages_limite(self):
        from unittest.mock import patch

        pages = {None: FauxResultat(outils_de_test(1), "p1")}
        for i in range(1, 10):
            pages[f"p{i}"] = FauxResultat(outils_de_test(1, f"x{i}"), f"p{i + 1}")
        with patch.object(mcp, "PAGES_MAX_DECOUVERTE", 3):
            outils, session = self.lire(pages)
        self.assertEqual(len(session.curseurs_demandes), 3)
        self.assertEqual(len(outils), 3)


class TestPlafondOutilsParServeur(unittest.TestCase):
    SERVEUR = {"id": "12345678-abcd-4321-abcd-123456789abc", "nom": "Serveur", "url": "https://mcp.example.com/mcp"}

    def test_plus_de_50_outils_sont_conserves_avec_des_noms_uniques(self):
        construits = mcp._construire_outils(self.SERVEUR, outils_de_test(120))
        self.assertEqual(len(construits), 120)
        self.assertEqual(len({o["nom"] for o in construits}), 120)
        self.assertTrue(all(len(o["nom"]) <= 64 for o in construits))

    def test_le_plafond_de_securite_reste_applique(self):
        from unittest.mock import patch

        with patch.object(mcp, "TAILLE_MAX_OUTILS_PAR_SERVEUR", 30):
            construits = mcp._construire_outils(self.SERVEUR, outils_de_test(120))
        self.assertEqual(len(construits), 30)

    def test_les_valeurs_par_defaut_sont_positives(self):
        self.assertGreater(mcp.TAILLE_MAX_OUTILS_PAR_SERVEUR, 50)
        self.assertGreaterEqual(mcp.PAGES_MAX_DECOUVERTE, 1)
        self.assertGreaterEqual(mcp.APERCU_MAX_OUTILS_TEST, 1)


class TestDecouverteReseauPartielle(unittest.TestCase):
    def test_garde_les_pages_deja_lues_si_une_page_suivante_echoue(self):
        from unittest.mock import patch

        async def partiel(_url, _headers, collecte=None):
            collecte.extend(outils_de_test(2))
            raise RuntimeError("page suivante en erreur")

        with patch.object(mcp, "valider_url_mcp", lambda url: url), patch.object(mcp, "_lister_outils_async", partiel):
            outils = mcp._lister_outils_reseau("https://mcp.example.com/mcp", {})
        self.assertEqual(len(outils), 2)

    def test_garde_les_pages_deja_lues_si_le_delai_tombe(self):
        from unittest.mock import patch
        import asyncio

        async def lent(_url, _headers, collecte=None):
            collecte.extend(outils_de_test(3))
            await asyncio.sleep(5)

        with patch.object(mcp, "valider_url_mcp", lambda url: url), patch.object(mcp, "_lister_outils_async", lent):
            outils = mcp._lister_outils_reseau("https://mcp.example.com/mcp", {}, delai=0.05)
        self.assertEqual(len(outils), 3)

    def test_sans_aucun_outil_lu_l_erreur_reste_claire(self):
        from unittest.mock import patch

        async def en_erreur(_url, _headers, collecte=None):
            raise RuntimeError("serveur injoignable")

        with patch.object(mcp, "valider_url_mcp", lambda url: url), patch.object(mcp, "_lister_outils_async", en_erreur):
            with self.assertRaises(ValueError) as contexte:
                mcp._lister_outils_reseau("https://mcp.example.com/mcp", {})
        self.assertIn("Impossible de joindre ce serveur MCP", str(contexte.exception))


class TestApercuDuTestDeServeur(unittest.TestCase):
    def lancer_le_test(self, nombre_outils_serveur):
        from unittest.mock import patch

        serveur = {"id": "s1", "nom": "Serveur", "url": "https://mcp.example.com/mcp", "auth_type": "none"}
        with patch.object(mcp, "_serveur_pour_utilisateur", return_value=serveur), \
                patch.object(mcp, "_lister_outils_reseau", return_value=outils_de_test(nombre_outils_serveur)):
            return mcp.tester_serveur("s1", utilisateur=types.SimpleNamespace(id="u1"))

    def test_apercu_limite_mais_nombre_complet_annonce(self):
        reponse = self.lancer_le_test(120)
        self.assertEqual(reponse["nombre_outils"], 120)
        self.assertEqual(len(reponse["outils"]), mcp.APERCU_MAX_OUTILS_TEST)

    def test_le_nombre_annonce_ne_depasse_pas_le_plafond_utilisable(self):
        reponse = self.lancer_le_test(mcp.TAILLE_MAX_OUTILS_PAR_SERVEUR + 40)
        self.assertEqual(reponse["nombre_outils"], mcp.TAILLE_MAX_OUTILS_PAR_SERVEUR)


if __name__ == "__main__":
    unittest.main()
