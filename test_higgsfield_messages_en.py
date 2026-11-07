"""Chaque erreur Higgsfield visible par l'utilisateur doit exister en anglais."""
import os
import unittest

os.environ.setdefault("HIGGSFIELD_API_KEY", "test")

from core.higgsfield_messages_en import message_en
from core.higgsfield_requetes import ErreurHiggsfield, construire_requete_genjutsu, construire_requete_image, construire_requete_video

VIDEO = "https://exemple.com/v.mp4"
IMG = "https://exemple.com/i.png"
MOTS_FRANCAIS = (" le ", " la ", " les ", " des ", " une ", "Il faut", "Choisis", "Impossible", "Utilise", " pas ", " ne ", "à", "é", "è")


def _erreurs():
    appels = [
        lambda: construire_requete_video("inconnu", "x"),
        lambda: construire_requete_video("seedance", "x", image_url="http://pas-https.com/i.png"),
        lambda: construire_requete_video("seedance", ""),
        lambda: construire_requete_video("seedance", "x", image_fin_url=IMG),
        lambda: construire_requete_video("seedance", "x", format_video="9:99"),
        lambda: construire_requete_image("inconnu", "x"),
        lambda: construire_requete_image("grok", ""),
        lambda: construire_requete_image("grok", "x", format_image="zzz"),
        lambda: construire_requete_image("grok", "x", style_id="3db34ab5-3439-4317-9e03-08dc30852e69"),
        lambda: construire_requete_image("soul", "x", images_reference=[IMG]),
        lambda: construire_requete_image("soul", "x", style_id="pas-un-uuid"),
        lambda: construire_requete_image("grok", "x", images_reference=[IMG] * 20),
        lambda: construire_requete_genjutsu("inconnu", VIDEO, [IMG]),
        lambda: construire_requete_genjutsu("genjutsu-motion", "", [IMG]),
        lambda: construire_requete_genjutsu("genjutsu-motion", VIDEO, []),
        lambda: construire_requete_genjutsu("genjutsu-motion", VIDEO, [IMG], preset_id="x"),
        lambda: construire_requete_genjutsu("genjutsu-motion", VIDEO, [IMG] * 20),
    ]
    for appel in appels:
        try:
            appel()
        except ErreurHiggsfield as e:
            yield str(e)


class TestMessagesEn(unittest.TestCase):
    def test_chaque_erreur_est_traduite(self):
        messages = list(_erreurs())
        self.assertGreaterEqual(len(messages), 12)
        for francais in messages:
            anglais = message_en(francais)
            self.assertNotEqual(anglais, francais, francais)
            for mot in MOTS_FRANCAIS:
                self.assertNotIn(mot, " " + anglais + " ", f"{francais} -> {anglais}")

    def test_limites_et_libelles(self):
        self.assertEqual(
            message_en("Limite du jour atteinte (3 vidéos par jour). Dis-le à l'utilisateur : il pourra en refaire demain."),
            "Daily limit reached (3 videos per day). You can make more tomorrow.",
        )
        self.assertEqual(message_en("Maximum 8 pour : les images de référence."), "Maximum 8 for: the reference images.")
        self.assertEqual(message_en("La vidéo source doit être une adresse publique en https."), "The source video must be a public https address.")

    def test_message_inconnu_rendu_tel_quel(self):
        self.assertEqual(message_en("Texte venant d'ailleurs"), "Texte venant d'ailleurs")


if __name__ == "__main__":
    unittest.main()
