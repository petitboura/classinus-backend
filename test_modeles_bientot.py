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
        # 3 niveaux pour Claude, GPT et Gemini, 3 modèles pour Grok (grok-4.3 sert deux niveaux, plus grok-build-0.1), 2 pour Meta (avance et pro).
        self.assertEqual(len(bientot), 14)

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
        self.assertEqual(len(bientot), 14)

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


class ModelesGrok(unittest.TestCase):
    def setUp(self):
        reinitialiser_cache_config_modeles()

    def tearDown(self):
        reinitialiser_cache_config_modeles()

    def test_ordre_finit_par_grok_puis_meta(self):
        from core.fournisseurs_llm import ORDRE_DISTRIBUTEURS
        self.assertEqual(ORDRE_DISTRIBUTEURS, ["claude", "gpt", "gemini", "deepseek", "grok", "meta"])

    def test_grok_deux_modeles_trois_niveaux_et_bientot(self):
        config = _config_modeles_de_repli()
        self.assertEqual(config["modeles"]["grok"]["essentiel"]["id"], "grok-4.3")
        self.assertEqual(config["modeles"]["grok"]["avance"]["id"], "grok-4.3")
        self.assertEqual(config["modeles"]["grok"]["pro"]["id"], "grok-4.7")
        self.assertTrue(config["fournisseurs"]["grok"]["bientot"])
        self.assertEqual(config["fournisseurs"]["grok"]["variable_cle_api"], "XAI_API_KEY")

    def test_grok_bientot_sans_doublon_et_jamais_autorise(self):
        with patch.dict(os.environ, {"XAI_API_KEY": "x", "DEEPSEEK_API_KEY": "x"}, clear=True):
            bientot = modeles_bientot_pour_agent("claude", "pro")
            grok = [m["modele_id"] for m in bientot if m["distributeur"] == "grok"]
            self.assertEqual(grok, ["grok-build-0.1", "grok-4.7", "grok-4.3"])
            self.assertFalse(modele_id_est_autorise("grok-4.7", "claude", "pro"))

    def test_grok_utilisable_quand_bientot_retire_et_cle_presente(self):
        with _avec_config_supabase(lambda config: config["fournisseurs"]["grok"].update(bientot=False)):
            with patch.dict(os.environ, {"XAI_API_KEY": "x"}, clear=True):
                disponibles = modeles_disponibles_pour_agent("gemini", "pro")
                ids = [m["modele_id"] for m in disponibles]
                self.assertEqual(ids, ["grok-4.7", "grok-4.3"])
                self.assertTrue(modele_id_est_autorise("grok-4.7", "gemini", "pro"))
                # Grok est le dernier de la hierarchie : un agent debloque a DeepSeek le voit aussi.
                self.assertIn("grok-4.7", [m["modele_id"] for m in modeles_disponibles_pour_agent("deepseek", "pro")])
                # Un agent debloque a Grok seul ne voit que Grok.
                self.assertEqual({m["distributeur"] for m in modeles_disponibles_pour_agent("grok", "pro")}, {"grok"})

    def test_grok_build_jamais_choisissable_meme_sans_bientot(self):
        with _avec_config_supabase(lambda config: config["fournisseurs"]["grok"].update(bientot=False)):
            with patch.dict(os.environ, {"XAI_API_KEY": "x"}, clear=True):
                for palier in ("essentiel", "avance", "pro"):
                    self.assertFalse(modele_id_est_autorise("grok-build-0.1", "claude", palier))
                self.assertTrue(modele_id_est_autorise("grok-build-0.1", "claude", "specialise"))

    def test_grok_sans_cle_invisible(self):
        with _avec_config_supabase(lambda config: config["fournisseurs"]["grok"].update(bientot=False)):
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(modeles_disponibles_pour_agent("gemini", "pro"), [])

    def test_modele_grok_reconnu_et_connexion_prevue(self):
        from core.fournisseurs_llm import distributeur_pour_modele_id, _STREAMERS_PAR_DISTRIBUTEUR
        with patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=None):
            self.assertEqual(distributeur_pour_modele_id("grok-4.7"), "grok")
        self.assertIn("grok", _STREAMERS_PAR_DISTRIBUTEUR)

    def test_connexion_grok_utilise_ladresse_xai(self):
        from core.fournisseurs_llm import _stream_grok
        envoye = {}

        class FauxOpenAI:
            def __init__(self, api_key=None, base_url=None):
                envoye["base_url"] = base_url
                envoye["cle"] = api_key
                self.chat = self
                self.completions = self

            def create(self, **kwargs):
                envoye["modele"] = kwargs["model"]
                envoye["messages"] = kwargs["messages"]
                morceau = type("M", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": "bonjour"})()})()]})()
                return iter([morceau])

        with patch.dict(os.environ, {"XAI_API_KEY": "cle-test"}, clear=True), patch("openai.OpenAI", FauxOpenAI):
            texte = "".join(_stream_grok("grok-4.7", "consigne", [{"role": "user", "content": "salut"}]))
        self.assertEqual(texte, "bonjour")
        self.assertEqual(envoye["base_url"], "https://api.x.ai/v1")
        self.assertEqual(envoye["cle"], "cle-test")
        self.assertEqual(envoye["modele"], "grok-4.7")
        self.assertEqual(envoye["messages"][0], {"role": "system", "content": "consigne"})


class ModelesMeta(unittest.TestCase):
    """Meta (28/10/2026, staging en Bientôt) : dernier de la hiérarchie, après Grok."""

    def setUp(self):
        reinitialiser_cache_config_modeles()

    def tearDown(self):
        reinitialiser_cache_config_modeles()

    def test_meta_deux_modeles_avance_pro_sans_essentiel_et_bientot(self):
        config = _config_modeles_de_repli()
        self.assertNotIn("essentiel", config["modeles"]["meta"])
        self.assertEqual(config["modeles"]["meta"]["avance"]["id"], "muse-spark-1.3")
        self.assertEqual(config["modeles"]["meta"]["pro"]["id"], "muse-wonder-1.0")
        self.assertTrue(config["fournisseurs"]["meta"]["bientot"])
        self.assertEqual(config["fournisseurs"]["meta"]["variable_cle_api"], "MODEL_API_KEY")

    def test_meta_bientot_wonder_en_premier_sans_doublon_et_jamais_autorise(self):
        with patch.dict(os.environ, {"MODEL_API_KEY": "x", "DEEPSEEK_API_KEY": "x"}, clear=True):
            bientot = modeles_bientot_pour_agent("claude", "pro")
            meta = [m["modele_id"] for m in bientot if m["distributeur"] == "meta"]
            self.assertEqual(meta, ["muse-wonder-1.0", "muse-spark-1.3"])
            self.assertFalse(modele_id_est_autorise("muse-wonder-1.0", "claude", "pro"))

    def test_meta_utilisable_quand_bientot_retire_et_cle_presente(self):
        with _avec_config_supabase(lambda config: config["fournisseurs"]["meta"].update(bientot=False)):
            with patch.dict(os.environ, {"MODEL_API_KEY": "x"}, clear=True):
                disponibles = modeles_disponibles_pour_agent("gemini", "pro")
                ids = [m["modele_id"] for m in disponibles]
                self.assertEqual(ids, ["muse-wonder-1.0", "muse-spark-1.3"])
                self.assertTrue(modele_id_est_autorise("muse-wonder-1.0", "gemini", "pro"))
                # Meta est le dernier de la hierarchie : un agent debloque a Grok le voit aussi.
                self.assertIn("muse-wonder-1.0", [m["modele_id"] for m in modeles_disponibles_pour_agent("grok", "pro")])
                # Un agent debloque a Meta seul ne voit que Meta.
                self.assertEqual({m["distributeur"] for m in modeles_disponibles_pour_agent("meta", "pro")}, {"meta"})

    def test_meta_sans_cle_invisible(self):
        with _avec_config_supabase(lambda config: config["fournisseurs"]["meta"].update(bientot=False)):
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(modeles_disponibles_pour_agent("gemini", "pro"), [])

    def test_modele_meta_reconnu_et_connexion_prevue(self):
        from core.fournisseurs_llm import distributeur_pour_modele_id, _STREAMERS_PAR_DISTRIBUTEUR
        with patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=None):
            self.assertEqual(distributeur_pour_modele_id("muse-wonder-1.0"), "meta")
        self.assertIn("meta", _STREAMERS_PAR_DISTRIBUTEUR)

    def test_connexion_meta_utilise_ladresse_meta(self):
        from core.fournisseurs_llm import _stream_meta
        envoye = {}

        class FauxOpenAI:
            def __init__(self, api_key=None, base_url=None):
                envoye["base_url"] = base_url
                envoye["cle"] = api_key
                self.chat = self
                self.completions = self

            def create(self, **kwargs):
                envoye["modele"] = kwargs["model"]
                envoye["messages"] = kwargs["messages"]
                morceau = type("M", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": "bonjour"})()})()]})()
                return iter([morceau])

        with patch.dict(os.environ, {"MODEL_API_KEY": "cle-test"}, clear=True), patch("openai.OpenAI", FauxOpenAI):
            texte = "".join(_stream_meta("muse-spark-1.3", "consigne", [{"role": "user", "content": "salut"}]))
        self.assertEqual(texte, "bonjour")
        self.assertEqual(envoye["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(envoye["cle"], "cle-test")
        self.assertEqual(envoye["modele"], "muse-spark-1.3")
        self.assertEqual(envoye["messages"][0], {"role": "system", "content": "consigne"})


if __name__ == "__main__":
    unittest.main()
