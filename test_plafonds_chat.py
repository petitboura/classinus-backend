"""Plafonds du chat : aucun plafond sur le contenu, plafonds de nombre, branchement dans l'application.

Decision de Bourama (23/10/2026) : le contenu (message, historique, resultats d'outils) n'est pas
plafonne, l'architecture s'en charge. Ces tests importent api.chat et api.main : ils demandent les
dependances completes du projet (requirements.txt) et sont ignores si elles manquent. Le plafond de
taille de requete et les reglages sont testes dans test_plafond_taille_requete.py (sans base).
"""
import os
import unittest

os.environ.setdefault("SUPABASE_URL", "http://x.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "eyJhbGciOiJIUzI1NiJ9.e30.x")

try:
    import api.chat  # noqa: F401
    _MANQUE = None
except ImportError as erreur:  # dependances completes absentes
    _MANQUE = f"dependances completes du projet requises : {erreur}"

avec_dependances_completes = unittest.skipIf(_MANQUE is not None, _MANQUE or "")

from core import plafonds_reglables as reglages

GROS = "x" * 300000


def _outils(n):
    return [{"nomOutil": "o", "nomLisible": "o", "resultat": "r"}] * n


@avec_dependances_completes
class ContenuNonPlafonne(unittest.TestCase):
    def setUp(self):
        from api.chat import EnvoyerMessagePayload

        self.P = EnvoyerMessagePayload

    def test_gros_message_courant(self):
        self.P(message=GROS)

    def test_gros_message_ancien_et_longue_reponse(self):
        self.P(message="a", historique=[{"role": "user", "content": GROS}, {"role": "assistant", "content": GROS}])

    def test_historique_tres_long(self):
        self.P(message="a", historique=[{"role": "user", "content": "a"}] * 1000)

    def test_gros_resultat_d_outil(self):
        self.P(message="a", historique=[{"role": "assistant", "content": "a", "outils": [{"nomOutil": "o", "nomLisible": "o", "resultat": GROS}]}])

    def test_plus_de_25_mo_au_total(self):
        self.P(message="a", historique=[{"role": "user", "content": GROS}] * 100)


@avec_dependances_completes
class PlafondsDeNombre(unittest.TestCase):
    def setUp(self):
        from api.chat import EnvoyerMessagePayload

        self.P = EnvoyerMessagePayload

    def _accepte(self, **kw):
        self.P(message="a", **kw)

    def _refuse(self, **kw):
        with self.assertRaises(Exception):
            self.P(message="a", **kw)

    def test_outils_par_message_10000(self):
        self._accepte(historique=[{"role": "assistant", "content": "a", "outils": _outils(500)}])
        self._accepte(historique=[{"role": "assistant", "content": "a", "outils": _outils(10000)}])
        self._refuse(historique=[{"role": "assistant", "content": "a", "outils": _outils(10001)}])

    def test_images_jointes_30(self):
        self._accepte(image_urls=["u"] * 30)
        self._refuse(image_urls=["u"] * 31)

    def test_zips_joints_20(self):
        self._accepte(zips_en_attente=["z"] * 20)
        self._refuse(zips_en_attente=["z"] * 21)


@avec_dependances_completes
class BranchementDansLApplication(unittest.TestCase):
    def test_plafond_pose_sur_le_chat_et_plus_interne_que_cors_et_traduction(self):
        from api.main import app

        noms = [m.cls.__name__ for m in app.user_middleware]  # du plus externe au plus interne
        self.assertIn("PlafondTailleRequete", noms)
        i = noms.index("PlafondTailleRequete")
        self.assertGreater(i, noms.index("CORSMiddleware"))
        self.assertGreater(i, noms.index("MiddlewareLangueErreurs"))
        options = app.user_middleware[i].kwargs
        self.assertEqual(options["prefixes"], ("/api/chat",))
        self.assertEqual(options["taille_max_mo"], reglages.TAILLE_MAX_REQUETE_CHAT_MO)


if __name__ == "__main__":
    unittest.main()
