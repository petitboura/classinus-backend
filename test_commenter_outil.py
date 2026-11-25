"""
Outil interne commenter (25/11/2026, demande de Bourama) : une courte note de l'IA entre deux appels
d'outils, montree comme une ligne a point dans la timeline du chat.

Joue la vraie boucle d'agent (core/boucle_agent.py:_agent_groq) avec un faux fournisseur, sans reseau.
On verifie : l'evenement "commentaire" (et jamais de statut ni d'outil_resultat), la reponse donnee
au modele, le plafond par tour, la persistance dans meta["segments"], le nettoyage du texte et le
fait que la definition de l'outil est fixe (cache de prompt).
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
from core.adaptateur_responses import ClientResponses  # noqa: E402
from libelles_activite_ia import nettoyer_commentaire, outils_avec_libelle  # noqa: E402
from routage_outils import NOM_OUTIL_COMMENTER, _outil_commenter, _separer_appels_commenter  # noqa: E402

NS = types.SimpleNamespace


def _element(type_element, **champs):
    return NS(type=type_element, model_dump=lambda exclude_none=True: {"type": type_element, **champs}, **champs)


def _appel_commenter(numero, texte):
    arguments = json.dumps({"texte": texte})
    identifiant = f"fc_{numero}"
    return [
        NS(type="response.output_item.added", item=NS(type="function_call", id=identifiant, call_id=f"c{numero}", name="commenter")),
        NS(type="response.function_call_arguments.delta", item_id=identifiant, delta=arguments),
        NS(type="response.output_item.done", item=_element(
            "function_call", id=identifiant, call_id=f"c{numero}", name="commenter", arguments=arguments)),
    ]


def _jouer(tours, outils=None):
    appels_api = []

    def creer(**kwargs):
        appels_api.append(kwargs)
        return iter(tours[len(appels_api) - 1])

    client = ClientResponses("cle", "openai")
    client._client = NS(responses=NS(create=creer))
    params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 40, "tolerance_repetition": 3}
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Cherche"}]
    with patch.object(boucle_agent, "parametres_outils", return_value=params), \
            patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
            patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
            patch.object(boucle_agent, "plafond_tour", return_value=None):
        evenements = list(boucle_agent._agent_groq(
            client, messages, outils if outils is not None else [_outil_commenter()], {},
            modele="gpt-6-astra", reasoning_effort="none",
        ))
    return evenements, messages, appels_api


def _fin(texte="Fait."):
    return [NS(type="response.output_text.delta", delta=texte), NS(type="response.completed")]


class CommenterDansLaBoucle(unittest.TestCase):
    def test_la_note_devient_un_evenement_commentaire_et_rien_d_autre(self):
        evenements, messages, _ = _jouer([_appel_commenter(1, "J'ai trouve ton cours, je le compare."), _fin()])

        commentaires = [e for e in evenements if e.get("type") == "commentaire"]
        self.assertEqual(len(commentaires), 1)
        self.assertEqual(commentaires[0]["texte"], "J'ai trouve ton cours, je le compare.")
        self.assertEqual(commentaires[0]["id_appel"], "c1")
        # Ce n'est pas un outil : aucune ligne d'outil, aucun statut.
        self.assertEqual([e for e in evenements if e.get("type") in ("statut", "statut_termine", "outil_resultat")], [])
        # Le modele recoit une reponse pour son appel, puis continue et repond.
        reponses = [m for m in messages if m["role"] == "tool"]
        self.assertEqual(len(reponses), 1)
        self.assertEqual(reponses[0]["tool_call_id"], "c1")
        self.assertIn("Continue ton travail", reponses[0]["content"])
        self.assertEqual("".join(e.get("texte", "") for e in evenements if e.get("type") == "reponse"), "Fait.")

    def test_une_note_illisible_n_est_pas_montree(self):
        evenements, messages, _ = _jouer([_appel_commenter(1, "  "), _fin()])
        self.assertEqual([e for e in evenements if e.get("type") == "commentaire"], [])
        self.assertIn("ignoree", [m for m in messages if m["role"] == "tool"][0]["content"])

    def test_plafond_de_notes_par_tour(self):
        plafond = boucle_agent.MAX_COMMENTAIRES_PAR_TOUR
        tours = [_appel_commenter(i, f"Note numero {i} pour l'utilisateur") for i in range(1, plafond + 3)] + [_fin()]
        evenements, messages, _ = _jouer(tours)
        self.assertEqual(len([e for e in evenements if e.get("type") == "commentaire"]), plafond)
        dernieres = [m["content"] for m in messages if m["role"] == "tool"][-2:]
        self.assertTrue(all("Trop de notes" in c for c in dernieres))

    def test_la_note_est_enregistree_dans_l_ordre_pour_la_reouverture(self):
        evenements, _, _ = _jouer([_appel_commenter(1, "Je compare les deux versions."), _fin("Voila.")])
        meta = {}
        accumulateur = []
        list(boucle_agent._capturer_reponse(iter(evenements), accumulateur, meta))
        self.assertEqual(
            meta["segments"],
            [{"type": "commentaire", "texte": "Je compare les deux versions."}, {"type": "texte", "texte": "Voila."}],
        )
        # Ce n'est pas un outil : rien a reinjecter au modele au tour suivant.
        self.assertNotIn("outils", meta)


class DefinitionEtNettoyage(unittest.TestCase):
    def test_la_definition_est_fixe_et_sans_champ_de_libelle(self):
        self.assertEqual(_outil_commenter(), _outil_commenter())
        envoye = outils_avec_libelle([_outil_commenter()])[0]
        self.assertEqual(list(envoye["function"]["parameters"]["properties"]), ["texte"])
        self.assertEqual(envoye["function"]["name"], NOM_OUTIL_COMMENTER)
        # Texte lu par le modele : jamais de tiret double.
        self.assertNotIn("--", json.dumps(envoye))

    def test_separation_des_appels(self):
        appels = [
            {"id": "a", "name": "commenter", "arguments": json.dumps({"texte": "Je lis le fichier"})},
            {"id": "b", "name": "lire_fichier", "arguments": "{}"},
            {"id": "c", "name": "commenter", "arguments": "pas du json"},
        ]
        normaux, commentaires = _separer_appels_commenter(appels)
        self.assertEqual([a["id"] for a in normaux], ["b"])
        self.assertEqual(commentaires, [{"id": "a", "texte": "Je lis le fichier"}, {"id": "c", "texte": None}])

    def test_nettoyage(self):
        self.assertEqual(nettoyer_commentaire("J'ai trouve 3 fichiers -- je les compare."), "J'ai trouve 3 fichiers, je les compare.")
        self.assertEqual(nettoyer_commentaire("Ligne un\nligne `deux` <b>trois</b>"), "Ligne un ligne deux btrois/b")
        self.assertIsNone(nettoyer_commentaire(None))
        self.assertIsNone(nettoyer_commentaire("12"))
        self.assertIsNone(nettoyer_commentaire("  "))
        long = nettoyer_commentaire("mot " * 200)
        self.assertLessEqual(len(long), 240)
        self.assertNotIn("--", long)


if __name__ == "__main__":
    unittest.main()
