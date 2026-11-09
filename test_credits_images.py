"""Tests des crédits d'images (09/11/2026).

Règles verrouillées : 1 crédit retiré par image juste avant l'envoi à Higgsfield, refus à 0 avec un
message clair en français et en anglais, crédit rendu si la génération échoue, la vidéo n'est
jamais touchée. Aucun appel réseau ni base dans ces tests : un faux client Supabase suffit.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.credits_images import (
    ErreurCreditsImages,
    message_pour_ia,
    rattacher_credit_image,
    rendre_credit_image,
    reserver_credit_image,
)
from core.erreurs import MESSAGES_EN, MESSAGES_FR
from core.higgsfield_requetes import ErreurHiggsfield

RACINE = Path(__file__).parent


class _Reponse:
    def __init__(self, data):
        self.data = data


class _Appel:
    def __init__(self, client, nom, parametres):
        self.client, self.nom, self.parametres = client, nom, parametres

    def execute(self):
        self.client.appels.append((self.nom, self.parametres))
        if self.client.erreur is not None:
            raise self.client.erreur
        return _Reponse(self.client.reponse)


class FauxClient:
    def __init__(self, reponse=True, erreur=None):
        self.reponse, self.erreur, self.appels = reponse, erreur, []

    def rpc(self, nom, parametres):
        return _Appel(self, nom, parametres)


class TestReserver(unittest.TestCase):
    def test_retire_un_credit_et_renvoie_une_reference(self):
        client = FauxClient(reponse=True)
        reference = reserver_credit_image(client, "user-1")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", reference))
        self.assertEqual(client.appels, [("credits_images_reserver", {"p_user": "user-1", "p_reference": reference})])

    def test_references_differentes_a_chaque_retrait(self):
        client = FauxClient(reponse=True)
        self.assertNotEqual(reserver_credit_image(client, "u"), reserver_credit_image(client, "u"))

    def test_solde_a_zero_refuse_avec_le_bon_code(self):
        with self.assertRaises(ErreurCreditsImages) as contexte:
            reserver_credit_image(FauxClient(reponse=False), "user-1")
        self.assertEqual(contexte.exception.code, "CREDITS_IMAGES_EPUISES")

    def test_base_en_panne_refuse_jamais_d_image_gratuite(self):
        with self.assertRaises(ErreurCreditsImages) as contexte:
            reserver_credit_image(FauxClient(erreur=RuntimeError("panne")), "user-1")
        self.assertEqual(contexte.exception.code, "CREDITS_IMAGES_INDISPONIBLE")

    def test_reponse_inattendue_refusee(self):
        with self.assertRaises(ErreurCreditsImages):
            reserver_credit_image(FauxClient(reponse=None), "user-1")

    def test_sans_utilisateur_refuse_sans_toucher_la_base(self):
        client = FauxClient()
        with self.assertRaises(ErreurHiggsfield) as contexte:
            reserver_credit_image(client, None)
        self.assertNotIsInstance(contexte.exception, ErreurCreditsImages)
        self.assertEqual(client.appels, [])

    def test_erreur_credits_est_une_erreur_higgsfield(self):
        self.assertTrue(issubclass(ErreurCreditsImages, ErreurHiggsfield))


class TestRendreEtRattacher(unittest.TestCase):
    def test_rendre_appelle_la_fonction_avec_la_reference(self):
        client = FauxClient()
        rendre_credit_image(client, "user-1", "ref-1")
        self.assertEqual(client.appels, [("credits_images_rendre", {"p_user": "user-1", "p_reference": "ref-1"})])

    def test_rendre_ne_leve_jamais(self):
        rendre_credit_image(FauxClient(erreur=RuntimeError("panne")), "user-1", "ref-1")

    def test_rendre_sans_reference_ou_sans_utilisateur_ne_fait_rien(self):
        client = FauxClient()
        rendre_credit_image(client, "user-1", None)
        rendre_credit_image(client, None, "ref-1")
        self.assertEqual(client.appels, [])

    def test_rattacher_remplace_la_reference_provisoire(self):
        client = FauxClient()
        rattacher_credit_image(client, "user-1", "ref-1", "req-9")
        self.assertEqual(
            client.appels,
            [("credits_images_rattacher", {"p_user": "user-1", "p_ancienne": "ref-1", "p_nouvelle": "req-9"})],
        )

    def test_rattacher_ne_leve_jamais(self):
        rattacher_credit_image(FauxClient(erreur=RuntimeError("panne")), "user-1", "ref-1", "req-9")

    def test_rattacher_sans_donnees_ne_fait_rien(self):
        client = FauxClient()
        rattacher_credit_image(client, "user-1", None, "req-9")
        rattacher_credit_image(client, "user-1", "ref-1", "")
        self.assertEqual(client.appels, [])


class TestMessages(unittest.TestCase):
    CODES = ("CREDITS_IMAGES_EPUISES", "CREDITS_IMAGES_INDISPONIBLE")

    def test_chaque_code_a_un_texte_francais_et_anglais(self):
        for code in self.CODES:
            self.assertTrue(MESSAGES_FR.get(code), f"{code} sans texte français")
            self.assertTrue(MESSAGES_EN.get(code), f"{code} sans texte anglais")

    def test_message_credits_epuises_invite_a_parrainer(self):
        self.assertIn("Invite tes amis", MESSAGES_FR["CREDITS_IMAGES_EPUISES"])
        self.assertIn("Invite your friends", MESSAGES_EN["CREDITS_IMAGES_EPUISES"])

    def test_aucun_chiffre_ecrit_en_dur(self):
        # Le solde de départ et le gain par filleul se règlent en base : jamais écrits dans un message.
        for code in self.CODES:
            self.assertNotRegex(MESSAGES_FR[code], r"\d")
            self.assertNotRegex(MESSAGES_EN[code], r"\d")
            self.assertNotRegex(message_pour_ia(ErreurCreditsImages(code)), r"\d")

    def test_message_pour_ia_empeche_de_relancer(self):
        texte = message_pour_ia(ErreurCreditsImages("CREDITS_IMAGES_EPUISES"))
        self.assertIn("sans relancer", texte)

    def test_code_inconnu_donne_le_message_indisponible(self):
        self.assertEqual(
            message_pour_ia(ErreurCreditsImages("AUTRE")),
            message_pour_ia(ErreurCreditsImages("CREDITS_IMAGES_INDISPONIBLE")),
        )


def _corps(texte: str, debut: str, fin: str) -> str:
    i = texte.index(debut)
    return texte[i : texte.index(fin, i)]


class TestToutesLesEntreesDImages(unittest.TestCase):
    """Garde-fous : si une entrée d'image perd son crédit, ou si la vidéo est touchée, un test échoue."""

    @classmethod
    def setUpClass(cls):
        cls.api = (RACINE / "api" / "higgsfield.py").read_text(encoding="utf-8")
        cls.outils = (RACINE / "core" / "outils_higgsfield.py").read_text(encoding="utf-8")
        cls.suivi = (RACINE / "core" / "higgsfield_suivi.py").read_text(encoding="utf-8")

    def test_route_image_retire_et_rend_le_credit(self):
        corps = _corps(self.api, "def lancer_image", "@router.post(\"/genjutsu\")")
        self.assertIn("reserver_credit_image", corps)
        self.assertIn("rendre_credit_image", corps)
        self.assertIn("rattacher_credit_image", corps)
        self.assertIn("ErreurCreditsImages", corps)

    def test_credit_retire_avant_l_envoi_a_higgsfield(self):
        for corps in (
            _corps(self.api, "def lancer_image", "@router.post(\"/genjutsu\")"),
            _corps(self.outils, "def generer_image_higgsfield", "def consulter_image_higgsfield"),
        ):
            self.assertLess(corps.index("reserver_credit_image"), corps.index("lancer_generation("))

    def test_outil_du_chat_retire_et_rend_le_credit(self):
        corps = _corps(self.outils, "def generer_image_higgsfield", "def consulter_image_higgsfield")
        self.assertIn("reserver_credit_image", corps)
        self.assertIn("rendre_credit_image", corps)
        self.assertIn("message_pour_ia", corps)

    def test_marketing_studio_en_image_retire_et_rend_le_credit(self):
        corps = _corps(self.api, "def lancer_marketing_studio", "@router.get(\"/statut/")
        self.assertIn('media == "image"', corps)
        self.assertIn("reserver_credit_image", corps)
        self.assertIn("rendre_credit_image", corps)
        self.assertIn("ErreurCreditsImages", corps)

    def test_suivi_rend_le_credit_d_une_image_qui_n_a_pas_abouti(self):
        self.assertIn("rendre_credit_image", _corps(self.suivi, "def marquer_annulee", "def _revendiquer"))
        terminer = _corps(self.suivi, "def _terminer", "def _traiter_une")
        self.assertIn("rendre_credit_image", terminer)
        self.assertIn('"image"', terminer)

    def test_outil_de_suivi_du_chat_rend_le_credit_sur_echec(self):
        corps = _corps(self.outils, "def _texte_suivi", "if higgsfield_api_disponible()")
        self.assertIn("rendre_credit_image", corps)

    def test_la_video_n_est_jamais_touchee(self):
        for corps in (
            _corps(self.api, "def lancer_video", "@router.post(\"/image\")"),
            _corps(self.api, "def lancer_genjutsu", "class DemandeMarketingStudio"),
            _corps(self.outils, "def lancer_video_higgsfield", "def consulter_video_higgsfield"),
        ):
            self.assertNotIn("credit", corps.lower())


if __name__ == "__main__":
    unittest.main()
