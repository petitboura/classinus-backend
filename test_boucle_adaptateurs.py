"""
Joue la vraie boucle d'agent (core/boucle_agent.py:_agent_groq) avec un faux fournisseur
Responses, sans réseau (20/10/2026) : un premier tour appelle un outil, le second doit recevoir
l'état du fournisseur rangé dans le message assistant, puis répondre en texte.
"""

import os
import types
import unittest
from unittest.mock import patch

# La boucle d'agent crée ses clients Supabase à l'import : de fausses valeurs suffisent ici, aucun
# appel réseau n'est fait.
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import efforts_modeles  # noqa: E402
from core.adaptateur_responses import ClientResponses

NS = types.SimpleNamespace


def _element(type_element, **champs):
    return NS(type=type_element, model_dump=lambda exclude_none=True: {"type": type_element, **champs}, **champs)


class BoucleAvecAdaptateur(unittest.TestCase):
    def test_deux_tours_avec_outil(self):
        appels_api = []
        tours = [
            [
                NS(type="response.output_item.done", item=_element("reasoning", id="rs_1", encrypted_content="enc")),
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="chercher")),
                NS(type="response.function_call_arguments.delta", item_id="fc_1", delta="{}"),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_1", call_id="c1", name="chercher", arguments="{}")),
            ],
            [NS(type="response.output_text.delta", delta="Voilà la réponse."), NS(type="response.completed")],
        ]

        def creer(**arguments):
            appels_api.append(arguments)
            return iter(tours[len(appels_api) - 1])

        client = ClientResponses("cle", "openai")
        client._client = NS(responses=NS(create=creer))

        def faux_traiter_appels(appels, messages_agent, table_routage, compteur, arret=None):
            for appel in appels:
                messages_agent.append({"role": "tool", "tool_call_id": appel["id"], "content": "ok"})
            return iter(())

        params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Cherche"}]
        outils = [{"type": "function", "function": {"name": "chercher", "description": "", "parameters": {"type": "object"}}}]
        with patch.object(boucle_agent, "parametres_outils", return_value=params), \
                patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
                patch.object(boucle_agent, "_traiter_appels", faux_traiter_appels), \
                patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
                patch.object(boucle_agent, "plafond_tour", return_value=None):
            evenements = list(boucle_agent._agent_groq(
                client, messages, outils, {}, modele="gpt-6-astra", reasoning_effort="none",
            ))

        texte = "".join(e.get("texte", "") for e in evenements if e.get("type") == "reponse")
        self.assertEqual(texte, "Voilà la réponse.")
        self.assertEqual(len(appels_api), 2)
        # L'effort refusé par ce modèle ("none" n'existe pas pour Astra) est remplacé par le défaut.
        self.assertEqual(appels_api[0]["reasoning"]["effort"], "low")
        assistant = [m for m in messages if m["role"] == "assistant"][0]
        self.assertEqual([e["type"] for e in assistant["fournisseur_etat"]["elements"]], ["reasoning", "function_call"])
        types_envoyes = [e.get("type") or e["role"] for e in appels_api[1]["input"]]
        self.assertEqual(types_envoyes, ["user", "reasoning", "function_call", "function_call_output"])


if __name__ == "__main__":
    unittest.main()
