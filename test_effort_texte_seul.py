"""
Le chemin "texte seul" (core/fournisseurs_llm.py:generer_reponse_premium) envoie l'effort choisi
(22/11/2026, regle "tout modele a son effort" de CLAUDE.md).

Avant ce correctif, seul DeepSeek recevait son effort sur ce chemin : Claude, GPT, Gemini, Grok,
Meta, les modeles Vultr et Baseten le perdaient. Aucun appel reseau ici : les clients des SDK sont
remplaces par des faux qui enregistrent ce qu'ils recoivent.
"""

import os
import types
import unittest
from unittest.mock import patch

from core import fournisseurs_llm
from core.fournisseurs_llm import effort_a_envoyer

NS = types.SimpleNamespace
MESSAGES = [{"role": "user", "content": "salut"}]


def morceau_texte(texte):
    return NS(choices=[NS(delta=NS(content=texte, reasoning_content=None))])


class FauxOpenAI:
    """Remplace openai.OpenAI : garde les arguments du dernier appel de chat.completions.create."""

    derniers_arguments = None

    def __init__(self, api_key=None, base_url=None, **reste):
        self.chat = NS(completions=self)

    def create(self, **arguments):
        FauxOpenAI.derniers_arguments = arguments
        return iter([morceau_texte("ok")])


class EffortAEnvoyer(unittest.TestCase):
    def test_le_choix_valide_passe_sinon_le_defaut_du_modele(self):
        self.assertEqual(effort_a_envoyer("claude-opus-5-5", "max", "claude"), "max")
        self.assertEqual(effort_a_envoyer("claude-opus-5-5", "none", "claude"), "low")
        self.assertEqual(effort_a_envoyer("claude-opus-5-5", None, "claude"), "low")
        self.assertEqual(effort_a_envoyer("gpt-6.2-sol", "none", "gpt"), "low")
        self.assertEqual(effort_a_envoyer("grok-4.7", "xhigh", "grok"), "xhigh")


class ChatCompletionsRecoitL_effort(unittest.TestCase):
    def setUp(self):
        FauxOpenAI.derniers_arguments = None

    def lire(self, modele, effort, cle):
        with patch.dict(os.environ, {cle: "cle-test"}, clear=True), patch("openai.OpenAI", FauxOpenAI):
            return list(fournisseurs_llm.generer_reponse_premium(modele, "consigne", MESSAGES, effort=effort))

    def test_gpt(self):
        self.assertEqual(self.lire("gpt-6.2-sol", "high", "OPENAI_API_KEY"), ["ok"])
        self.assertEqual(FauxOpenAI.derniers_arguments["reasoning_effort"], "high")

    def test_gpt_sans_choix_prend_le_niveau_le_plus_leger(self):
        self.lire("gpt-6.2-sol", None, "OPENAI_API_KEY")
        self.assertEqual(FauxOpenAI.derniers_arguments["reasoning_effort"], "low")

    def test_grok(self):
        self.lire("grok-4.7", "xhigh", "XAI_API_KEY")
        self.assertEqual(FauxOpenAI.derniers_arguments["reasoning_effort"], "xhigh")

    def test_grok_refuse_un_niveau_qu_il_ne_connait_pas(self):
        # grok-4.7 n'a pas "max" : le niveau par defaut part a la place, jamais une valeur refusee.
        self.lire("grok-4.7", "max", "XAI_API_KEY")
        self.assertEqual(FauxOpenAI.derniers_arguments["reasoning_effort"], "low")

    def test_meta(self):
        self.lire("muse-spark-1.3", "max", "MODEL_API_KEY")
        self.assertEqual(FauxOpenAI.derniers_arguments["reasoning_effort"], "max")

class ClaudeRecoitL_effort(unittest.TestCase):
    def test_claude_envoie_output_config_effort(self):
        recu = {}

        class FauxFlux:
            text_stream = iter(["bon", "jour"])

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        class FauxAnthropic:
            def __init__(self, api_key=None, **reste):
                self.messages = self

            def stream(self, **arguments):
                recu.update(arguments)
                return FauxFlux()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "cle-test"}, clear=True), patch("anthropic.Anthropic", FauxAnthropic):
            texte = "".join(fournisseurs_llm.generer_reponse_premium("claude-opus-5-5", "consigne", MESSAGES, effort="xhigh"))
        self.assertEqual(texte, "bonjour")
        self.assertEqual(recu["extra_body"], {"output_config": {"effort": "xhigh"}})
        self.assertEqual(recu["model"], "claude-opus-5-5")


class GeminiRecoitL_effort(unittest.TestCase):
    def sdk(self):
        """Le vrai SDK google-genai, ou saut du test : test_gif_joint.py remplace le module google
        par un faux (sans le remettre) quand toute la suite tourne d'un coup."""
        try:
            from google import genai as genai_module
            from google.genai import types as genai_types
            genai_module.Client
        except Exception:
            self.skipTest("SDK google-genai remplace par un faux par un autre fichier de tests")
        return genai_module, genai_types

    def lire(self, genai_module, effort):
        recu = {}

        class FauxModeles:
            def generate_content_stream(self, **arguments):
                recu.update(arguments)
                return iter([NS(text="ok")])

        class FauxClient:
            def __init__(self, api_key=None, **reste):
                self.models = FauxModeles()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-test"}, clear=True), \
                patch.object(genai_module, "Client", FauxClient):
            list(fournisseurs_llm.generer_reponse_premium("gemini-4-argon", "consigne", MESSAGES, effort=effort))
        return recu["config"]

    def test_gemini_envoie_thinking_level(self):
        genai_module, genai_types = self.sdk()
        configuration = self.lire(genai_module, "high")
        self.assertEqual(configuration.thinking_config.thinking_level, genai_types.ThinkingLevel.HIGH)
        self.assertEqual(configuration.system_instruction, "consigne")

    def test_gemini_sans_choix_prend_le_niveau_le_plus_leger(self):
        genai_module, genai_types = self.sdk()
        configuration = self.lire(genai_module, None)
        self.assertEqual(configuration.thinking_config.thinking_level, genai_types.ThinkingLevel.LOW)


class VultrEtBasetenRecoiventL_effort(unittest.TestCase):
    def test_vultr_seul_glm_ne_part_plus_au_maximum_par_defaut(self):
        recu = {}
        faux_client = NS(chat=NS(completions=NS(create=lambda **kw: recu.update(kw) or iter([morceau_texte("ok")]))))
        with patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "v"}, clear=True), \
                patch.object(fournisseurs_llm, "creer_client_vultr_generique", return_value=faux_client):
            fournisseurs_llm.reinitialiser_cache_config_modeles()
            self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)
            list(fournisseurs_llm.generer_reponse_premium("glm-5.3", "sys", MESSAGES))
        self.assertEqual(recu["reasoning_effort"], "low")

    def test_vultr_seul_envoie_le_choix(self):
        recu = {}
        faux_client = NS(chat=NS(completions=NS(create=lambda **kw: recu.update(kw) or iter([morceau_texte("ok")]))))
        with patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "v"}, clear=True), \
                patch.object(fournisseurs_llm, "creer_client_vultr_generique", return_value=faux_client):
            fournisseurs_llm.reinitialiser_cache_config_modeles()
            self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)
            list(fournisseurs_llm.generer_reponse_premium("glm-5.3", "sys", MESSAGES, effort="max"))
        self.assertEqual(recu["reasoning_effort"], "max")


if __name__ == "__main__":
    unittest.main()
