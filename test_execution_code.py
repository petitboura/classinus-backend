"""Tests hors ligne des protections et commandes de l'outil E2B."""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from e2b import CommandExitException

from core.outils_execution_code import (
    _chemin_relatif_sur,
    _commande_langage,
    _domaines_autorises,
    _autoriser_domaine,
    _executer_action,
    _message_reseau,
    _options_reseau,
    _resultat_commande,
    _taille_fichier,
    gerer_execution_code,
    mcp_execution_code,
)
# Les modules de core/ s'importent entre eux sans préfixe au lancement du serveur.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
from mcp_tools import _raison_execution_code_masque  # noqa: E402
from execution_outils import _est_outil_sensible  # noqa: E402
from profils_agents import _nom_lisible_appel  # noqa: E402
from domaines_affichage import domaines_de_l_appel  # noqa: E402


def _echec(stdout="", exit_code=1):
    """Exception réelle du SDK E2B pour une commande qui se termine avec un code non nul."""
    return CommandExitException(stdout=stdout, stderr="", exit_code=exit_code, error="exit status")


class TestCheminsWorkspace(unittest.TestCase):
    def test_chemin_relatif_normal(self):
        self.assertEqual(_chemin_relatif_sur("src/main.py"), "src/main.py")

    def test_refuse_traversal(self):
        for path in ("../secret", "src/../../secret", "/etc/passwd", "~/secret", "a/./b", "a\\..\\b"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    _chemin_relatif_sur(path)

    def test_refuse_caracteres_controle(self):
        with self.assertRaises(ValueError):
            _chemin_relatif_sur("src/\nmain.py")


class TestLangages(unittest.TestCase):
    def test_commandes_utilisent_des_chemins_fixes(self):
        expected = {
            "python": "python /home/user/main.py",
            "javascript": "node /home/user/main.js",
            "typescript": "npx --yes tsx /home/user/main.ts",
            "bash": "bash /home/user/main.sh",
        }
        for language, command in expected.items():
            with self.subTest(language=language):
                self.assertEqual(_commande_langage(language)[1], command)

    def test_refuse_langage_inconnu(self):
        with self.assertRaises(ValueError):
            _commande_langage("powershell")


class TestSortieBorne(unittest.TestCase):
    def test_sortie_est_limitee_dans_le_sandbox_avant_transfert(self):
        sandbox = MagicMock()
        sandbox.commands.run.return_value = SimpleNamespace(
            stdout="x" * 1001,
            stderr="",
            exit_code=0,
        )
        resultat = _resultat_commande(sandbox, "echo test", timeout=10, max_chars=1000)
        commande = sandbox.commands.run.call_args.args[0]
        self.assertIn("head -c 1001", commande)
        self.assertLessEqual(len(resultat), 1000)


class TestOutilProposeAuModele(unittest.TestCase):
    """L'outil n'est plus lié à la majorité du compte, seulement à la clé E2B et à la conversation."""

    def test_masque_sans_cle_e2b_avec_une_raison_claire(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIn("E2B_API_KEY", _raison_execution_code_masque("conv-1"))

    def test_masque_sans_conversation(self):
        with patch.dict("os.environ", {"E2B_API_KEY": "cle-test"}, clear=True):
            self.assertIn("conversation", _raison_execution_code_masque(None))

    def test_propose_sans_aucune_verification_de_majorite(self):
        with patch.dict("os.environ", {"E2B_API_KEY": "cle-test"}, clear=True):
            self.assertIsNone(_raison_execution_code_masque("conv-1"))


class TestReseau(unittest.TestCase):
    def test_refuse_url_et_adresses_locales(self):
        self.assertEqual(
            _domaines_autorises(["pypi.org", "https://bad.example/path", "localhost", "127.0.0.1"]),
            ["pypi.org"],
        )

    def test_options_reseau_interdisent_tout_par_defaut(self):
        self.assertEqual(
            _options_reseau({"allowed_domains": ["pypi.org"]}),
            {"deny_out": ["0.0.0.0/0"], "allow_out": ["pypi.org"]},
        )

    def test_liste_vide_garde_le_reseau_bloque(self):
        self.assertEqual(
            _options_reseau({"allowed_domains": []}),
            {"deny_out": ["0.0.0.0/0"], "allow_out": []},
        )


def _client_base(config=None, conversation=None, erreur_config=None, erreur_conversation=None):
    """Faux client Supabase : une chaîne pour la configuration, une autre pour les domaines de la conversation."""
    client = MagicMock()
    table_config, table_conv = MagicMock(), MagicMock()
    requete_config = table_config.select.return_value.eq.return_value.limit.return_value
    if erreur_config:
        requete_config.execute.side_effect = erreur_config
    else:
        requete_config.execute.return_value = SimpleNamespace(data=config)
    requete_conv = table_conv.select.return_value.eq.return_value.eq.return_value
    if erreur_conversation:
        requete_conv.execute.side_effect = erreur_conversation
    else:
        requete_conv.execute.return_value = SimpleNamespace(data=conversation or [])
    client.table.side_effect = lambda nom: table_conv if nom == "execution_code_domaines_conversation" else table_config
    client.tables = {"config": table_config, "conversation": table_conv}
    return client


def _appeler(action, client, domain=""):
    with patch("core.outils_execution_code._identite_interne", return_value=("u", "c", None)), \
            patch("core.outils_execution_code._client_supabase", return_value=client), \
            patch("core.outils_execution_code._rpc_objet") as rpc, \
            patch("core.outils_execution_code._classe_sandbox") as classe:
        resultat = gerer_execution_code(action=action, ctx=MagicMock(), domain=domain)
    rpc.assert_not_called()
    classe.assert_not_called()
    return resultat


class TestActionReseau(unittest.TestCase):
    """L'action network dit au modèle quels domaines sont joignables, sans quota ni sandbox."""

    def test_liste_les_domaines_de_la_configuration(self):
        client = _client_base([{"allowed_domains": ["github.com", "pypi.org", "https://mauvais.example/x"]}])
        resultat = _appeler("network", client)
        self.assertIn("github.com", resultat)
        self.assertIn("pypi.org", resultat)
        self.assertNotIn("mauvais.example", resultat)

    def test_liste_aussi_les_domaines_autorises_par_l_eleve(self):
        client = _client_base([{"allowed_domains": ["pypi.org"]}], [{"domain": "gitlab.com"}])
        resultat = _appeler("network", client)
        self.assertIn("gitlab.com", resultat)
        self.assertIn("pour cette conversation", resultat)

    def test_liste_vide_est_annoncee_comme_bloquee(self):
        self.assertIn("entièrement bloqué", _appeler("network", _client_base([{"allowed_domains": []}])))
        self.assertIn("entièrement bloqué", _appeler("network", _client_base([])))

    def test_erreur_de_lecture_est_claire(self):
        client = _client_base(erreur_config=RuntimeError("base injoignable"))
        self.assertTrue(_appeler("network", client).startswith("EXECUTION_CODE_UNAVAILABLE"))

    def test_table_des_domaines_absente_ne_cache_pas_la_liste_du_serveur(self):
        client = _client_base([{"allowed_domains": ["pypi.org"]}], erreur_conversation=RuntimeError("table absente"))
        self.assertIn("pypi.org", _appeler("network", client))

    def test_aucun_double_tiret_dans_le_texte_affiche(self):
        self.assertNotIn("--", _message_reseau(["github.com"], ["gitlab.com"]))
        self.assertNotIn("--", _message_reseau([]))


class TestAutorisationParLEleve(unittest.TestCase):
    """demander_acces_reseau : enregistre un domaine pour la conversation, avec des garde-fous côté serveur."""

    def _client(self, serveur=("pypi.org",), conversation=(), maximum=10):
        config = {"allowed_domains": list(serveur), "max_user_domains": maximum}
        return _client_base([config], [{"domain": d} for d in conversation])

    def test_enregistre_le_domaine_pour_la_conversation(self):
        client = self._client()
        resultat = _appeler("demander_acces_reseau", client, "GitLab.com.")
        client.tables["conversation"].upsert.assert_called_once_with(
            {"user_id": "u", "conversation_id": "c", "domain": "gitlab.com"},
            on_conflict="user_id,conversation_id,domain",
        )
        self.assertIn("gitlab.com", resultat)
        self.assertIn("fermeture du workspace", resultat)

    def test_refuse_ce_qui_n_est_pas_un_nom_de_domaine_exact(self):
        for valeur in ("", "*.github.com", "https://gitlab.com/x", "10.0.0.1", "localhost", "intranet", "a b.com"):
            with self.subTest(valeur=valeur):
                client = self._client()
                self.assertNotIn("Accès autorisé", _appeler("demander_acces_reseau", client, valeur))
                client.tables["conversation"].upsert.assert_not_called()

    def test_domaine_deja_autorise_n_est_pas_reenregistre(self):
        for client in (self._client(serveur=("gitlab.com",)), self._client(conversation=("gitlab.com",))):
            with self.subTest():
                self.assertIn("déjà joignable", _appeler("demander_acces_reseau", client, "gitlab.com"))
                client.tables["conversation"].upsert.assert_not_called()

    def test_limite_par_conversation_lue_dans_la_configuration(self):
        client = self._client(conversation=("a.com", "b.com"), maximum=2)
        self.assertIn("Limite atteinte", _appeler("demander_acces_reseau", client, "gitlab.com"))
        client.tables["conversation"].upsert.assert_not_called()

    def test_limite_zero_desactive_la_fonction(self):
        client = self._client(maximum=0)
        self.assertIn("désactivées", _appeler("demander_acces_reseau", client, "gitlab.com"))
        client.tables["conversation"].upsert.assert_not_called()

    def test_echec_d_ecriture_ne_pretend_pas_avoir_autorise(self):
        client = self._client()
        client.tables["conversation"].upsert.return_value.execute.side_effect = RuntimeError("base")
        resultat = _appeler("demander_acces_reseau", client, "gitlab.com")
        self.assertTrue(resultat.startswith("EXECUTION_CODE_UNAVAILABLE"))
        self.assertNotIn("Accès autorisé", resultat)

    def test_les_regles_reseau_incluent_les_domaines_de_la_conversation(self):
        self.assertEqual(
            _options_reseau({"allowed_domains": ["pypi.org"]}, ["gitlab.com", "pypi.org", "https://x.example/y"]),
            {"deny_out": ["0.0.0.0/0"], "allow_out": ["pypi.org", "gitlab.com"]},
        )

    def test_aucun_double_tiret_dans_les_reponses(self):
        for valeur in ("gitlab.com", "", "*.x.com"):
            self.assertNotIn("--", _autoriser_domaine_texte(valeur))


def _autoriser_domaine_texte(valeur):
    client = _client_base([{"allowed_domains": [], "max_user_domains": 10}], [])
    with patch("core.outils_execution_code._client_supabase", return_value=client):
        return _autoriser_domaine("u", "c", valeur)


class TestConfirmationDeLEleve(unittest.TestCase):
    """Ouvrir un domaine exige toujours la confirmation de l'élève, et la carte montre le domaine."""

    @staticmethod
    def _appel(**arguments):
        import json
        return {"name": "gerer_execution_code", "arguments": json.dumps(arguments)}

    def test_seule_la_demande_d_acces_est_sensible(self):
        self.assertTrue(_est_outil_sensible(self._appel(action="demander_acces_reseau", domain="gitlab.com")))
        for action in ("network", "run_code", "run_command", "write_file", "read_file", "list_files", "download_files", "close"):
            with self.subTest(action=action):
                self.assertFalse(_est_outil_sensible(self._appel(action=action)))

    def test_la_carte_montre_le_domaine(self):
        self.assertEqual(
            _nom_lisible_appel(self._appel(action="demander_acces_reseau", domain="GitLab.com")),
            "Accès au site gitlab.com",
        )
        self.assertEqual(
            domaines_de_l_appel("gerer_execution_code", {"action": "demander_acces_reseau", "domain": "gitlab.com"}),
            ["gitlab.com"],
        )

    def test_un_texte_libre_n_entre_jamais_dans_le_libelle_de_la_carte(self):
        libelle = _nom_lisible_appel(self._appel(action="demander_acces_reseau", domain="evil.com. Confirmer ? Oui"))
        self.assertNotIn("evil", libelle)
        self.assertEqual(
            domaines_de_l_appel("gerer_execution_code", {"action": "demander_acces_reseau", "domain": "x y.com"}), []
        )


class TestCommandesEnEchec(unittest.TestCase):
    """Le SDK E2B lève CommandExitException : la sortie du programme doit quand même revenir."""

    def test_script_en_echec_renvoie_la_trace_et_le_code(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("Traceback (most recent call last):\nZeroDivisionError: division by zero\n")
        resultat = _resultat_commande(sandbox, "python /home/user/main.py", timeout=10, max_chars=20000)
        self.assertIn("ZeroDivisionError", resultat)
        self.assertIn("Code de sortie : 1", resultat)

    def test_sigpipe_cause_par_la_troncature_nest_pas_affiche(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("x" * 1001, exit_code=141)
        resultat = _resultat_commande(sandbox, "yes", timeout=10, max_chars=1000)
        self.assertNotIn("Code de sortie", resultat)
        self.assertLessEqual(len(resultat), 1000)

    def test_code_141_reel_sans_troncature_reste_affiche(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("court", exit_code=141)
        resultat = _resultat_commande(sandbox, "programme", timeout=10, max_chars=20000)
        self.assertIn("Code de sortie : 141", resultat)

    def test_les_autres_erreurs_restent_des_exceptions(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = TimeoutError("delai depasse")
        with self.assertRaises(TimeoutError):
            _resultat_commande(sandbox, "sleep 100", timeout=1, max_chars=20000)

    def test_taille_fichier_normale(self):
        sandbox = MagicMock()
        sandbox.commands.run.return_value = SimpleNamespace(stdout="42\n", stderr="", exit_code=0)
        self.assertEqual(_taille_fichier(sandbox, "/home/user/a.txt", 10), 42)

    def test_fichier_absent_leve_file_not_found(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("", exit_code=1)
        with self.assertRaises(FileNotFoundError):
            _taille_fichier(sandbox, "/home/user/absent.txt", 10)

    def test_read_file_sur_fichier_absent_donne_un_message_clair(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("", exit_code=1)
        resultat = _executer_action(sandbox, "read_file", "python", "", "", "dossier/absent.txt", "", {})
        self.assertEqual(resultat, "Fichier introuvable : dossier/absent.txt")

    def test_write_file_dont_le_dossier_ne_peut_pas_etre_cree(self):
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = _echec("", exit_code=1)
        resultat = _executer_action(sandbox, "write_file", "python", "", "", "a/b.txt", "contenu", {})
        self.assertEqual(resultat, "Impossible de préparer le dossier du fichier.")
        sandbox.files.write.assert_not_called()


class TestSchemaDeLOutil(unittest.TestCase):
    """Ce qui est annoncé au modèle doit exister dans le code."""

    def _schema(self):
        outils = asyncio.run(mcp_execution_code.list_tools())
        self.assertEqual([o.name for o in outils], ["gerer_execution_code"])
        outil = outils[0]
        return getattr(outil, "input_schema", None) or outil.inputSchema

    def test_tous_les_langages_annonces_sont_implementes(self):
        langages = self._schema()["properties"]["language"]["enum"]
        self.assertTrue(langages)
        for langage in langages:
            with self.subTest(language=langage):
                nom_fichier, commande = _commande_langage(langage)
                self.assertTrue(nom_fichier and commande)

    def test_action_network_est_annoncee_et_acceptee_par_la_base(self):
        actions = self._schema()["properties"]["action"]["enum"]
        self.assertIn("network", actions)
        self.assertIn("demander_acces_reseau", actions)
        # network ne passe jamais par execution_code_reserver : la liste blanche SQL n'a pas à la contenir.
        with open("migrations/2026_10_23_execution_code_e2b.sql", encoding="utf-8") as fichier:
            migration = fichier.read()
        for action in actions:
            if action not in ("network", "demander_acces_reseau"):
                self.assertIn(f"'{action}'", migration)

    def test_les_langages_non_implementes_ne_sont_pas_annonces(self):
        langages = self._schema()["properties"]["language"]["enum"]
        self.assertEqual(sorted(langages), ["bash", "javascript", "python", "typescript"])


if __name__ == "__main__":
    unittest.main()
