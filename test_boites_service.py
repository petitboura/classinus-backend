"""Tests hors ligne du service de boîtes (faux Docker, aucun conteneur réel)."""
import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from boites_service import app as app_mod
from boites_service import proxy as proxy_mod
from boites_service.docker_cli import ErreurDocker, chemin_sur, id_valide

AUTH = {"Authorization": "Bearer jeton-test"}
ID = "a" * 32


class FauxDocker:
    def __init__(self):
        self.boites = {}
        self.navigateurs = {}
        self.appels = []

    def lister(self):
        return list(self.boites)

    def etat(self, boite_id):
        return self.boites.get(boite_id)

    def adresse(self, boite_id):
        return "172.20.0.5" if boite_id in self.boites else None

    def creer(self, boite_id, navigateur=False, utilisateur=""):
        self.boites[boite_id] = "running"
        if navigateur:
            self.navigateurs[boite_id] = (utilisateur, 0)

    def lister_navigateurs(self, utilisateur=""):
        return [(i, c) for i, (u, c) in self.navigateurs.items() if not utilisateur or u == utilisateur]

    def demarrer(self, boite_id):
        self.boites[boite_id] = "running"

    def arreter(self, boite_id):
        self.boites[boite_id] = "exited"

    def supprimer(self, boite_id):
        self.boites.pop(boite_id, None)
        self.navigateurs.pop(boite_id, None)

    def executer(self, boite_id, commande, delai):
        self.appels.append((commande, delai))
        return {"stdout": "ok", "stderr": "", "exit_code": 0}

    def lire(self, boite_id, chemin):
        return b"contenu"

    def ecrire(self, boite_id, chemin, octets):
        self.appels.append((chemin, octets))


class ServiceBoites(unittest.TestCase):
    def setUp(self):
        for p in (patch.dict(os.environ, {"BOITES_TOKEN": "jeton-test"}), patch.object(app_mod, "docker", FauxDocker()),
                  patch.object(app_mod, "registre", proxy_mod.RegistreBoites())):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app_mod.app)
        self.docker = app_mod.docker

    def test_sans_jeton_ou_avec_mauvais_jeton_tout_est_refuse(self):
        self.assertEqual(self.client.post("/boites", json={}).status_code, 401)
        self.assertEqual(self.client.post("/boites", json={}, headers={"Authorization": "Bearer faux"}).status_code, 401)
        self.assertEqual(self.client.get("/boites").status_code, 401)

    def test_refuse_de_demarrer_sans_jeton_configure(self):
        with patch.dict(os.environ, {"BOITES_TOKEN": ""}), self.assertRaises(RuntimeError):
            app_mod._token_attendu()

    def test_cycle_complet_creation_commande_fichier_pause_reprise_destruction(self):
        r = self.client.post("/boites", json={"timeout": 600}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        boite_id = r.json()["id"]
        # Sans règle, aucun domaine n'est autorisé pour cette boîte.
        self.assertEqual(app_mod.registre.domaines("172.20.0.5"), [])
        r = self.client.post(f"/boites/{boite_id}/commande", json={"commande": "echo ok", "timeout": 5}, headers=AUTH)
        self.assertEqual(r.json()["stdout"], "ok")
        self.assertIn(("echo ok", 5), self.docker.appels)
        r = self.client.put(f"/boites/{boite_id}/fichier", params={"chemin": "/home/user/a.txt"}, content=b"xyz", headers=AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertIn(("/home/user/a.txt", b"xyz"), self.docker.appels)
        self.assertEqual(self.client.get(f"/boites/{boite_id}/fichier", params={"chemin": "/home/user/a.txt"}, headers=AUTH).content, b"contenu")
        self.assertEqual(self.client.post(f"/boites/{boite_id}/pause", headers=AUTH).status_code, 200)
        self.assertEqual(self.docker.boites[boite_id], "exited")
        self.assertIsNone(app_mod.registre.domaines("172.20.0.5"))
        self.assertEqual(self.client.post(f"/boites/{boite_id}/connexion", json={}, headers=AUTH).status_code, 200)
        self.assertEqual(self.docker.boites[boite_id], "running")
        self.assertEqual(self.client.delete(f"/boites/{boite_id}", headers=AUTH).status_code, 200)
        self.assertNotIn(boite_id, self.docker.boites)

    def test_le_reseau_se_regle_par_boite(self):
        boite_id = self.client.post("/boites", json={}, headers=AUTH).json()["id"]
        r = self.client.put(f"/boites/{boite_id}/reseau", json={"allow_out": ["pypi.org"]}, headers=AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(app_mod.registre.domaines("172.20.0.5"), ["pypi.org"])

    def test_boite_inconnue_donne_404(self):
        for methode, chemin in (("post", f"/boites/{ID}/connexion"), ("post", f"/boites/{ID}/pause"),
                                ("put", f"/boites/{ID}/reseau")):
            r = getattr(self.client, methode)(chemin, json={"allow_out": []}, headers=AUTH)
            self.assertEqual(r.status_code, 404, chemin)

    def test_identifiant_invalide_donne_400(self):
        r = self.client.post("/boites/pas-un-id/commande", json={"commande": "ls"}, headers=AUTH)
        self.assertEqual(r.status_code, 400)

    def test_chemin_hors_du_dossier_de_travail_refuse(self):
        self.client.post("/boites", json={}, headers=AUTH)
        boite_id = self.docker.lister()[0]
        for chemin in ("/etc/passwd", "/home/user/../../etc/shadow", "relatif.txt", "/home/userx/a"):
            r = self.client.get(f"/boites/{boite_id}/fichier", params={"chemin": chemin}, headers=AUTH)
            self.assertEqual(r.status_code, 400, chemin)

    def test_capacite_maximale(self):
        with patch.dict(os.environ, {"BOITES_MAX": "2"}):
            self.assertEqual(self.client.post("/boites", json={}, headers=AUTH).status_code, 200)
            self.assertEqual(self.client.post("/boites", json={}, headers=AUTH).status_code, 200)
            self.assertEqual(self.client.post("/boites", json={}, headers=AUTH).status_code, 429)


class Validation(unittest.TestCase):
    def test_chemins(self):
        self.assertEqual(chemin_sur("/home/user/a/../b.txt"), "/home/user/b.txt")
        self.assertEqual(chemin_sur("/tmp/x"), "/tmp/x")
        for mauvais in ("/etc/passwd", "/home/user/../x", "", "a/b", "/proc/1/environ"):
            with self.assertRaises(ErreurDocker, msg=mauvais):
                chemin_sur(mauvais)

    def test_identifiants(self):
        self.assertEqual(id_valide("ab" * 16), "ab" * 16)
        for mauvais in ("", "ABC", "a;rm -rf /", "../x", "a" * 64):
            with self.assertRaises(ErreurDocker, msg=mauvais):
                id_valide(mauvais)


class DecisionsDuProxy(unittest.TestCase):
    def test_domaines(self):
        regles = ["pypi.org", "*.pythonhosted.org"]
        self.assertTrue(proxy_mod.domaine_autorise("pypi.org", regles))
        self.assertTrue(proxy_mod.domaine_autorise("PyPI.org.", regles))
        self.assertTrue(proxy_mod.domaine_autorise("files.pythonhosted.org", regles))
        self.assertFalse(proxy_mod.domaine_autorise("pythonhosted.org", regles))
        self.assertFalse(proxy_mod.domaine_autorise("evilpypi.org", regles))
        self.assertFalse(proxy_mod.domaine_autorise("pypi.org.evil.com", regles))
        self.assertFalse(proxy_mod.domaine_autorise("1.2.3.4", ["1.2.3.4"]))
        self.assertFalse(proxy_mod.domaine_autorise("pypi.org", []))

    def test_adresses_publiques_seulement(self):
        for privee in ("127.0.0.1", "10.0.0.5", "172.20.0.5", "192.168.1.1", "169.254.169.254", "::1", "fe80::1", "::ffff:10.0.0.1"):
            self.assertFalse(proxy_mod.adresse_publique(privee), privee)
        self.assertTrue(proxy_mod.adresse_publique("8.8.8.8"))


class ProxyDeBout(unittest.IsolatedAsyncioTestCase):
    async def _demander(self, registre, requete: bytes, source="127.0.0.1") -> bytes:
        serveur = await asyncio.start_server(proxy_mod.fabriquer_gestionnaire(registre), "127.0.0.1", 0)
        port = serveur.sockets[0].getsockname()[1]
        lecteur, ecrivain = await asyncio.open_connection("127.0.0.1", port)
        ecrivain.write(requete)
        await ecrivain.drain()
        try:
            return await asyncio.wait_for(lecteur.read(200), 5)
        finally:
            ecrivain.close()
            serveur.close()

    async def test_refus_domaine_non_autorise_port_interdit_et_boite_inconnue(self):
        registre = proxy_mod.RegistreBoites()
        registre.regler("x", "127.0.0.1", ["ok.test"])
        for requete in (b"CONNECT autre.test:443 HTTP/1.1\r\n\r\n", b"CONNECT ok.test:22 HTTP/1.1\r\n\r\n",
                        b"CONNECT 8.8.8.8:443 HTTP/1.1\r\n\r\n"):
            self.assertIn(b"403", await self._demander(registre, requete), requete)
        self.assertIn(b"403", await self._demander(proxy_mod.RegistreBoites(), b"CONNECT ok.test:443 HTTP/1.1\r\n\r\n"))

    async def test_refus_si_le_nom_autorise_pointe_vers_le_reseau_interne(self):
        registre = proxy_mod.RegistreBoites()
        registre.regler("x", "127.0.0.1", ["ok.test"])
        with patch.object(proxy_mod, "_resoudre_public", return_value=None):
            self.assertIn(b"403", await self._demander(registre, b"CONNECT ok.test:443 HTTP/1.1\r\n\r\n"))

    async def test_passage_autorise_vers_un_serveur_public_simule(self):
        async def echo(lecteur, ecrivain):
            ecrivain.write(b"bonjour" + await lecteur.read(10))
            await ecrivain.drain()
            ecrivain.close()
        distant = await asyncio.start_server(echo, "127.0.0.1", 0)
        port_distant = distant.sockets[0].getsockname()[1]
        registre = proxy_mod.RegistreBoites()
        registre.regler("x", "127.0.0.1", ["ok.test"])

        async def faux_public(hote, port):
            return "127.0.0.1"
        with patch.object(proxy_mod, "_resoudre_public", faux_public), \
                patch.object(proxy_mod, "PORTS_AUTORISES", {port_distant}):
            serveur = await asyncio.start_server(proxy_mod.fabriquer_gestionnaire(registre), "127.0.0.1", 0)
            port = serveur.sockets[0].getsockname()[1]
            lecteur, ecrivain = await asyncio.open_connection("127.0.0.1", port)
            ecrivain.write(f"CONNECT ok.test:{port_distant} HTTP/1.1\r\n\r\n".encode())
            await ecrivain.drain()
            self.assertIn(b"200", await asyncio.wait_for(lecteur.readuntil(b"\r\n\r\n"), 5))
            ecrivain.write(b"!")
            await ecrivain.drain()
            self.assertEqual(await asyncio.wait_for(lecteur.read(100), 5), b"bonjour!")
            ecrivain.close()
            serveur.close()
        distant.close()


if __name__ == "__main__":
    unittest.main()
