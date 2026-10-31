"""Historique des outils renvoye au modele : arguments de l'appel et resultat complet.

Sans base ni reseau : bibliotheque standard seulement.
"""
import json
import sys
import types
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "core"))

# constantes_agent ouvre un client Supabase a l'import : remplace par un module minimal.
sys.modules.setdefault("constantes_agent", types.SimpleNamespace(SEUIL_CARACTERES_OUTILS_HISTORIQUE=12000))

from core import historique_outils as h  # noqa: E402


def _message(outils, contenu="Fait."):
    return {"role": "assistant", "content": contenu, "outils": outils}


class ChampsHistoriqueOutil(unittest.TestCase):
    def test_arguments_dict_et_texte_sont_gardes(self):
        champs = h.champs_historique_outil({"action": "run_code", "code": "print(1)"}, "1", "1")
        self.assertEqual(json.loads(champs["arguments"])["code"], "print(1)")
        champs = h.champs_historique_outil('{"chemin": "a.py"}', "ok", "ok")
        self.assertEqual(champs["arguments"], '{"chemin": "a.py"}')

    def test_arguments_vides_ne_sont_pas_ajoutes(self):
        for vide in (None, "", "{}", {}, "null"):
            self.assertNotIn("arguments", h.champs_historique_outil(vide, "ok", "ok"))

    def test_resultat_complet_seulement_si_l_affichage_est_coupe(self):
        self.assertNotIn("resultat_complet", h.champs_historique_outil("{}", "court", "court"))
        long = "x" * 5000
        champs = h.champs_historique_outil("{}", long, long[:3000] + "...")
        self.assertEqual(champs["resultat_complet"], long)

    def test_plafonds_coupent_avec_un_marqueur(self):
        enorme = "y" * (h.PLAFOND_RESULTAT_OUTIL_HISTORIQUE + 10)
        champs = h.champs_historique_outil("{}", enorme, "court")
        self.assertIn("coupé", champs["resultat_complet"])
        self.assertLess(len(champs["resultat_complet"]), len(enorme) + 100)


class ReinjectionDansLHistorique(unittest.TestCase):
    def test_le_modele_revoit_les_arguments_et_le_resultat_complet(self):
        complet = "ligne\n" * 1500
        historique = [
            {"role": "user", "content": "lis le fichier"},
            _message([{
                "nomOutil": "github", "nomLisible": "GitHub",
                "resultat": complet[:3000] + "... (tronque)",
                "resultatComplet": complet,
                "arguments": '{"action": "lire", "chemin": "core/main.py"}',
            }]),
        ]
        contenu = h.enrichir_historique_avec_outils(historique)[1]["content"]
        self.assertIn('Appel : {"action": "lire", "chemin": "core/main.py"}', contenu)
        self.assertIn(complet, contenu)
        self.assertNotIn("(tronque)", contenu)

    def test_ancien_format_sans_nouveaux_champs_inchange(self):
        historique = [_message([{"nomOutil": "x", "nomLisible": "X", "resultat": "abc"}])]
        contenu = h.enrichir_historique_avec_outils(historique)[0]["content"]
        self.assertTrue(contenu.startswith("[Résultat de l'outil déjà exécuté -- X]\nabc"))
        self.assertNotIn("Appel :", contenu)

    def test_le_dernier_message_avec_outils_reste_entier_meme_au_dessus_du_seuil(self):
        gros = "z" * (h.SEUIL_CARACTERES_OUTILS_HISTORIQUE + 5000)
        historique = [
            _message([{"nomOutil": "a", "nomLisible": "Ancien", "resultat": "a" * 6000}]),
            {"role": "user", "content": "suite"},
            _message([{"nomOutil": "b", "nomLisible": "Recent", "resultat": gros}]),
        ]
        sortie = h.enrichir_historique_avec_outils(historique)
        self.assertIn(gros, sortie[2]["content"])
        self.assertIn("déjà exécuté plus tôt", sortie[0]["content"])


if __name__ == "__main__":
    unittest.main()
