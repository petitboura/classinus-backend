"""Tests hors ligne de la classification des outils pour la page Permissions des outils."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.catalogue_permissions import classer_outils_application, classer_outils_serveur

SENSIBLES = {"notion-update-page", "gerer_depot_github:creer_issue", "gerer_depot_github:supprimer"}


def _libelle(nom, action):
    return f"{nom}/{action}" if action else nom


class CatalogueApplicationTest(unittest.TestCase):
    def test_lecture_et_ecriture(self):
        outils = classer_outils_application("notion", ["notion-search", "notion-update-page"], SENSIBLES, _libelle)
        types = {o["cle"]: o["type"] for o in outils}
        self.assertEqual(types, {"notion-search": "lecture", "notion-update-page": "ecriture"})

    def test_outil_a_actions_une_ligne_par_action_sensible(self):
        outils = classer_outils_application("github", ["gerer_depot_github"], SENSIBLES, _libelle)
        types = {o["cle"]: o["type"] for o in outils}
        self.assertEqual(types["gerer_depot_github"], "lecture")
        self.assertEqual(types["gerer_depot_github:creer_issue"], "ecriture")
        self.assertEqual(types["gerer_depot_github:supprimer"], "ecriture")

    def test_autres_applications_ignorees(self):
        outils = classer_outils_application("notion", ["gerer_depot_github", "notion-search"], SENSIBLES, _libelle)
        self.assertEqual([o["cle"] for o in outils], ["notion-search"])


class CatalogueServeurTest(unittest.TestCase):
    def test_classement_et_doublons(self):
        a, b = "custommcp_list_abcdef_projets", "custommcp_delete_abcdef_projet"
        autre = "custommcp_list_123456_projets"
        elements = [{"nom": a, "label": "Lister"}, {"nom": a, "label": "Lister"},
                    {"nom": b, "label": "Supprimer"}, {"nom": autre, "label": "Autre"}]
        outils = classer_outils_serveur("custommcp_abcdef", elements, lambda nom: "list" in nom)
        self.assertEqual({o["cle"]: o["type"] for o in outils}, {a: "lecture", b: "ecriture"})


if __name__ == "__main__":
    unittest.main()
