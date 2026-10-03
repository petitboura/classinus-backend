"""Vérifie les réglages de transport, sans appel réseau."""

import os
import unittest
from unittest.mock import patch
from core.gemini_live_config import reglages_gemini_live, version_api_gemini_live


class VersionGeminiLive(unittest.TestCase):
    def test_proactivite_active_utilise_alpha(self):
        with patch.dict(os.environ, {"GEMINI_LIVE_PROACTIVITE": "1"}, clear=True):
            config = reglages_gemini_live()
            self.assertTrue(config["proactivite"])
            self.assertEqual(version_api_gemini_live(config["url"]), "v1alpha")

    def test_proactivite_inactive_conserve_beta(self):
        with patch.dict(os.environ, {"GEMINI_LIVE_PROACTIVITE": "0"}, clear=True):
            config = reglages_gemini_live()
            self.assertFalse(config["proactivite"])
            self.assertEqual(version_api_gemini_live(config["url"]), "v1beta")

    def test_url_explicite_reste_prioritaire(self):
        url = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
        with patch.dict(os.environ, {"GEMINI_LIVE_PROACTIVITE": "1", "GEMINI_LIVE_URL": url}, clear=True):
            config = reglages_gemini_live()
            self.assertEqual(config["url"], url)
            self.assertEqual(version_api_gemini_live(config["url"]), "v1beta")


if __name__ == "__main__":
    unittest.main()
