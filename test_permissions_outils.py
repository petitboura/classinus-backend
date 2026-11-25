"""Tests hors ligne : permissions des outils (autoriser, demander, bloquer), 24/11/2026.

Ne touchent ni la base ni le réseau : toute la logique de priorité est dans core/permissions_outils.py."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from core import permissions_outils as p
from core.permissions_outils import AUTORISER, BLOQUER, DEMANDER, ECRITURE, LECTURE, Permissions

OUTIL_PERSO = "custommcp_list_abcdef_projets"
INTERDITE = "gerer_navigateur:submit"
# registre_outils.py ne se charge pas hors serveur (il importe httpx et les connecteurs) : la liste
# des actions toujours à confirmer est donc injectée, comme le fait le vrai module en production.
LISTE_INTERDITE = frozenset({INTERDITE, "vercel_deploy_secret"})


def interdites():
    return patch.object(p, "_cles_interdites", return_value=LISTE_INTERDITE)


class GroupeTest(unittest.TestCase):
    def test_groupe_application(self):
        self.assertEqual(p.groupe_de_outil("vercel_list_projects"), "vercel_mcp")
        self.assertEqual(p.groupe_de_outil("notion-search"), "notion")
        self.assertEqual(p.groupe_de_outil("gerer_depot_github"), "github")
        self.assertEqual(p.groupe_de_outil("gerer_depot_github:supprimer"), "github")

    def test_groupe_serveur_perso(self):
        self.assertEqual(p.groupe_de_outil(OUTIL_PERSO), "custommcp_abcdef")
        self.assertEqual(p.groupe_serveur_perso("ABCDEF12-0000-0000-0000-000000000000"), "custommcp_abcdef")

    def test_outil_interne_sans_groupe(self):
        self.assertIsNone(p.groupe_de_outil("generer_image"))
        self.assertIsNone(p.groupe_de_outil(""))
        self.assertIsNone(p.groupe_de_outil(None))
        self.assertIsNone(p.groupe_de_outil("custommcp_mal_forme"))


class DefautsTest(unittest.TestCase):
    def test_application_connectee(self):
        self.assertEqual(p.defaut_pour("vercel_mcp", LECTURE), AUTORISER)
        self.assertEqual(p.defaut_pour("vercel_mcp", ECRITURE), DEMANDER)

    def test_serveur_perso_demande_toujours(self):
        self.assertEqual(p.defaut_pour("custommcp_abcdef", LECTURE), DEMANDER)
        self.assertEqual(p.defaut_pour("custommcp_abcdef", ECRITURE), DEMANDER)

    def test_outil_interne_comme_avant(self):
        self.assertEqual(p.defaut_pour(None, LECTURE), AUTORISER)
        self.assertEqual(p.defaut_pour(None, ECRITURE), DEMANDER)


class PrioriteTest(unittest.TestCase):
    def setUp(self):
        patcher = interdites()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sans_reglage_le_defaut_s_applique(self):
        perm = Permissions()
        self.assertEqual(perm.etat("vercel_list_projects", "vercel_mcp", LECTURE), AUTORISER)
        self.assertEqual(perm.etat("vercel_delete_project", "vercel_mcp", ECRITURE), DEMANDER)

    def test_la_categorie_s_applique_a_tous_ses_outils(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER})
        self.assertEqual(perm.etat("vercel_delete_project", "vercel_mcp", ECRITURE), AUTORISER)
        # L'autre catégorie n'est pas touchée.
        self.assertEqual(perm.etat("vercel_list_projects", "vercel_mcp", LECTURE), AUTORISER)

    def test_l_outil_l_emporte_sur_sa_categorie(self):
        perm = Permissions({
            p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER,
            "vercel_delete_project": BLOQUER,
        })
        self.assertEqual(perm.etat("vercel_delete_project", "vercel_mcp", ECRITURE), BLOQUER)
        self.assertEqual(perm.etat("vercel_deploy", "vercel_mcp", ECRITURE), AUTORISER)

    def test_lecture_peut_etre_mise_sur_demander_ou_bloquer(self):
        perm = Permissions({"vercel_list_projects": DEMANDER, p.cle_categorie("vercel_mcp", LECTURE): BLOQUER})
        self.assertEqual(perm.etat("vercel_list_projects", "vercel_mcp", LECTURE), DEMANDER)
        self.assertEqual(perm.etat("vercel_get_project", "vercel_mcp", LECTURE), BLOQUER)

    def test_serveur_perso_lecture_autorisee_en_bloc(self):
        perm = Permissions({p.cle_categorie("custommcp_abcdef", LECTURE): AUTORISER})
        self.assertEqual(perm.etat(OUTIL_PERSO, "custommcp_abcdef", LECTURE), AUTORISER)
        # L'écriture du même serveur continue de demander.
        self.assertEqual(perm.etat("custommcp_delete_abcdef_projet", "custommcp_abcdef", ECRITURE), DEMANDER)

    def test_autre_serveur_non_touche(self):
        perm = Permissions({p.cle_categorie("custommcp_abcdef", LECTURE): AUTORISER})
        self.assertEqual(perm.etat("custommcp_list_123456_x", "custommcp_123456", LECTURE), DEMANDER)

    def test_action_interdite_ne_devient_jamais_autorisee(self):
        perm = Permissions({INTERDITE: AUTORISER})
        self.assertEqual(perm.etat(INTERDITE, None, ECRITURE), DEMANDER)

    def test_etat_inconnu_ignore(self):
        perm = Permissions({"vercel_x": "n_importe_quoi"})
        self.assertFalse(perm)
        self.assertEqual(perm.etat("vercel_x", "vercel_mcp", ECRITURE), DEMANDER)

    def test_contains_compatible_avec_l_ancien_ensemble(self):
        perm = Permissions({"a": AUTORISER, "b": BLOQUER, "c": DEMANDER})
        self.assertIn("a", perm)
        self.assertNotIn("b", perm)
        self.assertNotIn("c", perm)

    def test_blocages(self):
        self.assertFalse(Permissions({"a": AUTORISER}).a_des_blocages())
        self.assertTrue(Permissions({"a": BLOQUER}).a_des_blocages())


class ValidationTest(unittest.TestCase):
    def setUp(self):
        patcher = interdites()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reglages_valides(self):
        self.assertIsNone(p.valider_reglage("vercel_mcp", "vercel_list_projects", BLOQUER))
        self.assertIsNone(p.valider_reglage("vercel_mcp", p.cle_categorie("vercel_mcp", ECRITURE), AUTORISER))
        self.assertIsNone(p.valider_reglage("custommcp_abcdef", OUTIL_PERSO, DEMANDER))
        self.assertIsNone(p.valider_reglage("custommcp_abcdef", p.cle_categorie("custommcp_abcdef", LECTURE), AUTORISER))

    def test_etat_inconnu_refuse(self):
        self.assertEqual(p.valider_reglage("vercel_mcp", "vercel_x", "supprimer"), "etat_invalide")

    def test_groupe_inconnu_refuse(self):
        self.assertEqual(p.valider_reglage("inconnu", "vercel_x", BLOQUER), "groupe_invalide")
        self.assertEqual(p.valider_reglage("custommcp_zzzzzz", OUTIL_PERSO, BLOQUER), "groupe_invalide")

    def test_outil_d_une_autre_application_refuse(self):
        self.assertEqual(p.valider_reglage("vercel_mcp", "railway_list_projects", BLOQUER), "outil_hors_application")
        self.assertEqual(p.valider_reglage("custommcp_abcdef", "custommcp_list_123456_x", BLOQUER), "outil_hors_application")

    def test_categorie_d_une_autre_application_refusee(self):
        self.assertEqual(p.valider_reglage("vercel_mcp", p.cle_categorie("railway_mcp", LECTURE), BLOQUER), "categorie_invalide")
        self.assertEqual(p.valider_reglage("vercel_mcp", "categorie:vercel_mcp:autre", BLOQUER), "categorie_invalide")

    def test_cle_trop_longue_refusee(self):
        self.assertEqual(p.valider_reglage("vercel_mcp", "vercel_" + "x" * 300, BLOQUER), "cle_invalide")

    def test_action_interdite_ne_peut_pas_etre_autorisee(self):
        self.assertEqual(p.valider_reglage("vercel_mcp", "vercel_deploy_secret", AUTORISER), "autorisation_interdite")
        # Mais elle peut être bloquée ou rester à confirmer.
        self.assertIsNone(p.valider_reglage("vercel_mcp", "vercel_deploy_secret", BLOQUER))
        self.assertIsNone(p.valider_reglage("vercel_mcp", "vercel_deploy_secret", DEMANDER))


class VueTest(unittest.TestCase):
    def setUp(self):
        patcher = interdites()
        patcher.start()
        self.addCleanup(patcher.stop)

    OUTILS = [
        {"cle": "vercel_list_projects", "nom_lisible": "Lister les projets", "type": LECTURE},
        {"cle": "vercel_get_project", "nom_lisible": "Consulter un projet", "type": LECTURE},
        {"cle": "vercel_delete_project", "nom_lisible": "Supprimer un projet", "type": ECRITURE},
    ]

    def test_deux_categories_avec_leurs_outils(self):
        vue = p.construire_vue("vercel_mcp", self.OUTILS, Permissions())
        self.assertEqual([c["type"] for c in vue["categories"]], [LECTURE, ECRITURE])
        lecture, ecriture = vue["categories"]
        self.assertEqual([o["cle"] for o in lecture["outils"]], ["vercel_get_project", "vercel_list_projects"])
        self.assertEqual([o["cle"] for o in ecriture["outils"]], ["vercel_delete_project"])
        self.assertEqual((lecture["par_defaut"], ecriture["par_defaut"]), (AUTORISER, DEMANDER))
        self.assertIsNone(lecture["etat"])
        self.assertEqual(lecture["etat_effectif"], AUTORISER)

    def test_reglages_visibles_dans_la_vue(self):
        perm = Permissions({
            p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER,
            "vercel_delete_project": BLOQUER,
        })
        vue = p.construire_vue("vercel_mcp", self.OUTILS, perm)
        ecriture = vue["categories"][1]
        self.assertEqual(ecriture["etat"], AUTORISER)
        self.assertEqual(ecriture["outils"][0]["etat"], BLOQUER)
        self.assertEqual(ecriture["outils"][0]["etat_effectif"], BLOQUER)

    def test_action_interdite_sans_choix_autoriser(self):
        outils = [{"cle": INTERDITE, "nom_lisible": "Valider un formulaire", "type": ECRITURE}]
        vue = p.construire_vue("vercel_mcp", outils, Permissions({INTERDITE: AUTORISER}))
        outil = vue["categories"][1]["outils"][0]
        self.assertFalse(outil["autorisation_possible"])
        self.assertEqual(outil["etat_effectif"], DEMANDER)


if __name__ == "__main__":
    unittest.main()
