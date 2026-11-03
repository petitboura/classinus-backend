"""
Reste d'outils par categorie et consignes de combinaison (03/11/2026, demande Bourama).
Sans reseau : les calculs seuls, puis la vraie boucle d'agent avec un faux fournisseur.
"""

import json
import os
import re
import sys
import types
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import efforts_modeles  # noqa: E402
import consignes_outils  # noqa: E402
import registre_outils  # noqa: E402
from core.adaptateur_responses import ClientResponses  # noqa: E402

NS = types.SimpleNamespace


def _outil(nom, description=""):
    return {
        "type": "function",
        "function": {"name": nom, "description": description, "parameters": {"type": "object", "properties": {}, "required": []}},
    }


def _element(type_element, **champs):
    return NS(type=type_element, model_dump=lambda exclude_none=True: {"type": type_element, **champs}, **champs)


# 20 outils Notion (par prefixe), 1 GitHub, 1 execution de code, 1 sans rapport.
NOTION = [_outil(f"notion-outil-{i}", f"action notion numero {i}") for i in range(20)]
CATALOGUE = NOTION + [
    _outil("gerer_depot_github", "depots github issues pull requests"),
    _outil("gerer_execution_code", "lancer du code et des commandes"),
    _outil("generer_image", "creer une image"),
]


class CalculsSeuls(unittest.TestCase):
    def test_nombre_restant_exclut_ce_qui_est_deja_en_main(self):
        en_main = {f"notion-outil-{i}" for i in range(5)}
        self.assertEqual(consignes_outils.nombre_outils_restants("notion", CATALOGUE, en_main), 15)

    def test_categorie_vide_ou_inconnue_donne_zero(self):
        self.assertEqual(consignes_outils.nombre_outils_restants(None, CATALOGUE, set()), 0)
        self.assertEqual(consignes_outils.nombre_outils_restants("inconnue", CATALOGUE, set()), 0)

    def test_texte_restes_vide_si_rien_ne_reste_et_dernier_nombre_garde(self):
        self.assertEqual(consignes_outils.texte_outils_restants([("notion", 0)]), "")
        texte = consignes_outils.texte_outils_restants([("notion", 9), ("notion", 4)])
        self.assertIn("Il reste 4 outils dans la catégorie notion", texte)
        self.assertNotIn("9", texte)
        self.assertIn("jamais deux fois le même outil", texte)

    def test_singulier(self):
        self.assertIn("Il reste 1 outil dans", consignes_outils.texte_outils_restants([("notion", 1)]))

    def test_consigne_github_demande_aussi_le_code_si_absent(self):
        github = [o for o in CATALOGUE if o["function"]["name"] == "gerer_depot_github"]
        texte = consignes_outils.consignes_familles(github, github)
        self.assertIn("mes_depots", texte)
        self.assertIn("catégorie execution_code", texte)

    def test_consigne_sans_rappel_quand_le_partenaire_est_deja_en_main(self):
        github = [o for o in CATALOGUE if o["function"]["name"] == "gerer_depot_github"]
        code = [o for o in CATALOGUE if o["function"]["name"] == "gerer_execution_code"]
        texte = consignes_outils.consignes_familles(github, github + code)
        self.assertIn("mes_depots", texte)
        self.assertNotIn("demande-les aussi", texte)

    def test_consigne_dans_l_autre_sens(self):
        code = [o for o in CATALOGUE if o["function"]["name"] == "gerer_execution_code"]
        texte = consignes_outils.consignes_familles(code, code)
        self.assertIn("clone-le ici avec git", texte)
        self.assertIn("catégorie github", texte)

    def test_categorie_hors_famille_ne_donne_aucune_consigne(self):
        self.assertEqual(consignes_outils.consignes_familles(NOTION[:3], NOTION[:3]), "")
        self.assertEqual(consignes_outils.consignes_familles([], []), "")

    def test_les_familles_ne_citent_que_des_categories_qui_existent(self):
        connues = set(registre_outils.NOMS_CATEGORIES_OUTILS)
        for famille in registre_outils.FAMILLES_OUTILS.values():
            for categorie, regle in famille.items():
                self.assertIn(categorie, connues)
                for partenaire in regle["avec"]:
                    self.assertIn(partenaire, connues)
                    self.assertNotEqual(partenaire, categorie)

    def test_aucun_double_tiret_dans_les_textes(self):
        for famille in registre_outils.FAMILLES_OUTILS.values():
            for regle in famille.values():
                self.assertNotIn("--", regle["consigne"])
        self.assertNotIn("--", consignes_outils.texte_outils_restants([("notion", 3)]))


def _jouer_demande(recherches, outils_depart=None, messages_suite=None):
    """Joue un tour : le modele appelle demander_outils avec `recherches`. Renvoie la reponse de l'outil et les outils du tour suivant."""
    arguments = json.dumps({"recherches": recherches})
    appels_api = []
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
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "x"}]
    with patch.object(boucle_agent, "parametres_outils", return_value=params), \
            patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
            patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
            patch.object(boucle_agent, "plafond_tour", return_value=None):
        list(boucle_agent._agent_groq(
            client, messages, outils_depart or [_outil("demander_outils")], {}, modele="gpt-6-astra", reasoning_effort="none",
            catalogue_complet=CATALOGUE, table_routage_complet={o["function"]["name"]: {} for o in CATALOGUE},
        ))
    reponse = [m for m in messages if m["role"] == "tool"][0]["content"]
    noms_tour_2 = {t.get("name") or (t.get("function") or {}).get("name") for t in appels_api[1].get("tools", [])}
    return reponse, noms_tour_2


class DansLaBoucle(unittest.TestCase):
    def test_la_reponse_dit_combien_il_reste(self):
        reponse, noms = _jouer_demande([{"besoin": "lire une page", "categorie": "notion"}])
        donnes = [n for n in noms if n.startswith("notion-")]
        reste = 20 - len(donnes)
        self.assertGreater(reste, 0)
        self.assertIn(f"Il reste {reste} outils dans la catégorie notion", reponse)

    def test_demande_suivante_ne_redonne_pas_les_memes_outils(self):
        premiere, noms_1 = _jouer_demande([{"besoin": "lire une page", "categorie": "notion"}])
        deja = [o for o in NOTION if o["function"]["name"] in noms_1]
        seconde, noms_2 = _jouer_demande(
            [{"besoin": "lire une page", "categorie": "notion"}],
            outils_depart=[_outil("demander_outils")] + deja,
        )
        nouveaux = {n for n in noms_2 if n.startswith("notion-")} - {o["function"]["name"] for o in deja}
        self.assertGreater(len(nouveaux), 0)
        for nom in nouveaux:
            self.assertNotIn(nom, premiere)

    def test_github_donne_la_consigne_et_rappelle_l_execution_de_code(self):
        reponse, _ = _jouer_demande([{"besoin": "cloner un depot public", "categorie": "github"}])
        self.assertIn("gerer_depot_github", reponse)
        self.assertIn("mes_depots", reponse)
        self.assertIn("catégorie execution_code", reponse)
        self.assertNotIn("--", reponse)

    def test_aucune_reponse_ne_contient_de_double_tiret(self):
        reponse, _ = _jouer_demande([{"besoin": "lire une page", "categorie": "notion"}])
        self.assertIsNone(re.search(r"--", reponse))


if __name__ == "__main__":
    unittest.main()
