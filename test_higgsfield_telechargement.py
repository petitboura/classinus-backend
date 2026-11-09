"""Tests du déblocage du téléchargement d'image après partage (09/11/2026).

Aucun appel réseau ni base : la base est remplacée par un faux client.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

_faux_auth = types.ModuleType("api.auth")
_faux_auth.supabase = MagicMock()
sys.modules.setdefault("api", types.ModuleType("api"))
sys.modules["api.auth"] = _faux_auth

from core import higgsfield_telechargement as tel  # noqa: E402
from core.erreurs import MESSAGES_EN, MESSAGES_FR  # noqa: E402


def _base(lignes):
    """Faux supabase dont select renvoie `lignes`."""
    base = MagicMock()
    chaine = base.table.return_value.select.return_value
    for _ in range(2):
        chaine = chaine.eq.return_value
    chaine.limit.return_value.execute.return_value.data = lignes
    return base


class TestDeblocage(unittest.TestCase):
    def test_image_non_partagee_verrouillee(self):
        self.assertFalse(tel.est_debloque({"genre": "image", "partage_termine_a": None}))

    def test_image_partagee_debloquee(self):
        self.assertTrue(tel.est_debloque({"genre": "image", "partage_termine_a": "2026-11-09T10:00:00Z"}))

    def test_video_jamais_verrouillee(self):
        self.assertTrue(tel.est_debloque({"genre": "video", "partage_termine_a": None}))


class TestMarquage(unittest.TestCase):
    def test_ligne_absente_refusee(self):
        with patch.object(tel, "supabase", _base([])):
            self.assertFalse(tel.marquer_partage_termine("u", "r"))

    def test_video_refusee(self):
        with patch.object(tel, "supabase", _base([{"genre": "video", "etat": "terminee", "partage_termine_a": None}])):
            self.assertFalse(tel.marquer_partage_termine("u", "r"))

    def test_image_en_cours_refusee(self):
        with patch.object(tel, "supabase", _base([{"genre": "image", "etat": "en_cours", "partage_termine_a": None}])):
            self.assertFalse(tel.marquer_partage_termine("u", "r"))

    def test_image_terminee_acceptee_et_enregistree(self):
        base = _base([{"genre": "image", "etat": "terminee", "partage_termine_a": None}])
        with patch.object(tel, "supabase", base):
            self.assertTrue(tel.marquer_partage_termine("u", "r"))
        base.table.return_value.update.assert_called_once()

    def test_deja_partagee_sans_nouvelle_ecriture(self):
        base = _base([{"genre": "image", "etat": "terminee", "partage_termine_a": "2026-11-09T10:00:00Z"}])
        with patch.object(tel, "supabase", base):
            self.assertTrue(tel.marquer_partage_termine("u", "r"))
        base.table.return_value.update.assert_not_called()


class TestMessages(unittest.TestCase):
    def test_codes_en_francais_et_anglais(self):
        for code in ("TELECHARGEMENT_PARTAGE_REQUIS", "IMPOSSIBLE_TELECHARGER_HIGGSFIELD", "PARTAGE_IMAGE_INVALIDE"):
            self.assertIn(code, MESSAGES_FR)
            self.assertIn(code, MESSAGES_EN)
            self.assertNotIn("--", MESSAGES_FR[code] + MESSAGES_EN[code])


if __name__ == "__main__":
    unittest.main()
