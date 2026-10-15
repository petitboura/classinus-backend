"""Vérifie le bloc d'identité de l'assistant (fournisseur puis modèle), sans appel réseau."""

import unittest
from unittest.mock import patch

from core import fournisseurs_llm, identite_modele
from core.fournisseurs_llm import _config_modeles_de_repli


def _avec_config_de_repli():
    return patch.object(fournisseurs_llm, "_config_modeles", return_value=_config_modeles_de_repli())


class TestBlocIdentite(unittest.TestCase):
    def test_modele_de_la_cascade_fournisseur_puis_modele(self):
        bloc = identite_modele.bloc_identite("deepseek-v4-flash")

        self.assertIn("assistant de Classinus, propulsé par DeepSeek, modèle DeepSeek V4 Flash", bloc)

    def test_chaque_modele_de_la_cascade_a_un_fournisseur(self):
        for modele_id, (fournisseur, modele) in identite_modele.MODELES_CASCADE.items():
            bloc = identite_modele.bloc_identite(modele_id)
            self.assertIn(f"propulsé par {fournisseur}, modèle {modele}", bloc, modele_id)

    def test_modele_du_selecteur_vient_de_la_configuration(self):
        with _avec_config_de_repli():
            bloc = identite_modele.bloc_identite("claude-sonnet-5")

        self.assertIn("propulsé par Anthropic, modèle Claude Sonnet 5", bloc)

    def test_nom_du_fournisseur_regle_dans_supabase_prime_sur_le_repli(self):
        config = _config_modeles_de_repli()
        config["fournisseurs"]["claude"]["nom_affiche"] = "Anthropic PBC"
        with patch.object(fournisseurs_llm, "_config_modeles", return_value=config):
            bloc = identite_modele.bloc_identite("claude-sonnet-5")

        self.assertIn("propulsé par Anthropic PBC, modèle Claude Sonnet 5", bloc)

    def test_nom_du_fournisseur_vide_dans_supabase_prend_le_repli(self):
        config = _config_modeles_de_repli()
        config["fournisseurs"]["gpt"]["nom_affiche"] = None
        with patch.object(fournisseurs_llm, "_config_modeles", return_value=config):
            bloc = identite_modele.bloc_identite("gpt-5.4")

        self.assertIn("propulsé par OpenAI, modèle GPT-5.4", bloc)

    def test_classinus_est_le_nom_de_l_application(self):
        bloc = identite_modele.bloc_identite("openai/gpt-oss-120b")

        self.assertIn("Classinus est le nom de l'application, pas le tien", bloc)
        self.assertIn("ne dis jamais que tu es Classinus", bloc)

    def test_modele_inconnu_ne_devine_rien(self):
        with _avec_config_de_repli():
            bloc = identite_modele.bloc_identite("modele-qui-n-existe-pas")

        self.assertEqual(bloc, identite_modele.BLOC_IDENTITE_INCONNU)
        self.assertNotIn("propulsé par", bloc.split("Tu ne sais pas")[0])
        self.assertIn("ne dis jamais que tu es Classinus", bloc)

    def test_modele_absent_donne_le_bloc_inconnu(self):
        self.assertEqual(identite_modele.bloc_identite(None), identite_modele.BLOC_IDENTITE_INCONNU)

    def test_configuration_illisible_ne_fait_pas_echouer(self):
        with patch.object(fournisseurs_llm, "_config_modeles", side_effect=RuntimeError("supabase")):
            bloc = identite_modele.bloc_identite("claude-sonnet-5")

        self.assertEqual(bloc, identite_modele.BLOC_IDENTITE_INCONNU)

    def test_aucun_tiret_cadratin_ni_double_tiret(self):
        textes = [identite_modele.BLOC_IDENTITE, identite_modele.BLOC_IDENTITE_INCONNU]
        for texte in textes:
            self.assertNotIn("—", texte)
            self.assertNotIn("--", texte)


class TestSystemeAvecIdentite(unittest.TestCase):
    def test_bloc_en_tete_et_prompt_intact(self):
        systeme = identite_modele.systeme_avec_identite("PROMPT_DE_BASE", "deepseek-v4-flash")

        self.assertTrue(systeme.startswith(identite_modele.bloc_identite("deepseek-v4-flash")))
        self.assertTrue(systeme.endswith("\n\nPROMPT_DE_BASE"))

    def test_prompt_vide(self):
        systeme = identite_modele.systeme_avec_identite("", "deepseek-v4-flash")

        self.assertEqual(systeme, identite_modele.bloc_identite("deepseek-v4-flash"))

    def test_message_systeme_remplace_le_premier_message_sans_cumuler(self):
        base = "PROMPT_DE_BASE"
        messages = [{"role": "system", "content": base}, {"role": "user", "content": "salut"}]

        messages[0] = identite_modele.message_systeme(base, "openai/gpt-oss-120b")
        messages[0] = identite_modele.message_systeme(base, "qwen/qwen3.6-27b")

        contenu = messages[0]["content"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(contenu.count("propulsé par"), 2)
        self.assertIn("Alibaba", contenu)
        self.assertNotIn("OpenAI", contenu)
        self.assertEqual(base, "PROMPT_DE_BASE")


if __name__ == "__main__":
    unittest.main()
