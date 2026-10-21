"""Tests de non-régression pour la localisation FR/EN."""
import unittest

from core.erreurs import MESSAGES_EN, MESSAGES_FR
from core.localisation import _prefer_anglais, _traduire_enveloppe


class TestLocalisation(unittest.TestCase):
    def test_chaque_code_erreur_a_une_traduction_anglaise(self):
        self.assertEqual(set(MESSAGES_FR), set(MESSAGES_EN))

    def test_entete_anglais_simple(self):
        self.assertTrue(_prefer_anglais({"headers": [(b"accept-language", b"en")]}))

    def test_entete_anglais_region_et_qualite(self):
        self.assertTrue(
            _prefer_anglais(
                {"headers": [(b"accept-language", b"en-US,en;q=0.9,fr;q=0.8")]}
            )
        )

    def test_entete_francais(self):
        self.assertFalse(_prefer_anglais({"headers": [(b"accept-language", b"fr")]}))

    def test_entete_absent_reste_francais(self):
        self.assertFalse(_prefer_anglais({"headers": []}))

    def test_traduction_erreur_avec_parametre(self):
        enveloppe = {
            "detail": {
                "code": "AGENT_NOM_DEJA_PROCHE",
                "message": "Texte français",
                "params": {"agent_id": "agent-123"},
            }
        }
        self.assertTrue(_traduire_enveloppe(enveloppe))
        self.assertIn("agent-123", enveloppe["detail"]["message"])
        self.assertIn("already exists", enveloppe["detail"]["message"])

    def test_code_inconnu_est_inchange(self):
        enveloppe = {"detail": {"code": "CODE_INCONNU", "message": "message français"}}
        avant = {"detail": dict(enveloppe["detail"])}
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)

    def test_payload_non_structure_est_inchange(self):
        enveloppe = {"detail": "Message français"}
        avant = dict(enveloppe)
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)


if __name__ == "__main__":
    unittest.main()
