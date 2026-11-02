"""
Correction du 01/11/2026 (demande de Bourama), sans reseau : un passage du modele sans texte ni
appel d'outil ne se termine plus en silence quand l'appelant le demande : erreur typee "vide", avec
l'etat de reprise si des outils avaient deja tourne (19 tours termines sans aucune reponse le 01/11).
Le delai long de Muse Spark Open est traite dans core/adaptateur_baseten.py.
"""

import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import erreur_tour  # noqa: E402

NS = types.SimpleNamespace

PARAMS = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}


def _morceau(raisonnement=None, contenu=None, fin=None):
    delta = NS(content=contenu, tool_calls=None, reasoning=raisonnement, reasoning_content=None)
    return NS(choices=[NS(delta=delta, finish_reason=fin)], usage=None)


class FauxClient:
    """Client compatible OpenAI dont le flux ne contient que de la reflexion, puis la fin."""

    def __init__(self, morceaux):
        self.morceaux = morceaux
        self.appels = []
        self.chat = NS(completions=NS(create=self._creer))

    def _creer(self, **arguments):
        self.appels.append(arguments)
        return iter(self.morceaux)


def _jouer(client, modele, **options):
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Question"}]
    with patch.object(boucle_agent, "parametres_outils", return_value=PARAMS), \
            patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
            patch.object(boucle_agent, "plafond_tour", return_value=None):
        return messages, list(boucle_agent._agent_groq(client, messages, None, {}, modele=modele, **options))


class ReponseVide(unittest.TestCase):
    def _client_reflexion_seule(self):
        return FauxClient([_morceau(raisonnement="Je réfléchis à la question."), _morceau(fin="stop")])

    def test_sans_option_la_boucle_s_arrete_comme_avant(self):
        _, evenements = _jouer(self._client_reflexion_seule(), "openai/gpt-oss-120b")
        self.assertFalse([e for e in evenements if e.get("type") == "reponse"])

    def test_avec_l_option_le_passage_vide_leve_l_erreur(self):
        with self.assertRaises(boucle_agent.ReponseVideErreur):
            _jouer(self._client_reflexion_seule(), "muse-spark-open", erreur_si_vide=True)

    def test_un_passage_avec_texte_ne_leve_rien(self):
        client = FauxClient([_morceau(contenu="Voilà.", fin="stop")])
        _, evenements = _jouer(client, "muse-spark-open", erreur_si_vide=True)
        texte = "".join(e.get("texte", "") for e in evenements if e.get("type") == "reponse")
        self.assertEqual(texte, "Voilà.")


class ErreurTypeeVide(unittest.TestCase):
    def test_code_vide(self):
        self.assertEqual(erreur_tour.classer_erreur(boucle_agent.ReponseVideErreur("x")), "vide")

    def test_sans_outil_deja_execute_pas_d_etat_de_reprise(self):
        base = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
        evenement = erreur_tour.evenement_echec(
            boucle_agent.ReponseVideErreur("x"), "fr", True,
            messages_agent=list(base), nb_messages_depart=len(base), outils_mcp=[], table_routage={},
            modele="muse-spark-open",
        )
        self.assertEqual(evenement["type"], "erreur_tour")
        self.assertEqual(evenement["code"], "vide")
        self.assertIsNone(evenement["etat_reprise"])

    def test_avec_outil_deja_execute_l_etat_de_reprise_est_joint(self):
        base = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
        messages = base + [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "outil", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "résultat obtenu"},
        ]
        evenement = erreur_tour.evenement_echec(
            boucle_agent.ReponseVideErreur("x"), "fr", True,
            messages_agent=messages, nb_messages_depart=len(base), outils_mcp=[], table_routage={},
            modele="muse-spark-open",
        )
        self.assertEqual(evenement["code"], "vide")
        self.assertIsNotNone(evenement["etat_reprise"])

    def test_client_sans_erreurs_typees_recoit_la_phrase_d_excuse(self):
        evenement = erreur_tour.evenement_echec(boucle_agent.ReponseVideErreur("x"), "fr", False)
        self.assertEqual(evenement["type"], "reponse")
        self.assertTrue(evenement["texte"])


if __name__ == "__main__":
    unittest.main()
