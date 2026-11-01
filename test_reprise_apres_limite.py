"""
Reprise apres une limite d'actions ou une repetition (core/boucle_agent.py, core/main.py:chat), sans reseau.

Probleme corrige le 01/11/2026 : l'etat de reprise se terminait par la consigne systeme "conclus et dis que
tu as atteint ta limite". Rejouee par le bouton Continuer, elle faisait redire la limite au modele au lieu de
poursuivre. On verifie que cette consigne est retiree, remplacee par une consigne de reprise quand l'utilisateur
n'a rien tape, et que les reprises apres un arret ou une erreur ne changent pas.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import main  # noqa: E402


def _appel(identifiant):
    return {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": identifiant, "type": "function", "function": {"name": "outil", "arguments": "{}"}}],
    }


def _resultat(identifiant):
    return {"role": "tool", "tool_call_id": identifiant, "content": "ok"}


BASE = [{"role": "system", "content": "consigne generale"}, {"role": "user", "content": "question"}]
TRAVAIL = BASE + [_appel("a"), _resultat("a")]

# Le texte exact ecrit par _agent_groq (plafond atteint) et par la detection de repetition.
CONSIGNE_LIMITE = {
    "role": "system",
    "content": (
        "Tu as atteint la limite de 50 actions pour cette réponse. Rédige maintenant ta réponse finale à partir "
        "de ce que tu as déjà obtenu, en indiquant clairement à l'utilisateur que tu as atteint cette limite et "
        "qu'il peut te demander de continuer pour poursuivre le travail."
    ),
}
CONSIGNE_REPETITION = {
    "role": "system",
    "content": (
        "Tu as répété 3 fois d'affilée exactement la même action (Lire un fichier) sans y arriver. Rédige "
        "maintenant ta réponse en expliquant clairement ce blocage à l'utilisateur, avec ce que tu as quand même "
        "réussi à faire jusque-là. Ne retente pas cette même action telle quelle."
    ),
}


class RetirerConsigneDeFin(unittest.TestCase):
    def test_retire_la_consigne_de_limite(self):
        messages, genre = boucle_agent.retirer_consigne_de_fin(TRAVAIL + [CONSIGNE_LIMITE])
        self.assertEqual(messages, TRAVAIL)
        self.assertEqual(genre, "limite")

    def test_retire_la_consigne_de_repetition(self):
        messages, genre = boucle_agent.retirer_consigne_de_fin(TRAVAIL + [CONSIGNE_REPETITION])
        self.assertEqual(messages, TRAVAIL)
        self.assertEqual(genre, "repetition")

    def test_sans_consigne_de_fin_rien_ne_change(self):
        messages, genre = boucle_agent.retirer_consigne_de_fin(TRAVAIL)
        self.assertEqual(messages, TRAVAIL)
        self.assertIsNone(genre)

    def test_la_consigne_generale_du_debut_n_est_jamais_retiree(self):
        messages, genre = boucle_agent.retirer_consigne_de_fin(BASE[:1])
        self.assertEqual(messages, BASE[:1])
        self.assertIsNone(genre)

    def test_un_message_systeme_ordinaire_a_la_fin_est_garde(self):
        autre = {"role": "system", "content": "Une autre consigne"}
        messages, genre = boucle_agent.retirer_consigne_de_fin(TRAVAIL + [autre])
        self.assertEqual(messages, TRAVAIL + [autre])
        self.assertIsNone(genre)

    def test_la_liste_d_origine_n_est_pas_modifiee(self):
        origine = TRAVAIL + [CONSIGNE_LIMITE]
        boucle_agent.retirer_consigne_de_fin(origine)
        self.assertEqual(origine, TRAVAIL + [CONSIGNE_LIMITE])

    def test_les_textes_ecrits_par_la_boucle_commencent_par_les_debuts_connus(self):
        self.assertTrue(CONSIGNE_LIMITE["content"].startswith(boucle_agent.DEBUT_CONSIGNE_LIMITE))
        self.assertTrue(CONSIGNE_REPETITION["content"].startswith(boucle_agent.DEBUT_CONSIGNE_REPETITION))

    def test_consigne_de_reprise_selon_le_genre(self):
        self.assertIn("nouveau budget", boucle_agent.consigne_de_reprise("limite")["content"])
        self.assertIn("réessayer", boucle_agent.consigne_de_reprise("repetition")["content"])
        self.assertIsNone(boucle_agent.consigne_de_reprise(None))


class ChatRepriseApresLimite(unittest.TestCase):
    """Le vrai chat(), reprise par le bouton Continuer ou Reessayer : ce que le modele recoit."""

    def _jouer(self, messages_agent, message_utilisateur=None):
        recus = []

        def capte(client, messages, *args, **kwargs):
            recus.append(list(messages))
            yield {"type": "reponse", "texte": "suite"}

        etat = {"messages_agent": messages_agent, "outils_mcp": [], "table_routage": {}, "modele": "m", "agent_nom": "A"}
        reprise = {"etat_reprise": etat, "type": "continuer_agent", "message_utilisateur": message_utilisateur}
        with patch.object(main, "_agent_groq", capte), patch.object(main, "_client_pour_reprise", lambda m: None), \
                patch.object(main, "_catalogue_pour_demander_outils", lambda *a, **k: ([], {})):
            list(main.chat(reprise=reprise))
        self.assertEqual(len(recus), 1)
        return recus[0]

    def _aucune_consigne_de_fin(self, messages):
        for m in messages:
            contenu = m.get("content")
            if m.get("role") == "system" and isinstance(contenu, str):
                self.assertFalse(contenu.startswith(boucle_agent.DEBUT_CONSIGNE_LIMITE))
                self.assertFalse(contenu.startswith(boucle_agent.DEBUT_CONSIGNE_REPETITION))

    def test_continuer_apres_la_limite_ne_rejoue_pas_la_consigne_de_fin(self):
        messages = self._jouer(TRAVAIL + [CONSIGNE_LIMITE])
        self._aucune_consigne_de_fin(messages)
        self.assertEqual(messages[:-1], TRAVAIL)
        self.assertEqual(messages[-1], boucle_agent.consigne_de_reprise("limite"))

    def test_reessayer_apres_une_repetition_ne_rejoue_pas_la_consigne_de_fin(self):
        messages = self._jouer(TRAVAIL + [CONSIGNE_REPETITION])
        self._aucune_consigne_de_fin(messages)
        self.assertEqual(messages[:-1], TRAVAIL)
        self.assertEqual(messages[-1], boucle_agent.consigne_de_reprise("repetition"))

    def test_message_tape_par_l_utilisateur_remplace_la_consigne_de_reprise(self):
        messages = self._jouer(TRAVAIL + [CONSIGNE_LIMITE], message_utilisateur="J'arrête là")
        self._aucune_consigne_de_fin(messages)
        self.assertEqual(messages[:-1], TRAVAIL)
        self.assertEqual(messages[-1], {"role": "user", "content": "J'arrête là"})

    def test_reprise_apres_un_arret_ou_une_erreur_ne_change_pas(self):
        messages = self._jouer(list(TRAVAIL))
        self.assertEqual(messages, TRAVAIL)


if __name__ == "__main__":
    unittest.main()
