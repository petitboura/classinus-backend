"""Tests de la passerelle mcp-video : aucune ressource hors de l'espace de travail."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class TestDependancesRemotion(unittest.TestCase):
    """node_modules n'est jamais sauvegardé : la passerelle doit le réinstaller."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projet = Path(self.tmp.name).resolve() / "projects" / "titre-anime"
        self.projet.mkdir(parents=True)

    def _avec_package_json(self):
        (self.projet / "package.json").write_text("{}", encoding="utf-8")

    def test_rien_a_faire_sans_package_json(self):
        with mock.patch.object(passerelle.subprocess, "run") as lancer:
            passerelle._assurer_dependances_remotion(self.projet)
        lancer.assert_not_called()

    def test_rien_a_faire_si_node_modules_present(self):
        self._avec_package_json()
        (self.projet / "node_modules").mkdir()
        with mock.patch.object(passerelle.subprocess, "run") as lancer:
            passerelle._assurer_dependances_remotion(self.projet)
        lancer.assert_not_called()

    def test_installe_quand_node_modules_manque(self):
        self._avec_package_json()
        fini = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(passerelle.subprocess, "run", return_value=fini) as lancer:
            passerelle._assurer_dependances_remotion(self.projet)
        lancer.assert_called_once()
        commande = lancer.call_args.args[0]
        self.assertEqual(commande[:2], ["npm", "install"])
        self.assertEqual(lancer.call_args.kwargs["cwd"], str(self.projet))
        self.assertIn("npm_config_cache", lancer.call_args.kwargs["env"])

    def test_echec_npm_remonte_un_message_lisible(self):
        self._avec_package_json()
        echec = mock.Mock(returncode=1, stdout="", stderr="npm ERR! network request failed")
        with mock.patch.object(passerelle.subprocess, "run", return_value=echec):
            with self.assertRaises(RuntimeError) as contexte:
                passerelle._assurer_dependances_remotion(self.projet)
        self.assertIn("installation des dépendances", str(contexte.exception))
        self.assertIn("network request failed", str(contexte.exception))
        self.assertNotIn("--", str(contexte.exception))

    def test_delai_depasse_remonte_un_message_lisible(self):
        self._avec_package_json()
        delai = passerelle.subprocess.TimeoutExpired(cmd="npm install", timeout=1)
        with mock.patch.object(passerelle.subprocess, "run", side_effect=delai):
            with self.assertRaises(RuntimeError) as contexte:
                passerelle._assurer_dependances_remotion(self.projet)
        self.assertIn("délai", str(contexte.exception))

    def test_npm_introuvable_remonte_un_message_lisible(self):
        self._avec_package_json()
        with mock.patch.object(passerelle.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(RuntimeError) as contexte:
                passerelle._assurer_dependances_remotion(self.projet)
        self.assertIn("npm est introuvable", str(contexte.exception))

    def test_dossier_projet_lu_dans_les_arguments(self):
        self.assertEqual(
            passerelle._dossier_projet_remotion({"project_path": str(self.projet), "composition_id": "x"}),
            self.projet,
        )
        self.assertEqual(passerelle._dossier_projet_remotion({"project_dir": str(self.projet)}), self.projet)
        self.assertIsNone(passerelle._dossier_projet_remotion({"composition_id": "x"}))
        self.assertIsNone(passerelle._dossier_projet_remotion({"project_path": ""}))


if __name__ == "__main__":
    unittest.main()
