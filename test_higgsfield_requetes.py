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


class TestReferencesVideo(unittest.TestCase):
    def test_references_seedance(self):
        adresse, corps = construire_requete_video(
            "seedance", "le héros court", 6, "9:16", "", True, "", "",
            ["https://x.com/a.jpg"], ["https://x.com/v.mp4"], None,
        )
        self.assertEqual(adresse, "bytedance/seedance-2.0/reference-to-video")
        self.assertEqual(corps["image_urls"], ["https://x.com/a.jpg"])
        self.assertEqual(corps["video_urls"], ["https://x.com/v.mp4"])

    def test_references_refusees(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("kling", "a", 5, "", "", True, "", "", ["https://x.com/a.jpg"])
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("seedance", "a", 5, "", "", True, "https://x.com/p.jpg", "", ["https://x.com/a.jpg"])
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("seedance", "a", 5, "", "", True, "", "", None, None, ["https://x.com/s.mp3"])
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_video("seedance", "a", 5, "", "", True, "", "", ["https://x.com/a.jpg"] * 10)


class TestRequeteImage(unittest.TestCase):
    def test_image_avec_references(self):
        adresse, corps = construire_requete_image(None, "un vase", "16:9", "2k", ["https://x.com/a.png"])
        self.assertEqual(adresse, "xai/grok-imagine-image-2.0")
        self.assertEqual(corps["image_urls"], ["https://x.com/a.png"])

    def test_trop_de_references(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image(None, "a", "", "", ["https://x.com/a.png"] * 11)


class TestRequeteSoul(unittest.TestCase):
    STYLE_Y2K = "7ee16ff3-c0b0-4f5f-a0e1-e7fc46144230"

    def test_soul_envoie_le_texte_le_style_le_format_et_la_qualite(self):
        adresse, corps = construire_requete_image("soul", "un portrait", "9:16", "1080p", None, self.STYLE_Y2K)
        self.assertEqual(adresse, "higgsfield-ai/soul/v2/standard")
        self.assertEqual(corps["prompt"], "un portrait")
        self.assertEqual(corps["style_id"], self.STYLE_Y2K)
        self.assertEqual(corps["aspect_ratio"], "9:16")
        self.assertEqual(corps["resolution"], "1080p")
        self.assertNotIn("image_urls", corps)

    def test_soul_sans_reglage_laisse_les_valeurs_par_defaut_de_higgsfield(self):
        adresse, corps = construire_requete_image("soul", "un portrait")
        self.assertEqual(corps, {"prompt": "un portrait"})
        # Le format par défaut (1:1) n'est pas renvoyé, comme pour grok avec auto.
        _, corps = construire_requete_image("soul", "un portrait", "1:1", "720p")
        self.assertNotIn("aspect_ratio", corps)

    def test_identifiant_de_style_en_majuscules_accepte(self):
        _, corps = construire_requete_image("soul", "a", "", "", None, self.STYLE_Y2K.upper())
        self.assertEqual(corps["style_id"], self.STYLE_Y2K)

    def test_soul_refuse_ce_qu_il_ne_sait_pas_faire(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image("soul", "a", "", "", ["https://x.com/a.png"])
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image("soul", "a", "auto")
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image("soul", "a", "", "1k")
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image("soul", "a", "", "", None, "pas-un-uuid")

    def test_style_refuse_pour_grok(self):
        with self.assertRaises(ErreurHiggsfield):
            construire_requete_image("grok", "a", "", "", None, self.STYLE_Y2K)

    def test_grok_inchange(self):
        adresse, corps = construire_requete_image("grok", "un vase", "auto", "1k")
        self.assertEqual(adresse, "xai/grok-imagine-image-2.0")
        self.assertEqual(corps, {"prompt": "un vase", "resolution": "1k"})


if __name__ == "__main__":
    unittest.main()
