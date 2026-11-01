"""Tests du moteur de fond Higgsfield (31/10/2026).

Regle verrouillee : API toujours en premier, notre MCP partage uniquement
pour les fonctions absentes de l'API, aucun equivalent invente, estimation
en credits seulement. Aucun appel reseau ni base dans ces tests.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.higgsfield_capacites import (
    CAPACITES,
    OUTILS_MCP_AUTORISES,
    capacite_par_id,
)
from core.higgsfield_catalogue import MODELES_IMAGE, MODELES_VIDEO
from core.higgsfield_routeur import choisir_voie


class TestRouteur(unittest.TestCase):
    def test_api_en_premier_meme_si_mcp_disponible(self):
        choix = choisir_voie("video", api_disponible=True, mcp_disponible=True)
        self.assertEqual(choix["voie"], "api")

    def test_mcp_seulement_si_fonction_absente_api(self):
        choix = choisir_voie("audio_tts", api_disponible=True, mcp_disponible=True)
        self.assertEqual(choix["voie"], "mcp")

    def test_aucun_repli_api_pour_mcp_only(self):
        choix = choisir_voie("upscale_video", api_disponible=True, mcp_disponible=False)
        self.assertEqual(choix["voie"], "indisponible")

    def test_api_absente_rend_video_indisponible(self):
        choix = choisir_voie("image", api_disponible=False, mcp_disponible=True)
        self.assertEqual(choix["voie"], "indisponible")

    def test_capacite_inconnue_indisponible(self):
        choix = choisir_voie("fonction_inventee", api_disponible=True, mcp_disponible=True)
        self.assertEqual(choix["voie"], "indisponible")
        self.assertIsNone(choix["capacite"])


class TestRegistre(unittest.TestCase):
    def test_ids_uniques(self):
        ids = [c["id"] for c in CAPACITES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_capacites_api_pointent_sur_catalogue_reel(self):
        for capacite in CAPACITES:
            if capacite["voie"] != "api":
                continue
            for modele in capacite["modeles_api"]:
                self.assertTrue(
                    modele in MODELES_VIDEO or modele in MODELES_IMAGE,
                    f"{capacite['id']} reference un modele absent du catalogue : {modele}",
                )

    def test_toute_capacite_mcp_a_des_outils_candidats(self):
        for capacite in CAPACITES:
            if capacite["voie"] == "mcp":
                self.assertTrue(capacite["outils_mcp"], capacite["id"])
                for outil in capacite["outils_mcp"]:
                    self.assertIn(outil, OUTILS_MCP_AUTORISES)

    def test_aucune_capacite_api_ne_promet_d_outil_mcp(self):
        for capacite in CAPACITES:
            if capacite["voie"] == "api":
                self.assertEqual(capacite["outils_mcp"], [])

    def test_capacite_par_id_insensible_casse(self):
        self.assertIsNotNone(capacite_par_id(" Audio_TTS "))
        self.assertIsNone(capacite_par_id(""))


class TestEstimationCreditsSeulement(unittest.TestCase):
    def test_aucun_montant_en_argent_dans_estimation(self):
        racine = Path(__file__).parent / "core"
        for nom in ("generation_video_higgsfield.py", "outils_higgsfield.py"):
            source = (racine / nom).read_text(encoding="utf-8").lower()
            self.assertNotIn("usd", source, nom)
            self.assertNotIn("dollar", source, nom)


if __name__ == "__main__":
    unittest.main()
