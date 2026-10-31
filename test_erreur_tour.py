"""
Erreur en plein tour (core/erreur_tour.py, core/main.py:chat, api/chat.py), sans reseau.

On verifie le code d'erreur, le nettoyage de l'etat de reprise, l'ancien comportement pour les
clients qui ne demandent pas les erreurs typees, et que la reprise envoyee par le chat est
acceptee par l'API (elle etait refusee faute du champ approuve).
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import erreur_tour  # noqa: E402
import main  # noqa: E402
from core.arret_tour import ArretTour  # noqa: E402


class ErreurFournisseur(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _appel(identifiant):
    return {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": identifiant, "type": "function", "function": {"name": "outil", "arguments": "{}"}}],
    }


def _resultat(identifiant):
    return {"role": "tool", "tool_call_id": identifiant, "content": "ok"}


BASE = [{"role": "system", "content": "s"}, {"role": "user", "content": "question"}]


class ClasserErreur(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(erreur_tour.classer_erreur(ErreurFournisseur("x", 429)), "forte_demande")
        self.assertEqual(erreur_tour.classer_erreur(ErreurFournisseur("Rate limit reached")), "forte_demande")
        self.assertEqual(erreur_tour.classer_erreur(ErreurFournisseur("Request timeout")), "delai")
        self.assertEqual(erreur_tour.classer_erreur(ErreurFournisseur("boom", 500)), "serveur")
        self.assertEqual(erreur_tour.classer_erreur(None), "serveur")


class MessagesReprenables(unittest.TestCase):
    def test_garde_un_etat_complet(self):
        messages = BASE + [_appel("a"), _resultat("a")]
        self.assertEqual(erreur_tour.messages_reprenables(messages), messages)

    def test_retire_un_appel_sans_reponse(self):
        complet = BASE + [_appel("a"), _resultat("a")]
        self.assertEqual(erreur_tour.messages_reprenables(complet + [_appel("b")]), complet)

    def test_retire_un_lot_a_moitie_repondu(self):
        lot = {"role": "assistant", "content": None, "tool_calls": _appel("b")["tool_calls"] + _appel("c")["tool_calls"]}
        complet = BASE + [_appel("a"), _resultat("a")]
        self.assertEqual(erreur_tour.messages_reprenables(complet + [lot, _resultat("b")]), complet)


class EvenementEchec(unittest.TestCase):
    def test_ancien_comportement_sans_erreurs_typees(self):
        fr = erreur_tour.evenement_echec(Exception("x"), "fr", False)
        self.assertEqual(fr["type"], "reponse")
        self.assertIn("réessayer", fr["texte"])
        en = erreur_tour.evenement_echec(Exception("x"), "en", False)
        self.assertEqual(en, {"type": "reponse", "texte": "Something went wrong. Please try again shortly."})
        self.assertIsNone(erreur_tour.evenement_echec(Exception("x"), "fr", False, avec_texte=False))

    def test_sans_outil_pas_d_etat(self):
        evenement = erreur_tour.evenement_echec(
            ErreurFournisseur("x", 429), "fr", True, messages_agent=list(BASE), nb_messages_depart=len(BASE), outils_mcp=[], table_routage={},
        )
        self.assertEqual(evenement, {"type": "erreur_tour", "code": "forte_demande", "etat_reprise": None})

    def test_avec_outil_etat_de_reprise_nettoye(self):
        messages = BASE + [_appel("a"), _resultat("a"), _appel("b")]
        evenement = erreur_tour.evenement_echec(
            Exception("boom"), "fr", True, messages_agent=messages, nb_messages_depart=len(BASE),
            outils_mcp=[{"function": {"name": "outil"}}], table_routage={"outil": "x"}, modele="m", reasoning_effort="low", agent_nom="A",
        )
        etat = evenement["etat_reprise"]
        self.assertEqual(evenement["code"], "serveur")
        self.assertEqual(etat["messages_agent"], BASE + [_appel("a"), _resultat("a")])
        self.assertEqual((etat["modele"], etat["agent_nom"], etat["table_routage"]), ("m", "A", {"outil": "x"}))

    def test_outils_de_l_historique_ne_comptent_pas(self):
        messages = BASE + [_resultat("ancien")]
        evenement = erreur_tour.evenement_echec(
            Exception("x"), "fr", True, messages_agent=messages, nb_messages_depart=len(messages), outils_mcp=[], table_routage={},
        )
        self.assertIsNone(evenement["etat_reprise"])


class ChatReprise(unittest.TestCase):
    """Le vrai chat(), reprise apres un tour arrete : l'erreur du modele devient un evenement."""

    ETAT = {"messages_agent": BASE + [_appel("a"), _resultat("a")], "outils_mcp": [], "table_routage": {}, "modele": "m", "agent_nom": "A"}

    def _jouer(self, erreurs_typees):
        def echoue(*args, **kwargs):
            raise ErreurFournisseur("Too many requests", 429)
            yield  # generateur

        reprise = {"etat_reprise": self.ETAT, "type": "continuer_agent", "message_utilisateur": None}
        with patch.object(main, "_agent_groq", echoue), patch.object(main, "_client_pour_reprise", lambda m: None), \
                patch.object(main, "_catalogue_pour_demander_outils", lambda *a, **k: ([], {})):
            return list(main.chat(reprise=reprise, erreurs_typees=erreurs_typees))

    def test_client_ordinaire_garde_la_phrase(self):
        evenements = self._jouer(False)
        self.assertEqual([e["type"] for e in evenements], ["reponse"])

    def test_chat_du_site_recoit_le_code_et_l_etat(self):
        evenements = self._jouer(True)
        self.assertEqual(len(evenements), 1)
        self.assertEqual(evenements[0]["type"], "erreur_tour")
        self.assertEqual(evenements[0]["code"], "forte_demande")
        self.assertEqual(evenements[0]["etat_reprise"]["messages_agent"], self.ETAT["messages_agent"])

    def test_reprise_reussie_sauvegardee_dans_la_conversation(self):
        # Correctif 31/10/2026 (bouton Continuer) : une continuation réussie doit être persistée
        # dans le fil d'origine et renvoyer l'événement meta, sans inventer de ligne "user"
        # quand l'utilisateur a juste cliqué Continuer (parent_id = question d'origine).
        def reussit(*args, **kwargs):
            yield {"type": "reponse", "texte": "suite"}

        sauvegardes = []

        def fausse_sauvegarde(*args, **kwargs):
            sauvegardes.append((args, kwargs))
            return {"message_id_user": 7, "message_id_assistant": 8, "created_at_assistant": "t"}

        reprise = {"etat_reprise": self.ETAT, "type": "continuer_agent", "message_utilisateur": None}
        with patch.object(main, "_agent_groq", reussit), patch.object(main, "_client_pour_reprise", lambda m: None), \
                patch.object(main, "_catalogue_pour_demander_outils", lambda *a, **k: ([], {})), \
                patch.object(main, "_sauvegarder_echange", fausse_sauvegarde):
            evenements = list(main.chat(
                reprise=reprise, user_id="u1", agent_id="a1", conversation_id="c1",
                parent_id=7, erreurs_typees=True,
            ))

        self.assertEqual([e["type"] for e in evenements], ["reponse", "meta"])
        self.assertEqual(evenements[1]["message_id_assistant"], 8)
        self.assertEqual(len(sauvegardes), 1)
        args, kwargs = sauvegardes[0]
        self.assertEqual(args[:5], ("u1", "a1", "", "suite", "c1"))
        self.assertEqual(kwargs["parent_id"], 7)
        self.assertFalse(kwargs["sauvegarder_message_utilisateur"])


class ArretUtilisateur(unittest.TestCase):
    """Clic sur Arrêter : le flux se ferme avec l'etat de reprise des outils deja obtenus."""

    def _arret(self, avec_etat):
        jeton = ArretTour("utilisateur")
        jeton.avec_etat = avec_etat
        jeton.demander()
        return jeton

    def _jouer(self, messages, arret):
        return list(boucle_agent._agent_groq(None, messages, [], {}, arret=arret, modele="m", agent_nom="A"))

    def test_etat_envoye_avec_les_outils_obtenus(self):
        messages = BASE + [_appel("a"), _resultat("a"), _appel("b")]
        evenements = self._jouer(messages, self._arret(True))
        self.assertEqual([e["type"] for e in evenements], ["arret_tour"])
        self.assertEqual(evenements[0]["etat_reprise"]["messages_agent"], BASE + [_appel("a"), _resultat("a")])

    def test_sans_outil_pas_d_etat(self):
        evenements = self._jouer(list(BASE), self._arret(True))
        self.assertEqual(evenements, [{"type": "arret_tour", "etat_reprise": None}])

    def test_client_qui_ne_le_demande_pas_ne_recoit_rien(self):
        messages = BASE + [_appel("a"), _resultat("a")]
        self.assertEqual(self._jouer(messages, self._arret(False)), [])


class ReprisePayload(unittest.TestCase):
    def test_la_reprise_du_chat_est_acceptee(self):
        sys.path.append(".")
        from api.chat import RepriseConfirmation, _reprise_pour_chat

        reprise = RepriseConfirmation(**{"etat_reprise": {"a": 1}, "type": "continuer_agent", "message_utilisateur": "stop"})
        self.assertEqual(
            _reprise_pour_chat(reprise),
            {"etat_reprise": {"a": 1}, "type": "continuer_agent", "message_utilisateur": "stop"},
        )

    def test_la_confirmation_reste_comme_avant(self):
        from api.chat import RepriseConfirmation, _reprise_pour_chat

        reprise = RepriseConfirmation(etat_reprise={"a": 1}, approuve=False)
        self.assertEqual(_reprise_pour_chat(reprise), {"etat_reprise": {"a": 1}, "approuve": False})

    def test_sans_type_ni_approbation_refuse(self):
        from api.chat import RepriseConfirmation

        with self.assertRaises(ValueError):
            RepriseConfirmation(etat_reprise={"a": 1})


if __name__ == "__main__":
    unittest.main()
