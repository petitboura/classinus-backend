"""Tests hors ligne des protections et commandes de l'outil E2B."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.outils_execution_code import (
    _chemin_relatif_sur,
    _commande_langage,
    _domaines_autorises,
    _options_reseau,
    _resultat_commande,
    _utilisateur_autorise,
)


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


if __name__ == "__main__":
    unittest.main()
