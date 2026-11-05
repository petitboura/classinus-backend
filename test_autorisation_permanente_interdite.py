"""Tests hors ligne : "Toujours autoriser" est impossible pour l'action finale du navigateur et
pour l'accès réseau de la boîte de code (aucun réseau, base simulée)."""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from core import autorisations_outils, boucle_agent
from core.execution_outils import _est_outil_sensible, cle_autorisation_appel
from core.registre_outils import AUTORISATION_PERMANENTE_INTERDITE

APPEL_SUBMIT = {"id": "a1", "name": "gerer_navigateur", "arguments": json.dumps({"action": "submit"})}
APPEL_RESEAU = {"id": "a2", "name": "gerer_execution_code", "arguments": json.dumps({"action": "demander_acces_reseau"})}
APPEL_CAPTURE = {"id": "a3", "name": "gerer_navigateur", "arguments": json.dumps({"action": "screenshot"})}


def _attente(appel):
    attente = MagicMock()
    attente.appel = appel
    attente.appels_restants = []
    return attente


class AutorisationPermanenteInterditeTest(unittest.TestCase):
    def test_les_deux_actions_sont_listees(self):
        self.assertEqual(
            AUTORISATION_PERMANENTE_INTERDITE,
            {"gerer_navigateur:submit", "gerer_execution_code:demander_acces_reseau"},
        )

    def test_elles_restent_sensibles(self):
        self.assertTrue(_est_outil_sensible(APPEL_SUBMIT))
        self.assertTrue(_est_outil_sensible(APPEL_RESEAU))
        self.assertFalse(_est_outil_sensible(APPEL_CAPTURE))

    def test_une_autorisation_deja_en_base_est_ignoree(self):
        cle = cle_autorisation_appel(APPEL_SUBMIT)
        self.assertEqual(cle, "gerer_navigateur:submit")
        lignes = MagicMock()
        lignes.data = [{"cle": "gerer_navigateur:submit"}, {"cle": "gerer_depot_github:creer_issue"}]
        base = MagicMock()
        base.table.return_value.select.return_value.eq.return_value.execute.return_value = lignes
        with patch.object(autorisations_outils, "_supabase_memoire", base):
            autorisees = autorisations_outils.charger_autorisations("u1")
        self.assertNotIn("gerer_navigateur:submit", autorisees)
        self.assertIn("gerer_depot_github:creer_issue", autorisees)
        self.assertTrue(_est_outil_sensible(APPEL_SUBMIT, autorisees))

    def test_rien_n_est_enregistre(self):
        base = MagicMock()
        with patch.object(autorisations_outils, "_supabase_memoire", base):
            self.assertFalse(autorisations_outils.enregistrer_autorisation("u1", "gerer_navigateur:submit", "x"))
            self.assertFalse(
                autorisations_outils.enregistrer_autorisation("u1", "gerer_execution_code:demander_acces_reseau", "x")
            )
        base.table.assert_not_called()

    def test_les_autres_actions_restent_memorisables(self):
        self.assertTrue(autorisations_outils.cle_valide("gerer_depot_github:creer_issue"))

    def test_le_bouton_n_est_pas_propose(self):
        for appel in (APPEL_SUBMIT, APPEL_RESEAU):
            evenement = boucle_agent._evenement_confirmation(_attente(appel), [], [], {})
            self.assertIsNone(evenement["cle_autorisation"])

    def test_le_bouton_reste_propose_pour_les_autres(self):
        appel = {"id": "a4", "name": "gerer_depot_github", "arguments": json.dumps({"action": "creer_issue"})}
        evenement = boucle_agent._evenement_confirmation(_attente(appel), [], [], {})
        self.assertEqual(evenement["cle_autorisation"], "gerer_depot_github:creer_issue")


if __name__ == "__main__":
    unittest.main()
