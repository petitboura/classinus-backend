"""Tests hors ligne des commandes longues en arrière-plan de l'outil d'exécution de code.

Les actions run_background, command_status et command_stop (02/11/2026, demande de Bourama)
lancent une commande détachée dont la sortie va dans un journal. Ces tests exécutent le vrai
bash dans un dossier temporaire, avec un faux sandbox : rien n'est écrit hors de ce dossier,
aucun appel réseau, aucun appel à E2B.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import outils_execution_code as module
from core.outils_execution_code import (
    _executer_action,
    _id_tache_valide,
    gerer_execution_code,
)

CONFIGURATION = {"max_output_chars": 20000, "inactivity_seconds": 300, "max_files_per_download": 50}


class _Commandes:
    """Exécute vraiment la commande avec bash, comme le fait le sandbox."""

    def __init__(self):
        self.historique = []

    def run(self, commande, timeout=None, request_timeout=None):
        self.historique.append(commande)
        p = subprocess.run(["bash", "-lc", commande], capture_output=True, text=True, timeout=30)
        return SimpleNamespace(stdout=p.stdout, stderr=p.stderr, exit_code=p.returncode)


def _bash_et_setsid_disponibles():
    return bool(shutil.which("bash") and shutil.which("setsid"))


@unittest.skipUnless(_bash_et_setsid_disponibles(), "bash et setsid sont nécessaires")
class TestCommandesLongues(unittest.TestCase):
    def setUp(self):
        self.racine = tempfile.mkdtemp(prefix="classinus_test_")
        self.addCleanup(shutil.rmtree, self.racine, True)
        patcher = patch.multiple(
            module, _ROOT=self.racine, _DOSSIER_TACHES=f"{self.racine}/.classinus_taches"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.commandes = _Commandes()
        self.sandbox = SimpleNamespace(commands=self.commandes)
        self.identifiants = []
        self.addCleanup(self._tout_arreter)

    def _tout_arreter(self):
        for identifiant in self.identifiants:
            try:
                _executer_action(self.sandbox, "command_stop", "python", "", "", "", "", CONFIGURATION, job_id=identifiant)
            except Exception:
                pass

    def _agir(self, action, command="", job_id=""):
        return _executer_action(
            self.sandbox, action, "python", "", command, "", "", CONFIGURATION, job_id=job_id
        )

    def _lancer(self, command):
        resultat = self._agir("run_background", command=command)
        self.assertIn("job_id", resultat)
        identifiant = resultat.split("job_id ")[1].split()[0].strip()
        self.identifiants.append(identifiant)
        return identifiant

    def _attendre(self, identifiant, mot, delai=10):
        fin = time.monotonic() + delai
        while time.monotonic() < fin:
            etat = self._agir("command_status", job_id=identifiant)
            if mot in etat:
                return etat
            time.sleep(0.2)
        self.fail(f"Etat '{mot}' jamais atteint, dernier état : {etat}")

    def test_le_lancement_rend_la_main_tout_de_suite(self):
        debut = time.monotonic()
        self._lancer("sleep 20")
        self.assertLess(time.monotonic() - debut, 5)

    def test_tache_terminee_avec_son_code_de_sortie_et_sa_sortie(self):
        identifiant = self._lancer("echo bonjour; echo erreur 1>&2; exit 3")
        etat = self._attendre(identifiant, "terminée")
        self.assertIn("code de sortie 3", etat)
        self.assertIn("bonjour", etat)
        self.assertIn("erreur", etat)

    def test_tache_en_cours_puis_arretee(self):
        identifiant = self._lancer("sleep 60")
        self.assertIn("en cours", self._agir("command_status", job_id=identifiant))
        self.assertIn("arrêtée", self._agir("command_stop", job_id=identifiant))
        etat = self._agir("command_status", job_id=identifiant)
        self.assertIn("arrêtée à ta demande", etat)

    def test_arreter_ne_laisse_aucun_processus(self):
        identifiant = self._lancer("sleep 61 && echo jamais")
        self._agir("command_stop", job_id=identifiant)
        survivants = subprocess.run(
            "ps -eo args | grep -E '[s]leep 61'", shell=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(survivants, "")

    def test_arreter_une_tache_terminee_est_sans_danger(self):
        identifiant = self._lancer("exit 0")
        self._attendre(identifiant, "terminée")
        self.assertIn("déjà terminée", self._agir("command_stop", job_id=identifiant))

    def test_tache_tuee_de_l_exterieur_est_dite_interrompue(self):
        identifiant = self._lancer("sleep 62")
        with open(f"{self.racine}/.classinus_taches/{identifiant}/pid", encoding="utf-8") as fichier:
            pid = fichier.read().strip()
        subprocess.run(f"kill -KILL -{pid}", shell=True)
        etat = self._attendre(identifiant, "interrompue")
        self.assertIn("interrompue", etat)

    def test_identifiant_inconnu(self):
        self.assertIn("Aucune tâche", self._agir("command_status", job_id="deadbeef"))
        self.assertIn("Aucune tâche", self._agir("command_stop", job_id="deadbeef"))

    def test_identifiants_dangereux_refuses_sans_toucher_au_shell(self):
        for mauvais in ("x; rm -rf /", "../../etc", "ABCDEF12", "abc", "", "deadbeef0", "dead beef"):
            with self.subTest(job_id=mauvais):
                self.commandes.historique.clear()
                for action in ("command_status", "command_stop"):
                    self.assertIn("job_id", self._agir(action, job_id=mauvais))
                self.assertEqual(self.commandes.historique, [])

    def test_longue_sortie_gardee_par_la_fin_et_bornee(self):
        identifiant = self._lancer("seq 1 30000")
        etat = self._attendre(identifiant, "terminée")
        # Les messages sont courts exprès : un échec ne doit pas recopier 20 000 caractères.
        self.assertLessEqual(len(etat), CONFIGURATION["max_output_chars"], "sortie non bornée")
        # La FIN du journal est gardée (l'erreur d'un build y est), jamais son début.
        self.assertTrue(etat.rstrip().endswith("30000"), "la fin du journal a été coupée")
        self.assertNotIn("sortie tronquée", etat)
        self.assertIn("derniers caractères", etat)
        self.assertNotIn("\n1\n2\n3\n", etat, "le début du journal ne devrait plus y être")

    def test_commande_avec_guillemets_et_dollars_est_transmise_telle_quelle(self):
        identifiant = self._lancer("X='a b'; echo \"[$X] $((2+3))\"")
        self.assertIn("[a b] 5", self._attendre(identifiant, "terminée"))

    def test_un_exit_dans_la_commande_ne_masque_pas_le_code_de_sortie(self):
        identifiant = self._lancer("exit 7")
        self.assertIn("code de sortie 7", self._attendre(identifiant, "terminée"))

    def test_commande_vide_ou_trop_longue_refusee(self):
        self.assertIn("Aucune commande", self._agir("run_background", command="   "))
        trop_long = "a" * (10000 + 1)
        self.assertIn("limite configurée", self._agir("run_background", command=trop_long))

    def test_les_journaux_ne_polluent_ni_les_listes_ni_les_archives(self):
        self._lancer("echo trace")
        for action in ("list_files", "find_files"):
            self.commandes.historique.clear()
            _executer_action(
                self.sandbox, action, "python", "", "", ".", "", CONFIGURATION, pattern="*.log"
            )
            self.assertIn(".classinus_taches", self.commandes.historique[0])
        self.commandes.historique.clear()
        _executer_action(self.sandbox, "search_files", "python", "", "", "", "", CONFIGURATION, pattern="x")
        self.assertIn(".classinus_taches", self.commandes.historique[0])


class TestIdentifiant(unittest.TestCase):
    def test_forme_stricte(self):
        self.assertTrue(_id_tache_valide("a1b2c3d4"))
        self.assertTrue(_id_tache_valide(" a1b2c3d4 "))
        for mauvais in ("", None, "a1b2c3d", "a1b2c3d45", "A1B2C3D4", "a1b2c3dg", "a1b2/3d4", "a1b2c3d4; ls"):
            with self.subTest(job_id=mauvais):
                self.assertFalse(_id_tache_valide(mauvais))


class TestValidationAvantReservation(unittest.TestCase):
    """Un appel invalide est refusé avant toute réservation : aucun quota ni sandbox consommé."""

    def _appeler(self, **arguments):
        with patch("core.outils_execution_code._identite_interne", return_value=("u", "c", None)), \
                patch.dict("os.environ", {"E2B_API_KEY": "cle-test"}), \
                patch("core.outils_execution_code._rpc_objet") as rpc, \
                patch("core.outils_execution_code._classe_sandbox") as classe:
            resultat = gerer_execution_code(ctx=MagicMock(), **arguments)
        rpc.assert_not_called()
        classe.assert_not_called()
        return resultat

    def test_run_background_sans_commande(self):
        self.assertIn("Aucune commande", self._appeler(action="run_background", command=""))

    def test_status_et_stop_sans_job_id_valide(self):
        for action in ("command_status", "command_stop"):
            for job_id in ("", "pas-un-id"):
                with self.subTest(action=action, job_id=job_id):
                    self.assertIn("job_id", self._appeler(action=action, job_id=job_id))


if __name__ == "__main__":
    unittest.main()
