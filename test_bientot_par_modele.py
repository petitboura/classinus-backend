"""
Verifie le Bientot modele par modele (04/11/2026, demande de Bourama) : DeepSeek Pro et Muse
Spark Open restent Bientot alors que leur fournisseur est ouvert, sauf pour les adresses de la
table acces_anticipe_modeles (ceux qui voient tout). Sans appel reseau.
"""

import copy
import unittest
from unittest.mock import patch

from core import fournisseurs_llm

CLES = {"DEEPSEEK_API_KEY": "d", "MODEL_API_KEY": "m", "BASETEN_API_KEY": "b", "VULTR_INFERENCE_API_KEY": "v"}
VOIT_TOUT = "voit.tout@example.com"


def config_de_test():
    config = fournisseurs_llm._config_modeles_de_repli()
    config = copy.deepcopy(config)
    # DeepSeek ouvert, Meta Bientot, Spark Open ouvert a tous par Baseten mais Bientot lui-meme.
    config["fournisseurs"]["deepseek"]["bientot"] = False
    config["fournisseurs"]["meta"]["bientot"] = True
    config["modeles"]["deepseek"]["pro"]["bientot"] = True
    config["modeles"]["meta"]["intermediaire"] = {
        "id": "muse-spark-open",
        "label": "Muse Spark Open",
        "baseten": "meta-models/muse-spark-open-1026",
        "baseten_seul": True,
        "bientot": True,
    }
    config["fournisseurs"]["grok"]["bientot"] = True
    config["acces_anticipe"] = {"deepseek": {VOIT_TOUT}, "meta": {VOIT_TOUT}, "grok": {VOIT_TOUT}}
    return config


class BientotParModele(unittest.TestCase):
    def setUp(self):
        for parche in (
            patch.object(fournisseurs_llm, "_config_modeles", side_effect=lambda: config_de_test()),
            patch.object(fournisseurs_llm, "_distributeur_disponible", return_value=True),
            patch.object(fournisseurs_llm, "cle_baseten_disponible", return_value=True),
            patch.object(fournisseurs_llm, "cle_vultr_disponible", return_value=True),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def ids(self, liste):
        return [m["modele_id"] for m in liste]

    def test_deepseek_pro_ferme_aux_autres(self):
        disponibles = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro", "autre@example.com")
        self.assertIn("deepseek-v4-flash", self.ids(disponibles))
        self.assertNotIn("deepseek-v4-pro", self.ids(disponibles))

    def test_spark_open_ferme_aux_autres(self):
        disponibles = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro", "autre@example.com")
        self.assertNotIn("muse-spark-open", self.ids(disponibles))

    def test_les_deux_figurent_en_bientot(self):
        bientot = fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro", "autre@example.com")
        self.assertIn("deepseek-v4-pro", self.ids(bientot))
        self.assertIn("muse-spark-open", self.ids(bientot))
        self.assertNotIn("deepseek-v4-flash", self.ids(bientot))

    def test_ceux_qui_voient_tout_gardent_les_deux(self):
        disponibles = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro", VOIT_TOUT)
        self.assertIn("deepseek-v4-pro", self.ids(disponibles))
        self.assertIn("muse-spark-open", self.ids(disponibles))
        bientot = fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro", VOIT_TOUT)
        self.assertNotIn("deepseek-v4-pro", self.ids(bientot))
        self.assertNotIn("muse-spark-open", self.ids(bientot))

    def test_choix_refuse_pour_les_autres_accepte_pour_ceux_qui_voient_tout(self):
        self.assertFalse(fournisseurs_llm.modele_id_est_autorise("deepseek-v4-pro", "claude", "pro", "autre@example.com"))
        self.assertTrue(fournisseurs_llm.modele_id_est_autorise("deepseek-v4-pro", "claude", "pro", VOIT_TOUT))

    def test_grok_build_ouvert_seulement_a_ceux_qui_voient_tout(self):
        autres = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro", "autre@example.com")
        self.assertNotIn("grok-build-0.1", self.ids(autres))
        self.assertIn("grok-build-0.1", self.ids(fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro", "autre@example.com")))
        eux = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro", VOIT_TOUT)
        self.assertIn("grok-build-0.1", self.ids(eux))
        self.assertNotIn("grok-build-0.1", self.ids(fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro", VOIT_TOUT)))
        self.assertTrue(fournisseurs_llm.modele_id_est_autorise("grok-build-0.1", "claude", "pro", VOIT_TOUT))
        self.assertFalse(fournisseurs_llm.modele_id_est_autorise("grok-build-0.1", "claude", "pro", "autre@example.com"))


if __name__ == "__main__":
    unittest.main()
