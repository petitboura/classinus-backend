"""Tests standard-library du stockage et des frontières d'accès de l'atelier vidéo."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.video_workspaces as video_workspaces


class FauxStockageR2:
    def __init__(self):
        self.objets: dict[str, bytes] = {}

    def upload(self, chemin: str, contenu: bytes, options: dict | None = None):
        self.objets[chemin] = bytes(contenu)

    def download(self, chemin: str) -> bytes:
        if chemin not in self.objets:
            raise FileNotFoundError(chemin)
        return self.objets[chemin]

    def remove(self, chemins: list[str]):
        for chemin in chemins:
            self.objets.pop(chemin, None)


class TestEspacesVideo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root_initial = video_workspaces.ROOT
        video_workspaces.ROOT = Path(self.tmp.name) / "instance-a"
        self.stockage = FauxStockageR2()
        self.patch_stockage = patch("core.stockage_r2.from_", return_value=self.stockage)
        self.patch_stockage.start()
        self.addCleanup(self.patch_stockage.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, video_workspaces, "ROOT", self.root_initial)

    def test_source_originale_et_metadonnees_durables(self):
        contenu = b"fake-video-content"
        meta = video_workspaces.enregistrer_video(
            "utilisateur-a",
            "conversation-a",
            "../ma-video.mp4",
            "video/mp4",
            contenu,
            12.3456,
        )

        self.assertEqual(meta["nom_fichier"], "ma-video.mp4")
        self.assertEqual(meta["duree_secondes"], 12.346)
        self.assertEqual(video_workspaces.lire_metadonnees_video(
            "utilisateur-a", "conversation-a", meta["video_id"]
        ), meta)
        self.assertEqual(video_workspaces.chemin_video(
            "utilisateur-a", "conversation-a", meta["video_id"]
        ).read_bytes(), contenu)
        self.assertEqual(len([k for k in self.stockage.objets if k.endswith(".mp4")]), 1)
        self.assertTrue(any(k.endswith(".json") for k in self.stockage.objets))

    def test_une_autre_conversation_ne_peut_pas_lire_la_source(self):
        meta = video_workspaces.enregistrer_video(
            "utilisateur-a", "conversation-a", "source.mp4", "video/mp4", b"video"
        )
        with self.assertRaises(FileNotFoundError):
            video_workspaces.lire_metadonnees_video(
                "utilisateur-a", "conversation-b", meta["video_id"]
            )
        with self.assertRaises(FileNotFoundError):
            video_workspaces.chemin_video(
                "utilisateur-b", "conversation-a", meta["video_id"]
            )

    def test_source_restaurable_sur_une_autre_instance_railway(self):
        contenu = b"video-qui-survit-au-redemarrage"
        meta = video_workspaces.enregistrer_video(
            "utilisateur-a", "conversation-a", "source.webm", "video/webm", contenu
        )
        video_workspaces.ROOT = Path(self.tmp.name) / "instance-b"

        donnees = video_workspaces.lire_metadonnees_video(
            "utilisateur-a", "conversation-a", meta["video_id"]
        )
        restauree = video_workspaces.chemin_video(
            "utilisateur-a", "conversation-a", meta["video_id"]
        )
        self.assertEqual(donnees["video_id"], meta["video_id"])
        self.assertEqual(restauree.read_bytes(), contenu)
        self.assertTrue(restauree.is_file())

    def test_chemins_externes_et_sorties_dans_uploads_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "uploads").mkdir()
            (root / "outputs").mkdir()
            source = root / "uploads" / "source.mp4"
            source.write_bytes(b"video")
            with self.assertRaises(ValueError):
                video_workspaces.chemin_interne(root, "../../etc/passwd")
            with self.assertRaises(ValueError):
                video_workspaces.chemin_interne(root, "https://example.com/video.mp4")
            with self.assertRaises(ValueError):
                video_workspaces.chemin_interne(root, str(source), sortie=True)
            sortie = video_workspaces.chemin_interne(
                root, "outputs/version-1.mp4", sortie=True
            )
            self.assertEqual(Path(sortie), root / "outputs" / "version-1.mp4")


if __name__ == "__main__":
    unittest.main()
