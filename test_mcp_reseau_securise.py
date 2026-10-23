"""Tests de la protection réseau des MCP personnalisés, avec la version de `mcp` de production.

Les serveurs de test tournent sur 127.0.0.1 : le contrôle d'adresse est donc remplacé par un
contrôle permissif pour ces tests, sauf là où on vérifie justement le refus.
"""
import asyncio
import os
import sys
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "test-only-secret")


class FauxClient:
    def table(self, *_args, **_kwargs):
        raise AssertionError("Ce test ne doit pas appeler Supabase")


supabase = types.ModuleType("supabase")
supabase.create_client = lambda *_args, **_kwargs: FauxClient()
supabase.ClientOptions = lambda **_kwargs: object()
sys.modules.setdefault("supabase", supabase)

from connexions import mcp_reseau_securise as reseau  # noqa: E402
from connexions import mcp_personnalises as mcp  # noqa: E402


def _autoriser_tout(_adresse):
    return None


class TestAdressesInterdites(unittest.TestCase):
    def test_refuse_adresses_privees_et_reservees(self):
        for valeur in (
            "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1",
            "0.0.0.0", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
            "64:ff9b::7f00:1", "2002:7f00:1::1",
        ):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError):
                    reseau.verifier_ip_publique(valeur)

    def test_accepte_adresses_publiques(self):
        for valeur in ("8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"):
            with self.subTest(valeur=valeur):
                reseau.verifier_ip_publique(valeur)

    def test_un_nom_dont_une_seule_adresse_est_privee_est_refuse(self):
        faux = [(None, None, None, None, ("8.8.8.8", 443)), (None, None, None, None, ("10.0.0.8", 443))]
        with patch.object(reseau.socket, "getaddrinfo", return_value=faux):
            with self.assertRaises(ValueError):
                reseau.resoudre_adresses_publiques("mixte.example", 443)


class _Interne(BaseHTTPRequestHandler):
    touches = []

    def do_GET(self):
        _Interne.touches.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"interne")

    do_POST = do_GET

    def log_message(self, *_):
        pass


def _serveur(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TestRedirectionsRefusees(unittest.TestCase):
    """Reproduit la faille signalée : un serveur public renvoie vers une adresse interne."""

    def test_une_redirection_n_est_jamais_suivie(self):
        interne = _serveur(_Interne)
        port_interne = interne.server_address[1]

        class Public(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(307)
                self.send_header("Location", f"http://127.0.0.1:{port_interne}/secret")
                self.end_headers()

            do_GET = do_POST

            def log_message(self, *_):
                pass

        public = _serveur(Public)
        _Interne.touches.clear()
        try:
            async def essai():
                async with reseau.creer_client_http_mcp(verificateur=_autoriser_tout) as client:
                    return await client.post(f"http://127.0.0.1:{public.server_address[1]}/mcp", json={})

            reponse = asyncio.run(essai())
            self.assertEqual(reponse.status_code, 307)
            time.sleep(0.2)
            self.assertEqual(_Interne.touches, [], "La redirection vers l'adresse interne a été suivie")
        finally:
            public.shutdown()
            interne.shutdown()

    def test_la_connexion_vers_une_adresse_privee_est_refusee(self):
        interne = _serveur(_Interne)
        _Interne.touches.clear()
        try:
            async def essai():
                async with reseau.creer_client_http_mcp() as client:
                    return await client.get(f"http://127.0.0.1:{interne.server_address[1]}/")

            with self.assertRaises(Exception):
                asyncio.run(essai())
            self.assertEqual(_Interne.touches, [])
        finally:
            interne.shutdown()

    def test_la_bibliotheque_mcp_de_production_suit_bien_les_redirections_par_defaut(self):
        """Garde-fou : si ce test échoue, la bibliothèque a changé et ce correctif est à revoir."""
        from mcp.client.streamable_http import create_mcp_http_client
        self.assertTrue(create_mcp_http_client().follow_redirects)


class TestCacheEtLenteur(unittest.TestCase):
    def setUp(self):
        mcp._CACHE_OUTILS.clear()
        mcp._CACHE_ECHECS.clear()
        mcp._CHARGEMENTS_EN_COURS.clear()

    def _serveurs(self, lignes):
        class Table:
            def select(self, *_):
                return self

            def eq(self, *_):
                return self

            def execute(self):
                return types.SimpleNamespace(data=lignes)

        class Faux:
            def table(self, *_):
                return Table()

        return patch.object(mcp, "_SUPABASE", Faux())

    def test_un_serveur_lent_ne_retarde_pas_le_message_et_l_echec_est_memorise(self):
        ligne = {"id": "11111111-2222-3333-4444-555555555555", "nom": "Lent", "url": "https://lent.example/mcp",
                 "auth_type": "none", "actif": True, "updated_at": "t0"}
        appels = []

        def lent(url, headers, delai=0):
            appels.append(url)
            time.sleep(1.5)
            raise ValueError("trop lent")

        with self._serveurs([ligne]), patch.object(mcp, "_lister_outils_reseau", side_effect=lent):
            debut = time.monotonic()
            self.assertEqual(mcp.lister_outils_pour_utilisateur("u", attente_max=0.3), [])
            self.assertLess(time.monotonic() - debut, 1.0)
            time.sleep(1.8)  # la découverte en arrière-plan se termine par un échec
            debut = time.monotonic()
            self.assertEqual(mcp.lister_outils_pour_utilisateur("u", attente_max=0.3), [])
            self.assertLess(time.monotonic() - debut, 0.2, "Un serveur en panne ne doit plus être recontacté")
            self.assertEqual(len(appels), 1)

    def test_les_routes_ne_contiennent_jamais_de_jeton(self):
        ligne = {"id": "11111111-2222-3333-4444-555555555555", "nom": "Mon serveur", "url": "https://ok.example/mcp",
                 "auth_type": "bearer", "bearer_token": "SECRET-JETON", "actif": True, "updated_at": "t0"}
        outil = types.SimpleNamespace(name="get_items", description="Liste", inputSchema={"type": "object", "properties": {}})
        with self._serveurs([ligne]), patch.object(mcp, "_lister_outils_reseau", return_value=[outil]):
            resultat = mcp.lister_outils_pour_utilisateur("u", attente_max=3)
        self.assertEqual(len(resultat), 1)
        self.assertNotIn("SECRET-JETON", repr(resultat))
        self.assertEqual(mcp.nom_serveur_pour_outil(resultat[0]["nom"]), "Mon serveur")


if __name__ == "__main__":
    unittest.main()
