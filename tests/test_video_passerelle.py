"""Tests de la passerelle mcp-video : aucune ressource hors de l'espace de travail."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SUPABASE_SECRET", "test-only-video-gateway-secret")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("R2_ENDPOINT", "https://example.invalid")
os.environ.setdefault("R2_BUCKET_NAME", "test")

from core import serveur_mcp_video as passerelle


class TestPasserelleVideo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "uploads").mkdir()
        (self.root / "outputs").mkdir()
        (self.root / "uploads" / "source.mp4").write_bytes(b"x")
        (self.root / "uploads" / "voix.wav").write_bytes(b"x")

    def normaliser(self, outil, arguments):
        return passerelle._normaliser_arguments(outil, arguments, self.root)

    def test_cles_imbriquees_hors_espace_refusees(self):
        cas = [
            ("audio_compose", {"tracks": [{"file": "/etc/hostname"}]}),
            ("audio_compose", {"tracks": [{"file": "http://169.254.169.254/latest/meta-data/"}]}),
            ("video_edit", {"timeline": {"tracks": [{"type": "image", "images": [{"source": "/etc/hostname"}]}]}}),
            ("video_edit", {"timeline": {"tracks": [{"type": "video", "clips": [{"source": "../../etc/passwd"}]}]}}),
        ]
        for outil, arguments in cas:
            with self.subTest(outil=outil, arguments=arguments):
                with self.assertRaises(ValueError):
                    self.normaliser(outil, arguments)

    def test_chaines_libres_dangereuses_refusees_quelle_que_soit_la_cle(self):
        for valeur in (
            "http://exemple.test/a.mp4",
            "https://exemple.test/a.mp4",
            "concat:/etc/passwd|/etc/hostname",
            "file:/etc/passwd",
            "pipe:0",
            "data:text/plain;base64,AAAA",
            "/etc/passwd",
            "../../etc/passwd",
            "dossier/../../../etc/passwd",
        ):
            with self.subTest(valeur=valeur):
                with self.assertRaises(ValueError):
                    self.normaliser("video_add_text", {"mystere": {"cle_inconnue": valeur}})

    def test_textes_ordinaires_non_touches(self):
        for texte in (
            "Visite https://classinus.com pour la suite",
            "Note: bonjour",
            "Data: 5 éléments",
            "File: rapport final",
            "Attends.. et regarde",
            "iw/2",
            "scale=1280:720",
            "#141414",
        ):
            with self.subTest(texte=texte):
                resultat = self.normaliser("video_add_text", {"text": texte})
                self.assertEqual(resultat["text"], texte)

    def test_fichiers_de_l_espace_acceptes(self):
        resultat = self.normaliser(
            "audio_compose",
            {"tracks": [{"file": "uploads/voix.wav", "volume": 1.0}]},
        )
        self.assertEqual(resultat["tracks"][0]["file"], str(self.root / "uploads" / "voix.wav"))
        absolu = str(self.root / "uploads" / "source.mp4")
        self.assertEqual(self.normaliser("video_trim", {"input_path": absolu})["input_path"], absolu)
        # Un chemin absolu de l'espace dans une clé inconnue reste accepté.
        self.assertEqual(self.normaliser("video_trim", {"x": {"y": absolu}})["x"]["y"], absolu)

    def test_chemins_connus_toujours_bloques(self):
        for outil, arguments in (
            ("video_trim", {"input_path": "/etc/hostname"}),
            ("video_batch", {"inputs": ["../../etc/passwd"], "operation": "trim"}),
        ):
            with self.subTest(outil=outil):
                with self.assertRaises(ValueError):
                    self.normaliser(outil, arguments)

    def test_sortie_hors_outputs_refusee(self):
        with self.assertRaises(ValueError):
            self.normaliser("video_trim", {"input_path": "uploads/source.mp4", "output_path": "uploads/ecrase.mp4"})

    def test_remotion_studio_non_expose(self):
        self.assertIn("remotion_studio", passerelle.OUTILS_NON_EXPOSES)
        self.assertNotIn("remotion_studio", passerelle._outils_exposes())
        if passerelle._tools_dict():
            self.assertIn("video_trim", passerelle._outils_exposes())


if __name__ == "__main__":
    unittest.main()
