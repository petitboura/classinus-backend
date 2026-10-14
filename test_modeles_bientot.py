"""Vérifie la liste des modèles "Bientôt" du sélecteur, sans appel réseau."""

import os
import unittest
from unittest.mock import patch

from core.fournisseurs_llm import (
    DISTRIBUTEURS_BIENTOT,
    modele_id_est_autorise,
    modeles_bientot_pour_agent,
    modeles_disponibles_pour_agent,
)

CLES_DEEPSEEK_SEULE = {"DEEPSEEK_API_KEY": "x"}


class ModelesBientot(unittest.TestCase):
    def test_deepseek_seul_utilisable_les_autres_bientot(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            bientot = modeles_bientot_pour_agent("claude", "pro")
        self.assertEqual({m["distributeur"] for m in disponibles}, {"deepseek"})
        self.assertEqual({m["distributeur"] for m in bientot}, set(DISTRIBUTEURS_BIENTOT))
        # 3 niveaux pour chacun des 3 fournisseurs "bientôt".
        self.assertEqual(len(bientot), 9)

    def test_aucun_modele_en_double(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            bientot = modeles_bientot_pour_agent("claude", "pro")
        ids = [m["modele_id"] for m in disponibles + bientot]
        self.assertEqual(len(ids), len(set(ids)))

    def test_un_modele_devenu_disponible_sort_de_la_liste_bientot(self):
        cles = {"DEEPSEEK_API_KEY": "x", "OPENAI_API_KEY": "x"}
        with patch.dict(os.environ, cles, clear=True):
            bientot = modeles_bientot_pour_agent("claude", "pro")
        self.assertNotIn("gpt", {m["distributeur"] for m in bientot})

    def test_agent_sans_modele_debloque_n_a_rien(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            self.assertEqual(modeles_bientot_pour_agent(None, None), [])
            self.assertEqual(modeles_bientot_pour_agent("aucun", "pro"), [])

    def test_un_modele_bientot_n_est_jamais_autorise(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            bientot = modeles_bientot_pour_agent("claude", "pro")
            for m in bientot:
                self.assertFalse(modele_id_est_autorise(m["modele_id"], "claude", "pro"))


if __name__ == "__main__":
    unittest.main()
