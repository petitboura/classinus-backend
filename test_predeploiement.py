"""Tests de la commande de pré-déploiement : la synchronisation ne bloque jamais, le test Gemini garde la main."""
import logging
import os
import unittest
from unittest import mock

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)

from scripts import predeploiement as P  # noqa: E402
from scripts import synchroniser_skills_plateforme as SYNC  # noqa: E402

BILAN = {"crees": [], "mis_a_jour": [], "inchanges": [], "absents": [], "erreurs": []}


class TestPredeploiement(unittest.TestCase):
    def test_la_synchronisation_passe_avant_le_test_gemini_et_le_code_de_gemini_decide(self):
        ordre = []
        with mock.patch.object(SYNC, "synchroniser", side_effect=lambda a: ordre.append("synchro") or BILAN) as sy, \
                mock.patch.object(SYNC, "afficher"), \
                mock.patch.object(P.subprocess, "run", side_effect=lambda *a, **k: ordre.append("gemini") or mock.Mock(returncode=0)):
            self.assertEqual(P.main(), 0)
        sy.assert_called_once_with(True)
        self.assertEqual(ordre, ["synchro", "gemini"])

    def test_un_echec_du_test_gemini_fait_echouer_le_deploiement_comme_avant(self):
        with mock.patch.object(SYNC, "synchroniser", return_value=BILAN), mock.patch.object(SYNC, "afficher"), \
                mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=1)):
            self.assertEqual(P.main(), 1)

    def test_une_erreur_de_synchronisation_ne_bloque_jamais_le_deploiement(self):
        with mock.patch.object(SYNC, "synchroniser", side_effect=RuntimeError("R2 injoignable")), \
                mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(P.main(), 0)
        run.assert_called_once()

    def test_des_erreurs_dans_le_bilan_ne_bloquent_pas_non_plus(self):
        bilan = dict(BILAN, erreurs=["documents-word : l'écriture a échoué (voir les logs)."])
        with mock.patch.object(SYNC, "synchroniser", return_value=bilan), mock.patch.object(SYNC, "afficher"), \
                mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=0)):
            self.assertEqual(P.main(), 0)

    def test_la_variable_peut_desactiver_la_synchronisation(self):
        for valeur in ("non", "NON", "0", "false", "off"):
            with self.subTest(valeur=valeur), mock.patch.dict(os.environ, {"SKILLS_PLATEFORME_SYNCHRO": valeur}), \
                    mock.patch.object(SYNC, "synchroniser") as sy, \
                    mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=0)):
                self.assertEqual(P.main(), 0)
                sy.assert_not_called()

    def test_sans_script_gemini_l_etape_est_sautee(self):
        with mock.patch.object(SYNC, "synchroniser", return_value=BILAN), mock.patch.object(SYNC, "afficher"), \
                mock.patch.object(P, "RACINE", P.RACINE / "dossier-inexistant"), \
                mock.patch.object(P.subprocess, "run") as run:
            self.assertEqual(P.main(), 0)
        run.assert_not_called()

    def test_le_script_gemini_est_lance_avec_le_meme_python_depuis_la_racine(self):
        with mock.patch.object(SYNC, "synchroniser", return_value=BILAN), mock.patch.object(SYNC, "afficher"), \
                mock.patch.object(P.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            P.main()
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], P.sys.executable)
        self.assertTrue(args[0][1].endswith("scripts/verifier_gemini_live.py"))
        self.assertEqual(kwargs["cwd"], str(P.RACINE))


if __name__ == "__main__":
    unittest.main()
