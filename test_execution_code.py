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
    _action_pour_reservation,
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
        for action in ("network", "run_code", "run_command", "write_file", "read_file", "list_files", "download_files", "importer_fichier", "close"):
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


class TestActionsWorkspace(unittest.TestCase):
    def test_edit_file_remplace_une_occurrence_unique(self):
        sandbox = MagicMock()
        sandbox.files.read.return_value = "valeur = 1\n"
        with patch("core.outils_execution_code._taille_fichier", return_value=12), patch("core.outils_execution_code._lancer_commande", return_value=SimpleNamespace(exit_code=0)):
            resultat = _executer_action(
                sandbox, "edit_file", "python", "", "", "main.py", "", {},
                old_text="valeur = 1", new_text="valeur = 2",
            )
        self.assertIn("1 occurrence remplacée", resultat)
        chemin_temporaire, contenu = sandbox.files.write.call_args.args
        self.assertIn(".classinus-", chemin_temporaire)
        self.assertEqual(contenu, "valeur = 2\n")

    def test_edit_file_refuse_un_texte_present_plusieurs_fois(self):
        sandbox = MagicMock()
        sandbox.files.read.return_value = "x = 1\nx = 1\n"
        with patch("core.outils_execution_code._taille_fichier", return_value=12):
            resultat = _executer_action(
                sandbox, "edit_file", "python", "", "", "main.py", "", {},
                old_text="x = 1", new_text="x = 2",
            )
        self.assertIn("apparaît 2 fois", resultat)
        sandbox.files.write.assert_not_called()

    def test_read_file_lit_une_plage_sans_telecharger_le_fichier_entier(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._taille_fichier", return_value=5000000), patch("core.outils_execution_code._resultat_commande", return_value="100\tligne") as executer:
            resultat = _executer_action(
                sandbox, "read_file", "python", "", "", "src/main.py", "", {},
                start_line=100, end_line=200,
            )
        self.assertIn("lignes 100 à 200", resultat)
        commande = executer.call_args.args[1]
        self.assertIn("sed -n '100,200p'", commande)
        self.assertIn("nl -ba -v 100", commande)
        sandbox.files.read.assert_not_called()

    def test_search_files_utilise_grep_avec_numero_de_ligne(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._resultat_commande", return_value="src/a.py:12:match") as executer:
            resultat = _executer_action(
                sandbox, "search_files", "python", "", "", "src", "", {},
                pattern="def calculer",
            )
        self.assertIn("src/a.py:12", resultat)
        commande = executer.call_args.args[1]
        self.assertIn("grep -RInE", commande)
        self.assertIn("--exclude-dir=.git", commande)
        self.assertIn("sed 's#^/home/user/##'", commande)
        self.assertIn("PIPESTATUS[0]", commande)
        self.assertIn("src", commande)

    def test_find_files_utilise_un_motif_de_nom_et_exclut_les_dependances(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._resultat_commande", return_value="src/main.py") as executer:
            resultat = _executer_action(
                sandbox, "find_files", "python", "", "", "", "", {},
                pattern="*.py",
            )
        self.assertIn("src/main.py", resultat)
        commande = executer.call_args.args[1]
        self.assertIn("-name '*.py'", commande)
        self.assertIn("node_modules", commande)
        self.assertIn("-type f", commande)

    def _edition(self, contenu, configuration=None, **options):
        sandbox = MagicMock()
        sandbox.files.read.return_value = contenu
        with patch("core.outils_execution_code._taille_fichier", return_value=len(contenu)), patch("core.outils_execution_code._lancer_commande", return_value=SimpleNamespace(exit_code=0)):
            resultat = _executer_action(sandbox, "edit_file", "python", "", "", "main.py", "", configuration or {}, **options)
        return sandbox, resultat

    def test_edit_file_replace_all_remplace_toutes_les_occurrences(self):
        sandbox, resultat = self._edition("x = 1\nx = 1\nx = 1\n", old_text="x = 1", new_text="x = 2", replace_all=True)
        self.assertIn("3 occurrences remplacées", resultat)
        self.assertEqual(sandbox.files.write.call_args.args[1], "x = 2\nx = 2\nx = 2\n")

    def test_edit_file_replace_all_sur_une_seule_occurrence_reste_au_singulier(self):
        sandbox, resultat = self._edition("valeur = 1\n", old_text="valeur = 1", new_text="valeur = 2", replace_all=True)
        self.assertIn("1 occurrence remplacée", resultat)
        self.assertNotIn("occurrences", resultat)

    def test_edit_file_sans_replace_all_propose_de_l_utiliser(self):
        sandbox, resultat = self._edition("x = 1\nx = 1\n", old_text="x = 1", new_text="x = 2")
        self.assertIn("apparaît 2 fois", resultat)
        self.assertIn("replace_all", resultat)
        sandbox.files.write.assert_not_called()

    def test_edit_file_replace_all_ne_depasse_pas_la_limite_de_taille(self):
        # Limite de 1024 octets (le minimum accepté) : le fichier de 800 octets passe, pas son résultat.
        sandbox, resultat = self._edition(
            "a\n" * 400, configuration={"max_file_bytes": 1024}, old_text="a", new_text="a" * 100, replace_all=True,
        )
        self.assertIn("dépasserait la limite", resultat)
        sandbox.files.write.assert_not_called()

    def test_search_files_glob_passe_avant_les_exclusions_de_secrets(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._resultat_commande", return_value="x") as executer:
            _executer_action(sandbox, "search_files", "python", "", "", "", "", {}, pattern="TODO", glob="*.py")
        commande = executer.call_args.args[1]
        self.assertIn("--include='*.py'", commande)
        # Avec GNU grep le dernier motif qui correspond l'emporte : include doit venir avant les exclusions.
        self.assertLess(commande.index("--include='*.py'"), commande.index("--exclude='.env'"))

    def test_search_files_sans_glob_n_ajoute_pas_de_filtre(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._resultat_commande", return_value="x") as executer:
            _executer_action(sandbox, "search_files", "python", "", "", "", "", {}, pattern="TODO")
        self.assertNotIn("--include", executer.call_args.args[1])

    def test_search_files_refuse_un_glob_avec_chemin(self):
        sandbox = MagicMock()
        for glob in ("src/*.py", "..", "a" * 300):
            with self.subTest(glob=glob[:20]):
                with patch("core.outils_execution_code._resultat_commande") as executer:
                    resultat = _executer_action(sandbox, "search_files", "python", "", "", "", "", {}, pattern="TODO", glob=glob)
                self.assertIn("filtre glob", resultat)
                executer.assert_not_called()

    def test_search_files_coupe_les_lignes_trop_longues_sans_toucher_au_code_de_grep(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._resultat_commande", return_value="x") as executer:
            _executer_action(sandbox, "search_files", "python", "", "", "", "", {}, pattern="TODO")
        commande = executer.call_args.args[1]
        self.assertIn("LC_ALL=C.UTF-8 sed -E", commande)
        self.assertIn(".{400}", commande)
        # Le code de sortie lu est celui de grep (premier élément du tube), pas celui des sed.
        self.assertIn("PIPESTATUS[0]", commande)

    def test_la_lecture_par_plage_n_utilise_plus_de_tiret_long(self):
        sandbox = MagicMock()
        with patch("core.outils_execution_code._taille_fichier", return_value=10), patch("core.outils_execution_code._resultat_commande", return_value="1\tligne"):
            resultat = _executer_action(sandbox, "read_file", "python", "", "", "a.py", "", {}, start_line=1, end_line=2)
        self.assertNotIn(chr(0x2014), resultat)
        self.assertIn("a.py : lignes 1 à 2", resultat)

    def test_actions_workspace_reutilisent_les_reservations_existantes(self):
        self.assertEqual(_action_pour_reservation("edit_file"), "write_file")
        self.assertEqual(_action_pour_reservation("search_files"), "read_file")
        self.assertEqual(_action_pour_reservation("find_files"), "read_file")


def _grep_et_sed_gnu_disponibles():
    import shutil
    import subprocess
    if not shutil.which("grep") or not shutil.which("sed"):
        return False
    try:
        sortie = subprocess.run(["grep", "-V"], capture_output=True, text=True).stdout
        return "GNU" in sortie
    except Exception:
        return False


@unittest.skipUnless(_grep_et_sed_gnu_disponibles(), "grep et sed GNU requis")
class TestRechercheDansUnVraiDossier(unittest.TestCase):
    """Lance la vraie commande de search_files sur un dossier temporaire (le workspace est simulé)."""

    def setUp(self):
        import subprocess
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        racine = self._tmp.name
        for chemin, contenu in {
            "src/a.py": "TODO dans a\n",
            "src/b.txt": "TODO dans b\n",
            "src/long.js": "TODO " + "x" * 3000 + "\nTODO court\n",
            "src/accentue.py": "TODO " + "é" * 600 + "\n",
            ".env": "TODO secret env\n",
            "cle.pem": "TODO secret pem\n",
            "node_modules/m/i.py": "TODO dependance\n",
        }.items():
            complet = os.path.join(racine, chemin)
            os.makedirs(os.path.dirname(complet), exist_ok=True)
            with open(complet, "w", encoding="utf-8") as f:
                f.write(contenu)

        def lancer(commande, timeout=None, request_timeout=None):
            traduite = commande.replace("/home/user", racine)
            r = subprocess.run(traduite, shell=True, capture_output=True, text=True)
            return SimpleNamespace(stdout=r.stdout + r.stderr, stderr="", exit_code=r.returncode)

        self.sandbox = MagicMock()
        self.sandbox.commands.run.side_effect = lancer

    def _chercher(self, pattern="TODO", **options):
        return _executer_action(self.sandbox, "search_files", "python", "", "", "", "", {}, pattern=pattern, **options)

    def test_le_glob_limite_la_recherche_aux_fichiers_voulus(self):
        resultat = self._chercher(glob="*.py")
        self.assertIn("src/a.py:1:TODO dans a", resultat)
        self.assertNotIn("b.txt", resultat)

    def test_un_glob_ne_peut_pas_rouvrir_un_fichier_secret(self):
        for glob in (".env", "*.pem", "*"):
            with self.subTest(glob=glob):
                resultat = self._chercher(glob=glob)
                self.assertNotIn("secret", resultat)
                self.assertNotIn("node_modules", resultat)

    def test_les_secrets_restent_exclus_sans_glob(self):
        resultat = self._chercher()
        self.assertNotIn("secret", resultat)
        self.assertIn("src/a.py", resultat)

    def test_une_ligne_minifiee_est_coupee_et_les_autres_resultats_restent_visibles(self):
        resultat = self._chercher(glob="*.js")
        self.assertIn("[ligne coupée]", resultat)
        self.assertIn("src/long.js:2:TODO court", resultat)
        self.assertLess(max(len(ligne) for ligne in resultat.splitlines()), 450)

    def test_la_coupe_ne_casse_jamais_un_caractere_accentue(self):
        resultat = self._chercher(glob="accentue.py")
        self.assertIn("[ligne coupée]", resultat)
        resultat.encode("utf-8")
        self.assertNotIn("�", resultat)

    def test_aucun_resultat_est_signale_sans_erreur(self):
        resultat = self._chercher(pattern="introuvable_xyz")
        self.assertEqual(resultat, "Aucun résultat.")


class TestLibellesDesActionsDeCodage(unittest.TestCase):
    def test_chaque_action_de_codage_a_sa_traduction_anglaise(self):
        from core.libelles_outils_anglais import LIBELLES_OUTILS_EN
        from core.registre_outils import REGISTRE_AFFICHAGE_OUTILS
        for action in ("edit_file", "search_files", "find_files", "read_file", "write_file", "list_files"):
            with self.subTest(action=action):
                libelle = REGISTRE_AFFICHAGE_OUTILS[f"gerer_execution_code:{action}"]["label"]
                self.assertIn(libelle, LIBELLES_OUTILS_EN)


class TestSchemaDeLOutil(unittest.TestCase):
    """Ce qui est annoncé au modèle doit exister dans le code."""

    def test_replace_all_et_glob_sont_annonces_au_modele(self):
        proprietes = self._schema()["properties"]
        self.assertEqual(proprietes["replace_all"]["type"], "boolean")
        self.assertEqual(proprietes["glob"]["type"], "string")

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
        self.assertTrue({"edit_file", "search_files", "find_files"}.issubset(set(actions)))
        # network ne passe jamais par execution_code_reserver : la liste blanche SQL n'a pas à la contenir.
        with open("migrations/2026_10_23_execution_code_e2b.sql", encoding="utf-8") as fichier:
            migration = fichier.read()
        # importer_fichier (27/10/2026) est réservé comme une écriture de fichier (write_file) : le code
        # envoie p_action = write_file, la liste blanche SQL n'a donc pas à la contenir non plus.
        alias_reservation = {
            "edit_file": "write_file",
            "search_files": "read_file",
            "find_files": "read_file",
        }
        for action in actions:
            if action not in ("network", "demander_acces_reseau", "importer_fichier"):
                self.assertIn(f"'{alias_reservation.get(action, action)}'", migration)
        self.assertIn("'github.com'", migration)

    def test_les_langages_non_implementes_ne_sont_pas_annonces(self):
        langages = self._schema()["properties"]["language"]["enum"]
        self.assertEqual(sorted(langages), ["bash", "javascript", "python", "typescript"])


if __name__ == "__main__":
    unittest.main()
