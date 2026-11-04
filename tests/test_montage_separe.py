"""Serveur de montage séparé : URL choisie par le chat, file d'attente, base Remotion."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import montage_file_attente as file_attente  # noqa: E402
from core import registre_outils  # noqa: E402
from core.remotion_prepare import preparer_node_modules  # noqa: E402


class UrlMontageTests(unittest.TestCase):
    def test_sans_variable_le_chat_appelle_son_propre_serveur(self):
        with mock.patch.dict(os.environ, {"PORT": "8000"}, clear=False):
            os.environ.pop("MONTAGE_VIDEO_URL", None)
            url = registre_outils._url_video(lambda _k: None, "u1", "a1", "c1")
        self.assertTrue(url.startswith("http://localhost:8000/mcp/video/?"))

    def test_avec_variable_le_chat_appelle_le_serveur_de_montage(self):
        with mock.patch.dict(os.environ, {"MONTAGE_VIDEO_URL": "https://montage.example.com/"}):
            url = registre_outils._url_video(lambda _k: None, "u1", "a1", "c1")
        self.assertTrue(url.startswith("https://montage.example.com/mcp/video/?"))
        self.assertIn("user_id=u1", url)
        self.assertIn("conversation_id=c1", url)

    def test_variable_invalide_ignoree(self):
        with mock.patch.dict(os.environ, {"MONTAGE_VIDEO_URL": "montage.example.com", "PORT": "8000"}):
            url = registre_outils._url_video(lambda _k: None, "u1", "a1", "c1")
        self.assertTrue(url.startswith("http://localhost:8000/"))


class FileAttenteTests(unittest.TestCase):
    def test_attente_trop_longue_renvoie_une_erreur_lisible(self):
        with mock.patch.object(file_attente, "_places", file_attente.threading.BoundedSemaphore(1)), \
                mock.patch.object(file_attente, "ATTENTE_MAX_S", 0.05):
            file_attente.prendre_place()
            with self.assertRaises(file_attente.AttenteTropLongue):
                file_attente.prendre_place()
            file_attente.liberer_place()
            file_attente.prendre_place()
            file_attente.liberer_place()


class BaseRemotionTests(unittest.TestCase):
    def _ecrire(self, dossier: Path, deps: dict):
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "package.json").write_text(json.dumps({"dependencies": deps}), encoding="utf-8")

    def test_copie_quand_les_paquets_sont_dans_la_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, projet = Path(tmp) / "base", Path(tmp) / "projet"
            self._ecrire(base, {"remotion": "^4", "react": "^18"})
            (base / "node_modules" / "remotion").mkdir(parents=True)
            (base / "node_modules" / "remotion" / "index.js").write_text("ok", encoding="utf-8")
            self._ecrire(projet, {"remotion": "^4.0.0"})
            with mock.patch.dict(os.environ, {"REMOTION_BASE_DIR": str(base)}):
                self.assertTrue(preparer_node_modules(projet))
            self.assertTrue((projet / "node_modules" / "remotion" / "index.js").is_file())

    def test_repli_si_paquet_inconnu_de_la_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, projet = Path(tmp) / "base", Path(tmp) / "projet"
            self._ecrire(base, {"remotion": "^4"})
            (base / "node_modules").mkdir(parents=True)
            self._ecrire(projet, {"remotion": "^4", "lodash": "^4"})
            with mock.patch.dict(os.environ, {"REMOTION_BASE_DIR": str(base)}):
                self.assertFalse(preparer_node_modules(projet))
            self.assertFalse((projet / "node_modules").exists())

    def test_repli_sans_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            projet = Path(tmp) / "projet"
            self._ecrire(projet, {"remotion": "^4"})
            with mock.patch.dict(os.environ, {"REMOTION_BASE_DIR": str(Path(tmp) / "absent")}):
                self.assertFalse(preparer_node_modules(projet))


if __name__ == "__main__":
    unittest.main()
