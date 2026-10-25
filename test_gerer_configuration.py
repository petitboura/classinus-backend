"""Tests de l'outil gerer_configuration (ex gerer_comportement) : il ne gère que la configuration, jamais les skills."""
import logging
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)

from core import outils_comportements_connaissance as O  # noqa: E402

REGLE = {"id": "r1", "nom": "Tutoiement", "description": "Toujours tutoyer", "categorie": "regle", "texte": "Tu me tutoies"}
SKILL_CLASSIQUE = {"id": "s1", "nom": "Ancien skill", "description": "Un skill classique", "categorie": None}


def ctx():
    requete = SimpleNamespace(query_params={"user_id": "u1", "agent_id": "a1"})
    return SimpleNamespace(request_context=SimpleNamespace(request=requete))


def appeler(**kwargs):
    return O.gerer_configuration(ctx=ctx(), **kwargs)


class TestGererConfiguration(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(O, "_lister_comportements", return_value=[REGLE, SKILL_CLASSIQUE])
        patch.start()
        self.addCleanup(patch.stop)

    def test_lister_ne_montre_que_la_configuration(self):
        texte = appeler(action="lister")
        self.assertIn("Tutoiement", texte)
        self.assertNotIn("Ancien skill", texte)

    def test_consulter_refuse_un_skill_classique_et_les_ids_recus(self):
        with mock.patch.object(O, "_obtenir_comportement_skill", return_value="contenu") as lecture:
            self.assertIn("introuvable", appeler(action="consulter", comportement_id="s1"))
            self.assertIn("introuvable", appeler(action="consulter", comportement_id="recu:x"))
            lecture.assert_not_called()
            self.assertEqual(appeler(action="consulter", comportement_id="r1"), "contenu")

    def test_ajouter_exige_une_categorie_et_renvoie_vers_gerer_skill(self):
        with mock.patch.object(O, "_ajouter_comportement") as ajout:
            texte = appeler(action="ajouter", texte="un skill")
            self.assertIn("gerer_skill", texte)
            ajout.assert_not_called()

    def test_ajouter_une_regle(self):
        with mock.patch.object(O, "_ajouter_comportement", return_value={"id": "n1", "description": "d"}) as ajout:
            texte = appeler(action="ajouter", categorie="regle", texte="Sois bref")
            ajout.assert_called_once()
            self.assertIn("n1", texte)

    def test_modifier_et_supprimer_refusent_un_skill_classique(self):
        with mock.patch.object(O, "_modifier_comportement") as modif, mock.patch.object(O, "_supprimer_comportement") as supp:
            self.assertIn("introuvable", appeler(action="modifier", comportement_id="s1", texte="x"))
            self.assertIn("introuvable", appeler(action="supprimer", comportement_id="s1"))
            modif.assert_not_called()
            supp.assert_not_called()

    def test_supprimer_un_element_de_configuration(self):
        with mock.patch.object(O, "_supprimer_comportement", return_value=True) as supp:
            self.assertIn("supprimé", appeler(action="supprimer", comportement_id="r1"))
            supp.assert_called_once_with("a1", "u1", "r1")

    def test_ancien_nom_retire(self):
        self.assertFalse(hasattr(O, "gerer_comportement"))


if __name__ == "__main__":
    unittest.main()
