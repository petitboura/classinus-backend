"""
Joue la vraie boucle d'agent (core/boucle_agent.py:_agent_groq) avec un faux fournisseur, sans
reseau (21/10/2026) : le modele appelle demander_outils pour Railway. On verifie le minimum de
5 outils, l'ajout des outils qui fournissent les identifiants, et que le tour suivant les recoit.
"""

import json
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import efforts_modeles  # noqa: E402
from core.adaptateur_responses import ClientResponses

NS = types.SimpleNamespace


def _element(type_element, **champs):
    return NS(type=type_element, model_dump=lambda exclude_none=True: {"type": type_element, **champs}, **champs)


def _outil(nom, obligatoires=(), description=""):
    return {
        "type": "function",
        "function": {
            "name": nom,
            "description": description,
            "parameters": {"type": "object", "properties": {}, "required": list(obligatoires)},
        },
    }


CATALOGUE = [
    _outil("railway_list-projects", description="liste les projets"),
    _outil("railway_list-services", ["projectId"], "liste les services d'un projet"),
    _outil("railway_redeploy", ["environmentId", "projectId", "serviceId"], "redeploie un service"),
    _outil("railway_get-status", ["projectId"], "etat du deploiement"),
    _outil("railway_get-logs", ["projectId"], "journaux"),
    _outil("railway_list-variables", ["projectId", "serviceId"], "variables d'un service"),
    _outil("railway_restart-service", ["projectId", "serviceId"], "redemarre un service"),
    _outil("vercel_list_teams", description="equipes"),
    _outil("generer_image", description="creer une image"),
]


class DemanderOutilsDansLaBoucle(unittest.TestCase):
    def test_minimum_et_prerequis_arrivent_au_tour_suivant(self):
        appels_api = []
        arguments = json.dumps({"recherches": [{"besoin": "redeployer un service", "categorie": "railway"}]})
        tours = [
            [
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="demander_outils")),
                NS(type="response.function_call_arguments.delta", item_id="fc_1", delta=arguments),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_1", call_id="c1", name="demander_outils", arguments=arguments)),
            ],
            [NS(type="response.output_text.delta", delta="Fait."), NS(type="response.completed")],
        ]

        def creer(**kwargs):
            appels_api.append(kwargs)
            return iter(tours[len(appels_api) - 1])

        client = ClientResponses("cle", "openai")
        client._client = NS(responses=NS(create=creer))

        params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Redeploie"}]
        outils_depart = [_outil("demander_outils")]
        with patch.object(boucle_agent, "parametres_outils", return_value=params), \
                patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
                patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
                patch.object(boucle_agent, "plafond_tour", return_value=None):
            evenements = list(boucle_agent._agent_groq(
                client, messages, outils_depart, {}, modele="gpt-6-astra", reasoning_effort="none",
                catalogue_complet=CATALOGUE, table_routage_complet={o["function"]["name"]: {} for o in CATALOGUE},
            ))

        reponse_outil = [m for m in messages if m["role"] == "tool"][0]["content"]
        # La categorie railway compte 7 outils dans ce catalogue : le minimum de 5 est atteint, et les
        # outils qui fournissent projectId et serviceId sont bien la.
        self.assertIn("railway_redeploy", reponse_outil)
        self.assertIn("railway_list-projects", reponse_outil)
        self.assertIn("railway_list-services", reponse_outil)
        self.assertIn("appelle d'abord", reponse_outil)
        # Ni l'outil d'une autre categorie ni un outil sans rapport.
        self.assertNotIn("vercel_list_teams", reponse_outil)
        self.assertNotIn("generer_image", reponse_outil)
        self.assertNotIn("--", reponse_outil)

        detail = [e for e in evenements if e.get("type") == "outil_resultat" and e.get("nom_outil") == "demander_outils"][0]["resultat"]
        self.assertIn("railway_redeploy", detail)

        # Le tour suivant recoit ces outils dans sa liste.
        noms_tour_2 = {t.get("name") or (t.get("function") or {}).get("name") for t in appels_api[1].get("tools", [])}
        for nom in ("railway_redeploy", "railway_list-projects", "railway_list-services"):
            self.assertIn(nom, noms_tour_2)
        texte = "".join(e.get("texte", "") for e in evenements if e.get("type") == "reponse")
        self.assertEqual(texte, "Fait.")

    def test_besoin_sans_mot_commun_dans_une_categorie_donne_quand_meme_le_minimum(self):
        arguments = json.dumps({"recherches": [{"besoin": "zzz qqq", "categorie": "railway"}]})
        appels_api = []
        tours = [
            [
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="demander_outils")),
                NS(type="response.function_call_arguments.delta", item_id="fc_1", delta=arguments),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_1", call_id="c1", name="demander_outils", arguments=arguments)),
            ],
            [NS(type="response.output_text.delta", delta="Ok."), NS(type="response.completed")],
        ]

        def creer(**kwargs):
            appels_api.append(kwargs)
            return iter(tours[len(appels_api) - 1])

        client = ClientResponses("cle", "openai")
        client._client = NS(responses=NS(create=creer))
        params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "x"}]
        with patch.object(boucle_agent, "parametres_outils", return_value=params), \
                patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
                patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
                patch.object(boucle_agent, "plafond_tour", return_value=None):
            list(boucle_agent._agent_groq(
                client, messages, [_outil("demander_outils")], {}, modele="gpt-6-astra", reasoning_effort="none",
                catalogue_complet=CATALOGUE, table_routage_complet={},
            ))
        reponse_outil = [m for m in messages if m["role"] == "tool"][0]["content"]
        self.assertIn("Trouvé et ajouté", reponse_outil)
        self.assertNotIn("Aucun outil correspondant", reponse_outil)


if __name__ == "__main__":
    unittest.main()
