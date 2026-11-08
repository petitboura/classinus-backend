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

        # Cache de prompt (07/11/2026) : la liste d'outils du tour suivant est IDENTIQUE a celle du
        # premier appel (elle part en tete de la requete, la changer ferait tout relire au prix
        # plein). Les outils trouves arrivent par leur fiche, dans la reponse de demander_outils.
        noms_tour_1 = [t.get("name") or (t.get("function") or {}).get("name") for t in appels_api[0].get("tools", [])]
        noms_tour_2 = [t.get("name") or (t.get("function") or {}).get("name") for t in appels_api[1].get("tools", [])]
        self.assertEqual(noms_tour_1, noms_tour_2)
        self.assertNotIn("railway_redeploy", noms_tour_2)
        self.assertIn("Parametres :", reponse_outil)
        self.assertIn("appeler_outil", reponse_outil)
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
        self.assertIn("Trouvé :", reponse_outil)
        self.assertNotIn("Aucun outil correspondant", reponse_outil)


if __name__ == "__main__":
    unittest.main()


class AppelerOutilDansLaBoucle(unittest.TestCase):
    """Cache de prompt (07/11/2026) : le modele obtient un outil avec demander_outils puis l'appelle
    par appeler_outil, sans que la liste d'outils envoyee au fournisseur change d'un appel a l'autre."""

    def test_de_la_demande_a_l_execution(self):
        demande = json.dumps({"recherches": [{"besoin": "lister les projets", "categorie": "railway"}]})
        appel_wrapper = json.dumps({"nom": "railway_list-projects", "arguments": {"libelle": "Je liste les projets"}})
        tours = [
            [
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="demander_outils")),
                NS(type="response.function_call_arguments.delta", item_id="fc_1", delta=demande),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_1", call_id="c1", name="demander_outils", arguments=demande)),
            ],
            [
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_2", call_id="c2", name="appeler_outil")),
                NS(type="response.function_call_arguments.delta", item_id="fc_2", delta=appel_wrapper),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_2", call_id="c2", name="appeler_outil", arguments=appel_wrapper)),
            ],
            [NS(type="response.output_text.delta", delta="Voila."), NS(type="response.completed")],
        ]
        appels_api = []

        def creer(**kwargs):
            appels_api.append(kwargs)
            return iter(tours[len(appels_api) - 1])

        executes = []

        def faux_traiter_appels(appels, messages_agent, *args, **kwargs):
            for appel in appels:
                executes.append(appel)
                yield {"type": "outil_resultat", "nom_outil": appel["name"], "id_appel": appel["id"], "resultat": "ok"}
                messages_agent.append({"role": "tool", "tool_call_id": appel["id"], "content": "[projets]"})

        client = ClientResponses("cle", "openai")
        client._client = NS(responses=NS(create=creer))
        params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Liste mes projets"}]
        outils_depart = [_outil("demander_outils"), _outil("appeler_outil")]
        with patch.object(boucle_agent, "parametres_outils", return_value=params), \
                patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
                patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
                patch.object(boucle_agent, "plafond_tour", return_value=None), \
                patch.object(boucle_agent, "_traiter_appels", faux_traiter_appels):
            evenements = list(boucle_agent._agent_groq(
                client, messages, outils_depart, {}, modele="gpt-6-astra", reasoning_effort="none",
                catalogue_complet=CATALOGUE, table_routage_complet={o["function"]["name"]: {} for o in CATALOGUE},
            ))

        # 1. Les trois appels au fournisseur recoivent exactement la meme liste d'outils.
        listes = [[t.get("name") or (t.get("function") or {}).get("name") for t in a.get("tools", [])] for a in appels_api]
        self.assertEqual(len(listes), 3)
        self.assertEqual(listes[0], listes[1])
        self.assertEqual(listes[1], listes[2])
        self.assertNotIn("railway_list-projects", listes[2])

        # 2. Ce qui est execute est le VRAI outil, avec ses vrais arguments et l'identifiant du modele.
        self.assertEqual(len(executes), 1)
        self.assertEqual(executes[0]["name"], "railway_list-projects")
        self.assertEqual(executes[0]["id"], "c2")
        self.assertEqual(json.loads(executes[0]["arguments"]), {"libelle": "Je liste les projets"})

        # 3. Les evenements (cartes du chat, journal) portent le vrai nom, jamais appeler_outil.
        noms_evenements = {e.get("nom_outil") for e in evenements if e.get("type") == "outil_resultat"}
        self.assertIn("railway_list-projects", noms_evenements)
        self.assertNotIn("appeler_outil", noms_evenements)

        # 4. La conversation garde l'appel tel que le modele l'a fait, avec un resultat pour chaque id.
        appeles = [c["function"]["name"] for m in messages if m.get("tool_calls") for c in m["tool_calls"]]
        self.assertEqual(appeles, ["demander_outils", "appeler_outil"])
        resultats = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
        self.assertEqual(resultats, {"c1", "c2"})

    def test_appel_refuse_renvoie_la_raison_au_modele(self):
        appel_wrapper = json.dumps({"nom": "n_importe_quoi", "arguments": {}})
        tours = [
            [
                NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="appeler_outil")),
                NS(type="response.function_call_arguments.delta", item_id="fc_1", delta=appel_wrapper),
                NS(type="response.output_item.done", item=_element(
                    "function_call", id="fc_1", call_id="c1", name="appeler_outil", arguments=appel_wrapper)),
            ],
            [NS(type="response.output_text.delta", delta="Ok."), NS(type="response.completed")],
        ]
        appels_api = []

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
                client, messages, [_outil("demander_outils"), _outil("appeler_outil")], {}, modele="gpt-6-astra",
                reasoning_effort="none", catalogue_complet=CATALOGUE, table_routage_complet={},
            ))
        retour = [m for m in messages if m["role"] == "tool"]
        self.assertEqual(len(retour), 1)
        self.assertEqual(retour[0]["tool_call_id"], "c1")
        self.assertIn("Outil inconnu", retour[0]["content"])
        self.assertEqual(len(appels_api), 2)
