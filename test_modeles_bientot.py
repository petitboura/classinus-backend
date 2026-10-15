"""Vérifie la liste des modèles "Bientôt" du sélecteur, sans appel réseau."""

import os
import unittest
from unittest.mock import patch

from core import fournisseurs_llm
from core.fournisseurs_llm import (
    DISTRIBUTEURS_BIENTOT,
    _config_modeles_de_repli,
    libelles_bientot,
    modele_id_est_autorise,
    modeles_bientot_pour_agent,
    modeles_disponibles_pour_agent,
    reinitialiser_cache_config_modeles,
)

CLES_DEEPSEEK_SEULE = {"DEEPSEEK_API_KEY": "x"}


def _avec_config_supabase(modifier):
    """Simule une lecture Supabase : repart du repli et applique `modifier`."""
    config = _config_modeles_de_repli()
    modifier(config)
    return patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=config)


class ModelesBientot(unittest.TestCase):
    def setUp(self):
        reinitialiser_cache_config_modeles()

    def tearDown(self):
        reinitialiser_cache_config_modeles()

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

    def test_cle_presente_ne_rend_pas_un_fournisseur_bientot_utilisable(self):
        cles = {"DEEPSEEK_API_KEY": "x", "OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "x", "GOOGLE_API_KEY": "x"}
        with patch.dict(os.environ, cles, clear=True):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            bientot = modeles_bientot_pour_agent("claude", "pro")
            self.assertTrue(all(m["distributeur"] == "deepseek" for m in disponibles))
            self.assertEqual({m["distributeur"] for m in bientot}, set(DISTRIBUTEURS_BIENTOT))
            for m in bientot:
                self.assertFalse(modele_id_est_autorise(m["modele_id"], "claude", "pro"))

    def test_fournisseur_non_bientot_dans_supabase_devient_utilisable(self):
        cles = {"DEEPSEEK_API_KEY": "x", "OPENAI_API_KEY": "x"}

        def ouvrir_gpt(config):
            config["fournisseurs"]["gpt"]["bientot"] = False

        with patch.dict(os.environ, cles, clear=True), _avec_config_supabase(ouvrir_gpt):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            bientot = modeles_bientot_pour_agent("claude", "pro")
        self.assertIn("gpt", {m["distributeur"] for m in disponibles})
        self.assertNotIn("gpt", {m["distributeur"] for m in bientot})

    def test_cle_api_non_requise_garde_le_fournisseur_visible_sans_cle(self):
        def sans_regle_de_cle(config):
            config["fournisseurs"]["deepseek"]["cle_api_requise"] = False

        with patch.dict(os.environ, {}, clear=True), _avec_config_supabase(sans_regle_de_cle):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
        self.assertEqual({m["distributeur"] for m in disponibles}, {"deepseek"})

    def test_cle_api_requise_masque_le_fournisseur_sans_cle(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(modeles_disponibles_pour_agent("claude", "pro"), [])

    def test_modele_inactif_dans_supabase_disparait(self):
        def retirer_pro(config):
            del config["modeles"]["deepseek"]["pro"]

        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True), _avec_config_supabase(retirer_pro):
            ids = [m["modele_id"] for m in modeles_disponibles_pour_agent("claude", "pro")]
        self.assertEqual(ids, ["deepseek-v4-flash"])

    def test_mot_bientot_vient_de_la_configuration(self):
        def autre_mot(config):
            config["textes"]["bientot"] = {"fr": "Très vite", "en": "Coming soon"}

        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True), _avec_config_supabase(autre_mot):
            bientot = modeles_bientot_pour_agent("claude", "pro")
            self.assertEqual(libelles_bientot()["en"], "Coming soon")
        self.assertTrue(bientot)
        for m in bientot:
            self.assertEqual(m["libelles_bientot"]["fr"], "Très vite")

    def test_mot_bientot_de_repli_si_texte_absent(self):
        def sans_texte(config):
            config["textes"] = {}

        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True), _avec_config_supabase(sans_texte):
            self.assertEqual(libelles_bientot(), {"fr": "Bientôt"})

    def test_supabase_en_panne_utilise_le_repli_du_code(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True), patch.object(
            fournisseurs_llm, "_lire_config_modeles_supabase", side_effect=RuntimeError("panne")
        ):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            bientot = modeles_bientot_pour_agent("claude", "pro")
        self.assertEqual({m["distributeur"] for m in disponibles}, {"deepseek"})
        self.assertEqual(len(bientot), 9)

    def test_supabase_en_panne_garde_la_derniere_configuration_connue(self):
        def ouvrir_gpt(config):
            config["fournisseurs"]["gpt"]["bientot"] = False

        cles = {"DEEPSEEK_API_KEY": "x", "OPENAI_API_KEY": "x"}
        with patch.dict(os.environ, cles, clear=True):
            with _avec_config_supabase(ouvrir_gpt):
                modeles_disponibles_pour_agent("claude", "pro")
            reinitialiser_cache_config_modeles_expire = fournisseurs_llm._cache_config_modeles
            reinitialiser_cache_config_modeles_expire["expire_a"] = 0
            with patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", side_effect=RuntimeError("panne")):
                disponibles = modeles_disponibles_pour_agent("claude", "pro")
        self.assertIn("gpt", {m["distributeur"] for m in disponibles})

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
