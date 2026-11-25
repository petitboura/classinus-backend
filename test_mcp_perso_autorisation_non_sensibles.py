"""Tests hors ligne : autoriser d'un coup les outils non sensibles d'un serveur MCP personnalisé (17/11/2026).

Un outil est non sensible si le serveur le déclare en lecture seule ou, sans indication, si son nom commence
par un verbe de lecture. Les autres restent sensibles, de même qu'un outil inconnu de ce processus."""
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "secret-de-test")

from connexions import mcp_personnalises as mcp
from core import autorisations_outils
from core.execution_outils import _est_outil_sensible

SERVEUR = {"id": "abcdef12-0000-0000-0000-000000000000", "nom": "Mon serveur", "url": "https://exemple.org/mcp"}
AUTRE_SERVEUR = {"id": "123456ab-0000-0000-0000-000000000000", "nom": "Autre", "url": "https://autre.org/mcp"}


def _outil(nom, lecture_seule=None):
    annotations = None if lecture_seule is None else {"readOnlyHint": lecture_seule}
    return SimpleNamespace(name=nom, description="", annotations=annotations, input_schema={"type": "object", "properties": {}})


def _appel(nom_expose):
    return {"id": "x", "name": nom_expose, "arguments": json.dumps({})}


class AutorisationNonSensiblesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        outils = mcp._construire_outils(SERVEUR, [
            _outil("list_projects"),                 # sans indication, verbe de lecture
            _outil("delete_project"),                # sans indication, pas un verbe de lecture
            _outil("run_task"),                      # sans indication, on ne sait pas
            _outil("query_data"),                    # "query" reste sensible sans indication
            _outil("get_user", lecture_seule=False), # le serveur dit que ce n'est pas de la lecture seule
            _outil("compute_report", lecture_seule=True),  # le serveur dit lecture seule
        ])
        mcp._avec_routes(SERVEUR, "u1", outils)
        cls.noms = {o["nom_reel"]: o["nom"] for o in outils}
        autres = mcp._construire_outils(AUTRE_SERVEUR, [_outil("list_things")])
        mcp._avec_routes(AUTRE_SERVEUR, "u1", autres)
        cls.nom_autre = autres[0]["nom"]
        cls.autorisations = frozenset({mcp.cle_autorisation_serveur(SERVEUR["id"])})

    def test_classement_des_outils(self):
        attendu = {
            "list_projects": True, "delete_project": False, "run_task": False,
            "query_data": False, "get_user": False, "compute_report": True,
        }
        for nom_reel, non_sensible in attendu.items():
            self.assertEqual(mcp.est_outil_non_sensible(self.noms[nom_reel]), non_sensible, nom_reel)

    def test_outil_inconnu_reste_sensible(self):
        self.assertFalse(mcp.est_outil_non_sensible("custommcp_list_abcdef_inconnu_0000"))

    def test_le_serveur_est_retrouve(self):
        self.assertEqual(mcp.serveur_id_pour_outil(self.noms["list_projects"]), SERVEUR["id"])

    def test_autorisation_en_bloc_seulement_pour_les_non_sensibles(self):
        self.assertTrue(mcp.autorise_en_bloc(self.noms["list_projects"], self.autorisations))
        self.assertTrue(mcp.autorise_en_bloc(self.noms["compute_report"], self.autorisations))
        for sensible in ("delete_project", "run_task", "query_data", "get_user"):
            self.assertFalse(mcp.autorise_en_bloc(self.noms[sensible], self.autorisations), sensible)

    def test_autorisation_en_bloc_limitee_a_son_serveur(self):
        self.assertFalse(mcp.autorise_en_bloc(self.nom_autre, self.autorisations))

    def test_sans_autorisation_on_demande(self):
        self.assertFalse(mcp.autorise_en_bloc(self.noms["list_projects"], frozenset()))
        self.assertTrue(_est_outil_sensible(_appel(self.noms["list_projects"]), frozenset()))

    def test_la_confirmation_saute_pour_les_non_sensibles_autorises(self):
        self.assertFalse(_est_outil_sensible(_appel(self.noms["list_projects"]), self.autorisations))
        self.assertTrue(_est_outil_sensible(_appel(self.noms["delete_project"]), self.autorisations))
        self.assertTrue(_est_outil_sensible(_appel(self.nom_autre), self.autorisations))

    def test_reglage_de_categorie_lecture_autorise_les_non_sensibles(self):
        from core import permissions_outils
        nom = self.noms["list_projects"]
        groupe = permissions_outils.groupe_de_outil(nom)
        lignes = MagicMock()
        lignes.data = [{"cle": permissions_outils.cle_categorie(groupe, "lecture"), "etat": "autoriser"}]
        base = MagicMock()
        base.table.return_value.select.return_value.eq.return_value.execute.return_value = lignes
        with patch.object(permissions_outils, "_client", return_value=base):
            permissions = autorisations_outils.charger_autorisations("u1")
        self.assertFalse(_est_outil_sensible(_appel(nom), permissions))
        self.assertTrue(_est_outil_sensible(_appel(self.noms["delete_project"]), permissions))

    def test_panne_de_lecture_des_serveurs_redemande(self):
        with patch.object(mcp, "_SUPABASE", MagicMock(**{"table.side_effect": RuntimeError("panne")})):
            self.assertEqual(mcp.autorisations_serveurs_pour_utilisateur("u1"), frozenset())

    def test_definir_refuse_un_serveur_qui_n_est_pas_le_sien(self):
        base = MagicMock()
        base.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        with patch.object(mcp, "_SUPABASE", base):
            self.assertFalse(mcp.definir_autorisation_non_sensibles("u1", SERVEUR["id"], True))

    def test_case_proposee_seulement_pour_un_outil_non_sensible(self):
        from core import boucle_agent
        self.assertEqual(boucle_agent._serveur_pour_case_non_sensibles(self.noms["list_projects"]), "Mon serveur")
        self.assertIsNone(boucle_agent._serveur_pour_case_non_sensibles(self.noms["delete_project"]))
        self.assertIsNone(boucle_agent._serveur_pour_case_non_sensibles("gerer_depot_github"))


if __name__ == "__main__":
    unittest.main()
