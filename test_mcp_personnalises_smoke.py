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
        with patch.object(mcp.socket, "getaddrinfo", return_value=resultat_dns):
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


if __name__ == "__main__":
    unittest.main()
