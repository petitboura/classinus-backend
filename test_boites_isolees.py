"""Tests hors ligne du fournisseur de boîtes Docker côté backend (aucun réseau, aucun Docker)."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from core import boites_isolees
from core.boites_isolees import BoiteDocker, ErreurBoite
from core.outils_execution_code import _executer_action, _resultat_commande

ENV_DOCKER = {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://boites.test", "BOITES_TOKEN": "secret"}


def _faux_service(gestionnaire):
    """Remplace le client HTTP par un transport simulé, et garde la trace des requêtes reçues."""
    recues = []

    def traiter(requete: httpx.Request):
        recues.append(requete)
        return gestionnaire(requete)

    def fabrique(delai=None):
        return httpx.Client(
            base_url="http://boites.test", transport=httpx.MockTransport(traiter),
            headers={"Authorization": "Bearer secret"},
        )

    return recues, patch.object(boites_isolees, "_client", fabrique)


class ChoixDuFournisseur(unittest.TestCase):
    def test_e2b_par_defaut_la_production_ne_change_pas(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(boites_isolees.fournisseur(), "e2b")
            self.assertIn("E2B_API_KEY", boites_isolees.raison_non_configuree())
        with patch.dict(os.environ, {"E2B_API_KEY": "k"}, clear=True):
            self.assertTrue(boites_isolees.configuree())

    def test_valeur_inconnue_garde_e2b(self):
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "autre"}, clear=True):
            self.assertEqual(boites_isolees.fournisseur(), "e2b")

    def test_docker_demande_url_et_jeton(self):
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker"}, clear=True):
            self.assertIn("BOITES_URL", boites_isolees.raison_non_configuree())
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x"}, clear=True):
            self.assertIn("BOITES_TOKEN", boites_isolees.raison_non_configuree())
        with patch.dict(os.environ, ENV_DOCKER, clear=True):
            self.assertTrue(boites_isolees.configuree())
            self.assertIs(boites_isolees.classe_sandbox(), BoiteDocker)

    def test_la_cle_e2b_seule_ne_suffit_pas_en_mode_docker(self):
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker", "E2B_API_KEY": "k"}, clear=True):
            self.assertFalse(boites_isolees.configuree())


class ClientBoiteDocker(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, ENV_DOCKER, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_creation_regle_le_reseau_avec_les_domaines_autorises(self):
        def service(req):
            if req.method == "POST" and req.url.path == "/boites":
                return httpx.Response(200, json={"id": "a" * 32})
            return httpx.Response(200, json={})
        recues, patcher = _faux_service(service)
        with patcher:
            boite = BoiteDocker.create(
                template="base", timeout=600, metadata={}, lifecycle={},
                network={"deny_out": ["0.0.0.0/0"], "allow_out": ["pypi.org", "*.python.org"]},
            )
        self.assertEqual(boite.sandbox_id, "a" * 32)
        reseau = [r for r in recues if r.url.path.endswith("/reseau")][0]
        self.assertEqual(json.loads(reseau.content), {"allow_out": ["pypi.org", "*.python.org"]})
        self.assertTrue(all(r.headers["Authorization"] == "Bearer secret" for r in recues))

    def test_une_boite_dont_le_reseau_echoue_est_detruite(self):
        def service(req):
            if req.url.path == "/boites" and req.method == "POST":
                return httpx.Response(200, json={"id": "b" * 32})
            if req.url.path.endswith("/reseau"):
                return httpx.Response(500)
            return httpx.Response(200, json={})
        recues, patcher = _faux_service(service)
        with patcher, self.assertRaises(ErreurBoite):
            BoiteDocker.create(network={"allow_out": []})
        self.assertTrue(any(r.method == "DELETE" for r in recues))

    def test_boite_absente_donne_404_comme_attendu_par_l_outil(self):
        _, patcher = _faux_service(lambda req: httpx.Response(404))
        with patcher, self.assertRaises(ErreurBoite) as ctx:
            BoiteDocker.connect("c" * 32, timeout=60, on_resume="reboot")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_capacite_atteinte_donne_429(self):
        _, patcher = _faux_service(lambda req: httpx.Response(429))
        with patcher, self.assertRaises(ErreurBoite) as ctx:
            BoiteDocker.create()
        self.assertEqual(ctx.exception.status_code, 429)

    def test_service_injoignable_donne_503(self):
        def tomber(req):
            raise httpx.ConnectError("coupé")
        _, patcher = _faux_service(tomber)
        with patcher, self.assertRaises(ErreurBoite) as ctx:
            BoiteDocker.kill("d" * 32)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_commande_renvoie_sortie_et_code_sans_lever(self):
        _, patcher = _faux_service(lambda req: httpx.Response(200, json={"stdout": "boum\n", "stderr": "", "exit_code": 3}))
        boite = BoiteDocker("e" * 32)
        with patcher:
            texte = _resultat_commande(boite, "python x.py", 10, 5000)
        self.assertIn("boum", texte)
        self.assertIn("Code de sortie : 3", texte)

    def test_lecture_et_ecriture_de_fichiers(self):
        stockage = {}

        def service(req):
            chemin = req.url.params["chemin"]
            if req.method == "PUT":
                stockage[chemin] = req.content
                return httpx.Response(200, json={})
            return httpx.Response(200, content=stockage[chemin])
        recues, patcher = _faux_service(service)
        boite = BoiteDocker("f" * 32)
        with patcher:
            boite.files.write("/home/user/a.txt", "héllo")
            self.assertEqual(boite.files.read("/home/user/a.txt", format="text"), "héllo")
            self.assertEqual(boite.files.read("/home/user/a.txt", format="bytes"), "héllo".encode())
            boite.files.write("/home/user/b.bin", b"\x00\x01")
            self.assertEqual(stockage["/home/user/b.bin"], b"\x00\x01")

    def test_action_write_file_de_l_outil_passe_par_la_boite_docker(self):
        stockage = {}

        def service(req):
            if req.method == "PUT":
                stockage[req.url.params["chemin"]] = req.content
            return httpx.Response(200, json={"stdout": "", "stderr": "", "exit_code": 0})
        _, patcher = _faux_service(service)
        with patcher:
            _executer_action(
                BoiteDocker("1" * 32), "write_file", "python", "", "", "dossier/note.txt", "contenu",
                {}, None, "", "", "", None, None, False, "", "",
            )
        self.assertEqual(stockage.get("/home/user/dossier/note.txt"), b"contenu")


if __name__ == "__main__":
    unittest.main()
