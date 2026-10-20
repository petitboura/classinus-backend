"""
Vérifie les adaptateurs Claude, GPT, Grok et Gemini sans appel réseau (20/10/2026).

Chaque test joue un flux simulé du fournisseur, relit les morceaux comme le fait la boucle
d'agent (core/boucle_agent.py), puis vérifie la conversion des messages du tour suivant.
"""

import json
import types
import unittest
from unittest.mock import patch

from core import fournisseurs_llm
from core.adaptateur_claude import ClientClaude, _convertir_messages as claude_messages
from core.adaptateur_commun import CLE_ETAT_FOURNISSEUR
from core.adaptateur_gemini import ClientGemini, _convertir_messages as gemini_messages
from core.adaptateur_responses import ClientResponses, _convertir_messages as responses_messages
from core.efforts_modeles import effort_defaut, effort_valide_pour_modele, efforts_pour_modele

NS = types.SimpleNamespace

OUTILS = [{"type": "function", "function": {
    "name": "chercher", "description": "Cherche", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
}}]


def lire_flux(flux):
    """Recolle les morceaux comme la boucle d'agent : texte, raisonnement, appels, fin."""
    texte, raisonnement, appels, fin = "", "", {}, None
    for morceau in flux:
        choix = morceau.choices[0]
        if choix.finish_reason:
            fin = choix.finish_reason
        if choix.delta.content:
            texte += choix.delta.content
        if choix.delta.reasoning:
            raisonnement += choix.delta.reasoning
        for fragment in choix.delta.tool_calls or []:
            appel = appels.setdefault(fragment.index, {"id": None, "name": "", "arguments": ""})
            if fragment.id:
                appel["id"] = fragment.id
            if fragment.function.name:
                appel["name"] += fragment.function.name
            if fragment.function.arguments:
                appel["arguments"] += fragment.function.arguments
    return texte, raisonnement, [appels[i] for i in sorted(appels)], fin


def messages_apres_outil(appel, etat):
    assistant = {"role": "assistant", "content": None, CLE_ETAT_FOURNISSEUR: etat, "tool_calls": [{
        "id": appel["id"], "type": "function", "function": {"name": appel["name"], "arguments": appel["arguments"]},
    }]}
    return [
        {"role": "system", "content": "Consigne de base"},
        {"role": "user", "content": "Cherche les dérivées"},
        assistant,
        {"role": "tool", "tool_call_id": appel["id"], "content": "résultat de la recherche"},
    ]


class Efforts(unittest.TestCase):
    def test_chaque_fournisseur_a_ses_niveaux(self):
        self.assertEqual(efforts_pour_modele("claude-sonnet-5-5", "claude"), ["low", "medium", "high", "xhigh", "max"])
        self.assertEqual(efforts_pour_modele("gpt-6-astra", "gpt"), ["low", "medium", "high", "xhigh", "max"])
        self.assertEqual(efforts_pour_modele("gpt-6-luna", "gpt")[0], "none")
        self.assertEqual(efforts_pour_modele("grok-4.7", "grok"), ["low", "medium", "high", "xhigh"])
        self.assertEqual(efforts_pour_modele("grok-4.3", "grok")[0], "none")
        self.assertEqual(efforts_pour_modele("gemini-4-argon", "gemini"), ["low", "medium", "high"])
        self.assertEqual(efforts_pour_modele("deepseek-v4-flash", "deepseek"), ["none", "low", "high", "max"])

    def test_modele_inconnu_recoit_la_liste_prudente_de_son_fournisseur(self):
        self.assertEqual(efforts_pour_modele("claude-futur-9", "claude"), ["low", "medium", "high"])

    def test_effort_refuse_remplace_par_le_defaut(self):
        self.assertEqual(effort_valide_pour_modele("gpt-6-astra", "none", "gpt"), "low")
        self.assertEqual(effort_valide_pour_modele("grok-4.7", "max", "grok"), "low")
        self.assertEqual(effort_valide_pour_modele("claude-opus-5-5", "xhigh", "claude"), "xhigh")
        self.assertIsNone(effort_defaut([]))

    def test_la_liste_des_modeles_porte_les_efforts(self):
        avec_cles = {"ANTHROPIC_API_KEY": "x", "DEEPSEEK_API_KEY": "x"}
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        config = fournisseurs_llm._config_modeles_de_repli()
        config["fournisseurs"]["claude"]["bientot"] = False
        with patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=config), \
                patch.dict("os.environ", avec_cles, clear=True):
            modeles = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro")
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        for modele in modeles:
            self.assertIn("efforts", modele)
            self.assertEqual(modele["effort_defaut"], "low")
        claude = [m for m in modeles if m["distributeur"] == "claude"]
        self.assertTrue(claude)


class Responses(unittest.TestCase):
    def _client(self, evenements):
        client = ClientResponses("cle", "openai")
        client._client = NS(responses=NS(create=lambda **arguments: self._enregistrer(arguments, evenements)))
        return client

    def _enregistrer(self, arguments, evenements):
        self.arguments = arguments
        return iter(evenements)

    def test_appel_d_outil_avec_raisonnement_rejoue(self):
        raisonnement = NS(type="reasoning", id="rs_1", model_dump=lambda exclude_none=True: {
            "type": "reasoning", "id": "rs_1", "encrypted_content": "abc", "summary": []})
        appel = NS(type="function_call", id="fc_1", call_id="call_1", name="chercher", arguments='{"q":"x"}',
                   model_dump=lambda exclude_none=True: {
                       "type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "chercher", "arguments": '{"q":"x"}'})
        evenements = [
            NS(type="response.reasoning_summary_text.delta", delta="Je réfléchis"),
            NS(type="response.output_item.done", item=raisonnement),
            NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="call_1", name="chercher")),
            NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='{"q":'),
            NS(type="response.function_call_arguments.delta", item_id="fc_1", delta='"x"}'),
            NS(type="response.output_item.done", item=appel),
            NS(type="response.completed"),
        ]
        client = self._client(evenements)
        flux = client.chat.completions.create(
            model="gpt-6-astra", messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}],
            tools=OUTILS, reasoning_effort="high", max_completion_tokens=4096, timeout=10, stream=True)
        texte, pensee, appels, fin = lire_flux(flux)
        self.assertEqual(pensee, "Je réfléchis")
        self.assertEqual(appels, [{"id": "call_1", "name": "chercher", "arguments": '{"q":"x"}'}])
        self.assertEqual(fin, "tool_calls")
        self.assertEqual(self.arguments["reasoning"], {"effort": "high", "summary": "auto"})
        self.assertIs(self.arguments["store"], False)
        self.assertEqual(self.arguments["tools"][0]["name"], "chercher")
        self.assertNotIn("max_output_tokens", self.arguments)
        etat = client.etat_dernier_tour()
        self.assertEqual([e["type"] for e in etat["elements"]], ["reasoning", "function_call"])

        instructions, entree = responses_messages(messages_apres_outil(appels[0], etat), True)
        self.assertEqual(instructions, "Consigne de base")
        self.assertEqual([e.get("type") or e["role"] for e in entree],
                         ["user", "reasoning", "function_call", "function_call_output"])
        self.assertEqual(entree[-1], {"type": "function_call_output", "call_id": "call_1", "output": "résultat de la recherche"})

    def test_arguments_non_diffuses_repris_a_la_fin_de_l_element(self):
        appel = NS(type="function_call", id="fc_1", call_id="call_1", name="chercher", arguments='{"q":"y"}',
                   model_dump=lambda exclude_none=True: {"type": "function_call"})
        client = self._client([
            NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="call_1", name="chercher")),
            NS(type="response.output_item.done", item=appel),
        ])
        _, _, appels, _ = lire_flux(client.chat.completions.create(model="grok-4.7", messages=[], tools=OUTILS))
        self.assertEqual(appels[0]["arguments"], '{"q":"y"}')

    def test_reponse_texte_sans_outil(self):
        client = self._client([NS(type="response.output_text.delta", delta="Bonjour"), NS(type="response.completed")])
        texte, _, appels, fin = lire_flux(client.chat.completions.create(model="gpt-6-luna", messages=[]))
        self.assertEqual((texte, appels, fin), ("Bonjour", [], "stop"))
        self.assertIsNone(client.etat_dernier_tour())

    def test_grok_sans_stockage_ni_resume(self):
        client = ClientResponses("cle", "xai")
        client._client = NS(responses=NS(create=lambda **a: self._enregistrer(a, [])))
        lire_flux(client.chat.completions.create(model="grok-4.7", messages=[], reasoning_effort="xhigh"))
        self.assertEqual(self.arguments["reasoning"], {"effort": "xhigh"})
        self.assertNotIn("store", self.arguments)
        self.assertNotIn("include", self.arguments)

    def test_echec_du_fournisseur_remonte(self):
        client = self._client([NS(type="response.failed", response=NS(error=NS(code="server_error", message="boum")))])
        with self.assertRaises(RuntimeError):
            lire_flux(client.chat.completions.create(model="gpt-6-luna", messages=[]))


class Claude(unittest.TestCase):
    def test_outil_reflexion_signee_et_effort(self):
        from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock
        blocs = [
            ThinkingBlock(type="thinking", thinking="Il faut chercher", signature="sig123"),
            ToolUseBlock(type="tool_use", id="toolu_1", name="chercher", input={"q": "x"}),
        ]
        evenements = [
            NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking="Il faut chercher")),
            NS(type="content_block_delta", index=1, delta=NS(type="text_delta", text="Je cherche.")),
            NS(type="content_block_start", index=2, content_block=NS(type="tool_use", id="toolu_1", name="chercher")),
            NS(type="content_block_delta", index=2, delta=NS(type="input_json_delta", partial_json='{"q":')),
            NS(type="content_block_delta", index=2, delta=NS(type="input_json_delta", partial_json='"x"}')),
        ]
        final = NS(content=blocs, stop_reason="tool_use")

        class Contexte:
            def __enter__(self_inner):
                return NS(__iter__=None, get_final_message=lambda: final, evenements=evenements)

            def __exit__(self_inner, *a):
                return False

        class Flux:
            def __init__(self_inner):
                self_inner.evenements = evenements

            def __iter__(self_inner):
                return iter(self_inner.evenements)

            def get_final_message(self_inner):
                return final

        captured = {}

        class Contexte2:
            def __enter__(self_inner):
                return Flux()

            def __exit__(self_inner, *a):
                return False

        def stream(**arguments):
            captured.update(arguments)
            return Contexte2()

        client = ClientClaude("cle")
        client._client = NS(messages=NS(stream=stream))
        flux = client.chat.completions.create(
            model="claude-sonnet-5-5", messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}],
            tools=OUTILS, reasoning_effort="xhigh", max_completion_tokens=4096)
        texte, pensee, appels, fin = lire_flux(flux)
        self.assertEqual((texte, pensee, fin), ("Je cherche.", "Il faut chercher", "tool_calls"))
        self.assertEqual(appels, [{"id": "toolu_1", "name": "chercher", "arguments": '{"q":"x"}'}])
        self.assertEqual(captured["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(captured["extra_body"], {"output_config": {"effort": "xhigh"}})
        self.assertEqual(captured["system"], "S")
        self.assertGreater(captured["max_tokens"], 4096)
        self.assertEqual(captured["tools"][0]["input_schema"]["type"], "object")
        etat = client.etat_dernier_tour()
        self.assertEqual(etat["blocs"][0]["signature"], "sig123")

        systeme, converti = claude_messages(messages_apres_outil(appels[0], etat))
        self.assertEqual(systeme, "Consigne de base")
        self.assertEqual([m["role"] for m in converti], ["user", "assistant", "user"])
        self.assertEqual(converti[1]["content"][0]["type"], "thinking")
        self.assertEqual(converti[2]["content"][0]["type"], "tool_result")
        self.assertEqual(converti[2]["content"][0]["tool_use_id"], "toolu_1")

    def test_consigne_systeme_en_cours_de_route_apres_les_resultats(self):
        messages = messages_apres_outil({"id": "t1", "name": "chercher", "arguments": "{}"}, None)
        messages.append({"role": "system", "content": "Tu as répété"})
        _, converti = claude_messages(messages)
        dernier = converti[-1]["content"]
        self.assertEqual([b["type"] for b in dernier], ["tool_result", "text"])
        self.assertIn("Tu as répété", dernier[1]["text"])

    def test_sans_etat_les_appels_sont_reconstruits(self):
        _, converti = claude_messages(messages_apres_outil({"id": "t1", "name": "chercher", "arguments": '{"q":"z"}'}, None))
        self.assertEqual(converti[1]["content"], [{"type": "tool_use", "id": "t1", "name": "chercher", "input": {"q": "z"}}])


class Gemini(unittest.TestCase):
    def test_appel_d_outil_signature_et_niveau(self):
        from google.genai import types as gt
        reponses = [
            gt.GenerateContentResponse.model_validate({"candidates": [{"content": {"role": "model", "parts": [
                {"text": "Je réfléchis", "thought": True}]}}]}),
            gt.GenerateContentResponse.model_validate({"candidates": [{"finish_reason": "STOP", "content": {"role": "model", "parts": [
                {"function_call": {"id": "g1", "name": "chercher", "args": {"q": "x"}}, "thought_signature": "c2lnbmF0dXJl"}]}}]}),
        ]
        captured = {}

        def flux(**arguments):
            captured.update(arguments)
            return iter(reponses)

        client = ClientGemini("cle")
        client._client = NS(models=NS(generate_content_stream=flux))
        flux_morceaux = client.chat.completions.create(
            model="gemini-4-argon", messages=[{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}],
            tools=OUTILS, reasoning_effort="high")
        texte, pensee, appels, fin = lire_flux(flux_morceaux)
        self.assertEqual((pensee, fin), ("Je réfléchis", "tool_calls"))
        self.assertEqual(appels, [{"id": "g1", "name": "chercher", "arguments": '{"q": "x"}'}])
        configuration = captured["config"]
        self.assertEqual(configuration.thinking_config.thinking_level, gt.ThinkingLevel.HIGH)
        self.assertEqual(configuration.system_instruction, "S")
        self.assertEqual(configuration.tools[0].function_declarations[0].name, "chercher")

        etat = client.etat_dernier_tour()
        json.dumps(etat)  # doit voyager en JSON avec l'état de reprise
        systeme, contenus = gemini_messages(messages_apres_outil(appels[0], etat))
        self.assertEqual([c.role for c in contenus], ["user", "model", "user"])
        self.assertEqual(contenus[1].parts[1].function_call.id, "g1")
        self.assertEqual(contenus[1].parts[1].thought_signature, b"signature")
        reponse_outil = contenus[2].parts[0].function_response
        self.assertEqual((reponse_outil.id, reponse_outil.name), ("g1", "chercher"))

    def test_identifiant_genere_quand_gemini_n_en_donne_pas(self):
        from google.genai import types as gt
        reponse = gt.GenerateContentResponse.model_validate({"candidates": [{"content": {"role": "model", "parts": [
            {"function_call": {"name": "chercher", "args": {}}}]}}]})
        client = ClientGemini("cle")
        client._client = NS(models=NS(generate_content_stream=lambda **a: iter([reponse])))
        _, _, appels, _ = lire_flux(client.chat.completions.create(model="gemini-3.8-flash", messages=[], tools=OUTILS))
        self.assertTrue(appels[0]["id"])
        self.assertEqual(client.etat_dernier_tour()["parties"][0]["function_call"]["id"], appels[0]["id"])


if __name__ == "__main__":
    unittest.main()
