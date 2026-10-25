"""Vérifie la construction des demandes Higgsfield, sans réseau ni base."""
import unittest

from core.higgsfield_requetes import (
    ErreurHiggsfield,
    construire_requete_image,
    construire_requete_video,
)


class TestRequeteVideo(unittest.TestCase):
    def test_texte_seedance_par_defaut(self):
        adresse, corps = construire_requete_video(None, "un lion", None)
        self.assertEqual(adresse, "bytedance/seedance-2.0/text-to-video")
        self.assertEqual(corps["duration"], 5)
        self.assertTrue(corps["generate_audio"])

    def test_duree_bornee_et_son_kling(self):
        adresse, corps = construire_requete_video("kling", "un lion", 99, "9:16", "", False)
        self.assertEqual(adresse, "kling-video/v3.0/pro/text-to-video")
        self.assertEqual(corps["duration"], 15)
        self.assertEqual(corps["sound"], "off")

    def test_animation_image_sans_format(self):
        adresse, corps = construire_requete_video(
            "seedance", "", None, "16:9", "1080p", True, "https://x.com/a.jpg", "https://x.com/b.jpg"
        )
        self.assertEqual(adresse, "bytedance/seedance-2.0/image-to-video")
        self.assertNotIn("aspect_ratio", corps)
        self.assertEqual(corps["end_image_url"], "https://x.com/b.jpg")

    def test_refus_lisibles(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("inconnu", "a")
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("seedance", "a", 5, "7:7")
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("seedance", "a", 5, "", "", True, "http://x.com/a.jpg")
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("kling", "", 5, "", "", True, "https://x.com/a.jpg")


class TestRequeteImage(unittest.TestCase):
    def test_image_avec_references(self):
        adresse, corps = construire_requete_image(None, "un vase", "16:9", "2k", ["https://x.com/a.png"])
        self.assertEqual(adresse, "xai/grok-imagine-image-2.0")
        self.assertEqual(corps["image_urls"], ["https://x.com/a.png"])

    def test_trop_de_references(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image(None, "a", "", "", ["https://x.com/a.png"] * 11)


if __name__ == "__main__":
    unittest.main()
