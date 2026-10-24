"""Tests hors ligne des protections et commandes de l'outil E2B."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from e2b import CommandExitException

from core.outils_execution_code import (
    _chemin_relatif_sur,
    _commande_langage,
    _domaines_autorises,
    _executer_action,
    _options_reseau,
    _resultat_commande,
    _taille_fichier,
    _utilisateur_autorise,
    mcp_execution_code,
)


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


class TestAutorisationMajorite(unittest.TestCase):
    def _client_avec_profil(self, profil):
        client = MagicMock()
        resultat = (
            client.table.return_value.select.return_value.eq.return_value
            .maybe_single.return_value.execute.return_value
        )
        resultat.data = profil
        return client

    def test_seul_majeur_explicitement_confirme_est_autorise(self):
        for valeur, attendu in ((True, True), (False, False), (None, False)):
            with self.subTest(est_majeur=valeur):
                client = self._client_avec_profil({"est_majeur": valeur})
                with patch("core.outils_execution_code._client_supabase", return_value=client):
                    self.assertEqual(_utilisateur_autorise("utilisateur-test"), attendu)

    def test_profil_absent_est_refuse(self):
        client = self._client_avec_profil(None)
        with patch("core.outils_execution_code._client_supabase", return_value=client):
            self.assertFalse(_utilisateur_autorise("utilisateur-test"))

    def test_erreur_base_est_refusee(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = RuntimeError(
            "database unavailable"
        )
        with patch("core.outils_execution_code._client_supabase", return_value=client):
            self.assertFalse(_utilisateur_autorise("utilisateur-test"))


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

    def test_les_langages_non_implementes_ne_sont_pas_annonces(self):
        langages = self._schema()["properties"]["language"]["enum"]
        self.assertEqual(sorted(langages), ["bash", "javascript", "python", "typescript"])


if __name__ == "__main__":
    unittest.main()
