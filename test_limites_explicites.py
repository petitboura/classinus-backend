"""Limites explicites : codes traduisibles, valeurs brutes, aucune phrase française collée dans un gabarit anglais."""
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.erreurs import MESSAGES_EN, MESSAGES_FR, erreur_api

CODES_LIMITES = (
    "LIMITE_CHAMP_IMAGES",
    "LIMITE_CHAMP_IMAGES_VIDEO",
    "LIMITE_CHAMP_OUTILS",
    "LIMITE_CHAMP_ZIPS",
    "LIMITE_CHAMP_OUTILS_CHOISIS",
    "LIMITE_CHAMP_DEPASSEE",
    "LIMITE_CHAMP_DEPASSEE_SANS_MAXIMUM",
    "LIMITE_DEBIT_CHAT",
    "LIMITE_DEBIT_GENERATION",
    "LIMITE_DEBIT_HIGGSFIELD",
    "LIMITE_DEBIT_PROFIL",
    "LIMITE_DEBIT_RENDU_ANIMATION",
    "LIMITE_DEBIT_WIDGETS",
    "LIMITE_DEBIT_BIBLIOTHEQUE",
    "LIMITE_DEBIT_GENERIQUE",
    "LIMITE_DEBIT_SANS_PLAFOND",
    "MCP_SONDAGE_LIMITE",
    "RENDU_VIDEO_OCCUPE",
)


def _valeurs(modele: str) -> set:
    return set(re.findall(r"\{(\w+)\}", modele))


class TestMessagesLimites(unittest.TestCase):
    def test_chaque_code_existe_en_francais_et_en_anglais_avec_les_memes_valeurs(self):
        for code in CODES_LIMITES:
            self.assertIn(code, MESSAGES_FR, code)
            self.assertIn(code, MESSAGES_EN, code)
            self.assertEqual(_valeurs(MESSAGES_FR[code]), _valeurs(MESSAGES_EN[code]), code)

    def test_anciens_codes_a_phrase_collee_supprimes(self):
        for code in ("LIMITE_CHAMP_ATTEINTE", "LIMITE_DEBIT_ATTEINTE"):
            self.assertNotIn(code, MESSAGES_FR)
            self.assertNotIn(code, MESSAGES_EN)

    def test_la_file_video_affiche_la_vraie_limite(self):
        detail = erreur_api(503, "RENDU_VIDEO_OCCUPE", maximum=8).detail
        self.assertIn("8", detail["message"])
        self.assertEqual(detail["params"], {"maximum": 8})


class TestGestionnaireLimiteDebit(unittest.TestCase):
    def _corps(self, chemin: str, detail: str) -> tuple[int, dict]:
        from core import limitation_debit

        requete = SimpleNamespace(url=SimpleNamespace(path=chemin))
        with patch.object(limitation_debit, "_cle_limitation", return_value="ip:test"):
            reponse = limitation_debit.gestionnaire_limite_depassee(requete, SimpleNamespace(detail=detail))
        return reponse.status_code, json.loads(reponse.body)["detail"]

    def test_plafond_converti_en_valeurs_brutes(self):
        statut, detail = self._corps("/api/chat/stream", "10 per 1 minute")
        self.assertEqual(statut, 429)
        self.assertEqual(detail["code"], "LIMITE_DEBIT_CHAT")
        self.assertEqual(detail["params"], {"maximum": 10, "secondes": 60})
        self.assertIn("10", detail["message"])
        self.assertIn("60", detail["message"])

    def test_fenetre_en_heures_convertie_en_secondes(self):
        _, detail = self._corps("/api/bibliotheque", "5 per 2 hour")
        self.assertEqual(detail["code"], "LIMITE_DEBIT_BIBLIOTHEQUE")
        self.assertEqual(detail["params"], {"maximum": 5, "secondes": 7200})

    def test_fonctionnalite_inconnue(self):
        _, detail = self._corps("/api/autre", "3 per 1 minute")
        self.assertEqual(detail["code"], "LIMITE_DEBIT_GENERIQUE")

    def test_plafond_illisible_ne_laisse_aucun_marqueur_non_remplace(self):
        _, detail = self._corps("/api/chat", "inattendu")
        self.assertEqual(detail["code"], "LIMITE_DEBIT_SANS_PLAFOND")
        self.assertNotIn("params", detail)
        self.assertNotIn("{", detail["message"])


if __name__ == "__main__":
    unittest.main()
