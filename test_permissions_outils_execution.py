"""Tests hors ligne : les réglages autoriser / demander / bloquer appliqués par la boucle d'exécution (24/11/2026).

core/execution_outils.py tire le registre des outils, requests et les connecteurs, absents d'un poste de
test minimal : leurs dépendances sont remplacées ici par de petites doublures, avant l'import. La logique
testée (étapes de décision, refus d'un outil bloqué, confirmation d'une lecture) est celle du vrai fichier."""
import importlib
import json
import os
import sys
import types
import unittest
from unittest.mock import patch

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RACINE, "core"))
sys.path.insert(0, RACINE)

INTERDITE = "gerer_navigateur:submit"
OUTILS_SENSIBLES_TEST = {"vercel_delete_project", "vercel_deploy", INTERDITE, "gerer_depot_github:supprimer"}
EXECUTES = []


def _module(nom, **attributs):
    module = types.ModuleType(nom)
    module.__dict__.update(attributs)
    return module


def _installer_doublures():
    def appeler_outil(nom, arguments, table, arret=None):
        EXECUTES.append(nom)
        return json.dumps({"text": "fait"})

    registre = _module(
        "registre_outils",
        OUTILS_SENSIBLES=OUTILS_SENSIBLES_TEST,
        AUTORISATION_PERMANENTE_INTERDITE=frozenset({INTERDITE}),
        # Comme le vrai : tout "custommcp_" est sensible, un serveur prefixe l'est sauf lecture reconnue.
        est_outil_sensible_serveur_personnel=lambda nom: nom.startswith("custommcp_") or nom in OUTILS_SENSIBLES_TEST,
    )
    doublures = {
        "requests": _module("requests"),
        "registre_outils": registre,
        "core.registre_outils": registre,
        "core.mcp_tools": _module("core.mcp_tools", appeler_outil=appeler_outil),
        "profils_agents": _module(
            "profils_agents",
            _nom_lisible_appel=lambda appel: appel["name"],
            _action_appel=lambda appel: None,
            _champs_domaines_appel=lambda appel: {},
        ),
        "libelles_activite_ia": _module(
            "libelles_activite_ia",
            champs_timeline_appel=lambda appel, nom: (nom, f"{nom}...", f"{nom} effectué", False),
        ),
        "historique_outils": _module("historique_outils", champs_historique_outil=lambda *a: {}),
        "core.captures_modele": _module(
            "core.captures_modele",
            sans_image=lambda r: r,
            pour_le_modele=lambda r: (r, []),
            ajouter_message_images=lambda messages, images: None,
        ),
        "core.ressources_ui": _module(
            "core.ressources_ui",
            marquer_source=lambda r, n: r,
            separer_ressources_ui=lambda r: (r, []),
            NOTE_POUR_LE_MODELE="",
        ),
    }
    sys.modules.update(doublures)
    # `from core import captures_modele` lit l'attribut du paquet : on le pose aussi.
    import core
    core.captures_modele = doublures["core.captures_modele"]
    core.mcp_tools = doublures["core.mcp_tools"]


_installer_doublures()
sys.modules.pop("core.execution_outils", None)
execution = importlib.import_module("core.execution_outils")
from core import permissions_outils as p
from core.permissions_outils import AUTORISER, BLOQUER, DEMANDER, ECRITURE, LECTURE, Permissions

LISTE_INTERDITE = frozenset({INTERDITE})


def appel(nom, identifiant="a1", **arguments):
    return {"id": identifiant, "name": nom, "arguments": json.dumps(arguments)}


def jouer(appels, permissions):
    """Exécute un lot et renvoie (évènements, messages ajoutés, appel mis en attente ou None)."""
    messages, evenements, attente = [], [], None
    EXECUTES.clear()
    try:
        for evenement in execution._traiter_appels(list(appels), messages, {}, None, autorisations=permissions):
            evenements.append(evenement)
    except execution._AttenteConfirmation as e:
        attente = e
    return evenements, messages, attente


class BaseTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(p, "_cles_interdites", return_value=LISTE_INTERDITE)
        patcher.start()
        self.addCleanup(patcher.stop)


class DecisionTest(BaseTest):
    def test_defauts_comme_avant(self):
        perm = Permissions()
        self.assertFalse(execution._est_outil_sensible(appel("vercel_list_projects"), perm))
        self.assertTrue(execution._est_outil_sensible(appel("vercel_delete_project"), perm))

    def test_lecture_mise_sur_demander_reclame_la_confirmation(self):
        perm = Permissions({"vercel_list_projects": DEMANDER})
        self.assertTrue(execution._est_outil_sensible(appel("vercel_list_projects"), perm))

    def test_categorie_lecture_sur_demander(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", LECTURE): DEMANDER})
        self.assertTrue(execution._est_outil_sensible(appel("vercel_get_project"), perm))

    def test_ecriture_autorisee_en_bloc(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER})
        self.assertFalse(execution._est_outil_sensible(appel("vercel_delete_project"), perm))
        self.assertFalse(execution._est_outil_sensible(appel("vercel_deploy"), perm))

    def test_exception_outil_sur_demander_dans_une_categorie_autorisee(self):
        perm = Permissions({
            p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER,
            "vercel_delete_project": DEMANDER,
        })
        self.assertTrue(execution._est_outil_sensible(appel("vercel_delete_project"), perm))
        self.assertFalse(execution._est_outil_sensible(appel("vercel_deploy"), perm))

    def test_l_action_interdite_reste_a_confirmer_meme_si_une_ligne_dit_autoriser(self):
        perm = Permissions({INTERDITE: AUTORISER})
        self.assertTrue(execution._est_outil_sensible(appel("gerer_navigateur", action="submit"), perm))

    def test_ancien_ensemble_de_cles_toujours_pris_en_charge(self):
        self.assertFalse(execution._est_outil_sensible(appel("vercel_delete_project"), frozenset({"vercel_delete_project"})))
        self.assertTrue(execution._est_outil_sensible(appel("vercel_delete_project"), frozenset()))
        self.assertTrue(execution._est_outil_sensible(appel("vercel_delete_project")))

    def test_une_panne_de_decision_retombe_sur_l_ancien_comportement(self):
        class Casse(Permissions):
            def etat(self, *a, **k):
                raise RuntimeError("panne")

        perm = Casse({"vercel_delete_project": AUTORISER})
        self.assertIsNone(execution.etat_permission_appel(appel("vercel_delete_project"), perm))
        # Ancien chemin : l'action autorisée n'est pas redemandée, une lecture reste libre.
        self.assertFalse(execution._est_outil_sensible(appel("vercel_delete_project"), perm))
        self.assertFalse(execution._est_outil_sensible(appel("vercel_list_projects"), perm))


class BlocageTest(BaseTest):
    def test_outil_bloque_n_est_pas_execute_et_l_ia_lit_pourquoi(self):
        perm = Permissions({"vercel_list_projects": BLOQUER})
        evenements, messages, attente = jouer([appel("vercel_list_projects")], perm)
        self.assertIsNone(attente)
        self.assertEqual(EXECUTES, [])
        self.assertEqual([e["type"] for e in evenements], ["statut", "statut_termine", "outil_resultat"])
        self.assertTrue(evenements[1]["texte"].endswith(" bloqué"))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "tool")
        self.assertEqual(messages[0]["tool_call_id"], "a1")
        self.assertIn("vercel_list_projects", messages[0]["content"])
        # Les deux langues sont dans le texte lu par l'IA.
        self.assertIn("Outil bloqué", messages[0]["content"])
        self.assertIn("Tool blocked", messages[0]["content"])

    def test_texte_du_refus_sans_tiret_double_ni_tiret_long(self):
        self.assertNotIn("--", execution.TEXTE_OUTIL_BLOQUE)
        self.assertNotIn("—", execution.TEXTE_OUTIL_BLOQUE)
        self.assertNotIn("–", execution.TEXTE_OUTIL_BLOQUE)

    def test_ecriture_bloquee_sans_demander_de_confirmation(self):
        perm = Permissions({"vercel_delete_project": BLOQUER})
        evenements, messages, attente = jouer([appel("vercel_delete_project")], perm)
        self.assertIsNone(attente)
        self.assertEqual(EXECUTES, [])
        self.assertEqual(len(messages), 1)

    def test_blocage_de_categorie(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", ECRITURE): BLOQUER})
        _, messages, attente = jouer([appel("vercel_deploy")], perm)
        self.assertIsNone(attente)
        self.assertEqual(EXECUTES, [])
        self.assertEqual(len(messages), 1)

    def test_lot_mixte_seul_le_bloque_est_refuse(self):
        perm = Permissions({"vercel_get_project": BLOQUER})
        lot = [appel("vercel_get_project", "a1"), appel("vercel_list_projects", "a2")]
        _, messages, attente = jouer(lot, perm)
        self.assertIsNone(attente)
        self.assertEqual(EXECUTES, ["vercel_list_projects"])
        self.assertEqual(sorted(m["tool_call_id"] for m in messages), ["a1", "a2"])

    def test_chaque_appel_du_lot_recoit_une_reponse(self):
        perm = Permissions({"vercel_get_project": BLOQUER, "vercel_list_projects": BLOQUER})
        lot = [appel("vercel_get_project", "a1"), appel("vercel_list_projects", "a2")]
        _, messages, _ = jouer(lot, perm)
        self.assertEqual(sorted(m["tool_call_id"] for m in messages), ["a1", "a2"])
        self.assertEqual(EXECUTES, [])

    def test_bloque_puis_sensible_les_restants_attendent_la_confirmation(self):
        perm = Permissions({"vercel_get_project": BLOQUER})
        lot = [appel("vercel_get_project", "a1"), appel("vercel_delete_project", "a2"), appel("vercel_list_projects", "a3")]
        _, messages, attente = jouer(lot, perm)
        self.assertIsNotNone(attente)
        self.assertEqual(attente.appel["id"], "a2")
        # Le bloqué n'est plus dans les appels à rejouer après la confirmation.
        self.assertEqual([a["id"] for a in attente.appels_restants], ["a3"])
        self.assertEqual([m["tool_call_id"] for m in messages], ["a1"])
        self.assertEqual(EXECUTES, [])

    def test_sans_blocage_le_comportement_est_inchange(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", ECRITURE): AUTORISER})
        _, messages, attente = jouer([appel("vercel_delete_project")], perm)
        self.assertIsNone(attente)
        self.assertEqual(EXECUTES, ["vercel_delete_project"])
        self.assertEqual(len(messages), 1)

    def test_ecriture_par_defaut_demande_toujours_confirmation(self):
        _, messages, attente = jouer([appel("vercel_delete_project")], Permissions())
        self.assertIsNotNone(attente)
        self.assertEqual(EXECUTES, [])
        self.assertEqual(messages, [])

    def test_lecture_sur_demander_attend_la_confirmation(self):
        perm = Permissions({p.cle_categorie("vercel_mcp", LECTURE): DEMANDER})
        _, _, attente = jouer([appel("vercel_list_projects")], perm)
        self.assertIsNotNone(attente)
        self.assertEqual(EXECUTES, [])

    def test_blocage_sur_le_nom_d_un_outil_a_actions_vaut_pour_ses_actions(self):
        perm = Permissions({"gerer_depot_github": BLOQUER})
        # Action de lecture : la clé de l'outil est son nom.
        self.assertEqual(execution.etat_permission_appel(appel("gerer_depot_github", action="lire"), perm), BLOQUER)
        # Action sensible : sa clé est "outil:action", et le blocage posé sur le nom de l'outil l'atteint aussi.
        self.assertEqual(execution.cle_autorisation_appel(appel("gerer_depot_github", action="supprimer")), "gerer_depot_github:supprimer")
        self.assertEqual(execution.etat_permission_appel(appel("gerer_depot_github", action="supprimer"), perm), BLOQUER)
        # Sans blocage sur le nom, l'action sensible suit son propre réglage.
        autre = Permissions({"gerer_depot_github:supprimer": AUTORISER})
        self.assertEqual(execution.etat_permission_appel(appel("gerer_depot_github", action="supprimer"), autre), AUTORISER)


if __name__ == "__main__":
    unittest.main()
