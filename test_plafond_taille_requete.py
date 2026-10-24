"""Plafond de taille de requete du chat et reglages des plafonds : tests sans base ni reseau.

Dependances minimales (comme la CI) : fastapi, slowapi, requests, httpx. Les tests qui ont besoin de
tout le projet (modele de requete du chat, branchement dans api.main) sont dans test_plafonds_chat.py.
"""
import importlib
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from core import plafonds_reglables as reglages
from core.localisation import MiddlewareLangueErreurs
from core.plafond_taille_requete import PlafondTailleRequete


class ReglagesParVariable(unittest.TestCase):
    def tearDown(self):
        with patch.dict(os.environ):
            for nom in [n for n in os.environ if n.startswith(("CLASSINUS_CHAT_", "CLASSINUS_TACHE_"))]:
                del os.environ[nom]
            importlib.reload(reglages)

    def _recharger(self, **env):
        with patch.dict(os.environ, env):
            return importlib.reload(reglages)

    def test_valeurs_par_defaut(self):
        r = self._recharger()
        self.assertEqual(
            (r.PLAFOND_OUTILS_PAR_MESSAGE, r.PLAFOND_IMAGES_JOINTES, r.PLAFOND_ZIPS_JOINTS, r.TAILLE_MAX_REQUETE_CHAT_MO),
            (50, 30, 20, 100),
        )
        self.assertEqual(r.AGE_TACHE_PERIMEE.total_seconds(), 2 * 3600)

    def test_valeurs_reglees(self):
        r = self._recharger(
            CLASSINUS_CHAT_MAX_OUTILS_PAR_MESSAGE="80",
            CLASSINUS_CHAT_MAX_IMAGES_JOINTES="40",
            CLASSINUS_CHAT_MAX_ZIPS_JOINTS="25",
            CLASSINUS_CHAT_TAILLE_MAX_REQUETE_MO="250",
            CLASSINUS_TACHE_PERIMEE_HEURES="4",
        )
        self.assertEqual((r.PLAFOND_OUTILS_PAR_MESSAGE, r.PLAFOND_IMAGES_JOINTES, r.PLAFOND_ZIPS_JOINTS), (80, 40, 25))
        self.assertEqual(r.TAILLE_MAX_REQUETE_CHAT_MO, 250)
        self.assertEqual(r.AGE_TACHE_PERIMEE.total_seconds(), 4 * 3600)

    def test_valeurs_invalides_retombent_sur_le_defaut(self):
        for invalide in ("abc", "", "0", "-5", "  "):
            with self.subTest(valeur=invalide):
                r = self._recharger(CLASSINUS_CHAT_TAILLE_MAX_REQUETE_MO=invalide, CLASSINUS_CHAT_MAX_IMAGES_JOINTES=invalide)
                self.assertEqual((r.TAILLE_MAX_REQUETE_CHAT_MO, r.PLAFOND_IMAGES_JOINTES), (100, 30))

    def test_delai_des_taches_utilise_la_configuration(self):
        from core import taches_file_attente

        self.assertEqual(taches_file_attente._AGE_TACHE_PERIMEE, reglages.AGE_TACHE_PERIMEE)


def _application(taille_max_mo=1, avec_traduction_et_cors=True):
    app = FastAPI()

    @app.post("/api/chat")
    async def chat(request: Request):
        corps = await request.body()
        return {"octets": len(corps)}

    @app.post("/api/autre")
    async def autre(request: Request):
        return {"octets": len(await request.body())}

    @app.get("/api/chat")
    async def lire():
        return {"ok": True}

    # Meme ordre que api/main.py : le plafond est le plus interne.
    app.add_middleware(PlafondTailleRequete, prefixes=("/api/chat",), taille_max_mo=taille_max_mo)
    if avec_traduction_et_cors:
        app.add_middleware(MiddlewareLangueErreurs)
        app.add_middleware(CORSMiddleware, allow_origins=["https://classinus.test"], allow_methods=["*"], allow_headers=["*"])
    return app


MO = 1024 * 1024


class PlafondTailleRequeteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(_application(1))

    def test_petite_requete_passe(self):
        r = self.client.post("/api/chat", content=b"a" * 1000)
        self.assertEqual((r.status_code, r.json()["octets"]), (200, 1000))

    def test_requete_au_plafond_exact_passe(self):
        r = self.client.post("/api/chat", content=b"a" * MO)
        self.assertEqual(r.status_code, 200)

    def test_content_length_trop_grand_refuse_413_structure(self):
        r = self.client.post("/api/chat", content=b"a" * (MO + 1))
        self.assertEqual(r.status_code, 413)
        detail = r.json()["detail"]
        self.assertEqual(detail["code"], "REQUETE_TROP_VOLUMINEUSE")
        self.assertEqual(detail["params"], {"taille_max": 1})
        self.assertIn("1 Mo", detail["message"])

    def test_envoi_par_morceaux_sans_content_length_refuse(self):
        def morceaux():
            for _ in range(3):
                yield b"a" * (MO // 2)

        r = self.client.post("/api/chat", content=morceaux())
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["detail"]["code"], "REQUETE_TROP_VOLUMINEUSE")

    def test_envoi_par_morceaux_sous_le_plafond_passe(self):
        def morceaux():
            for _ in range(3):
                yield b"a" * 1000

        r = self.client.post("/api/chat", content=morceaux())
        self.assertEqual((r.status_code, r.json()["octets"]), (200, 3000))

    def test_autres_routes_et_methodes_non_concernees(self):
        self.assertEqual(self.client.post("/api/autre", content=b"a" * (2 * MO)).status_code, 200)
        self.assertEqual(self.client.get("/api/chat").status_code, 200)

    def test_refus_porte_les_en_tetes_cors(self):
        r = self.client.post("/api/chat", content=b"a" * (MO + 1), headers={"Origin": "https://classinus.test"})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.headers.get("access-control-allow-origin"), "https://classinus.test")

    def test_refus_traduit_en_anglais(self):
        r = self.client.post("/api/chat", content=b"a" * (MO + 1), headers={"Accept-Language": "en"})
        self.assertEqual(r.status_code, 413)
        self.assertIn("maximum accepted size (1 MB)", r.json()["detail"]["message"])

    def test_messages_fr_et_en_declares(self):
        from core.erreurs import MESSAGES_EN, MESSAGES_FR

        self.assertIn("REQUETE_TROP_VOLUMINEUSE", MESSAGES_FR)
        self.assertIn("REQUETE_TROP_VOLUMINEUSE", MESSAGES_EN)



if __name__ == "__main__":
    unittest.main()
