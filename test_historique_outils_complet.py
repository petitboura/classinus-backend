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


class JournalDesOutilsDansLHistorique(unittest.TestCase):
    def test_le_journal_contient_les_arguments_et_le_resultat_complet(self):
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
        journal = h.journal_outils_historique(historique)
        self.assertIn('Appel : {"action": "lire", "chemin": "core/main.py"}', journal)
        self.assertIn(complet, journal)
        self.assertNotIn("(tronque)", journal)

    def test_les_messages_assistant_restent_du_texte_seul(self):
        historique = [
            {"role": "user", "content": "lis le fichier"},
            _message([{"nomOutil": "x", "nomLisible": "X", "resultat": "abc"}], contenu="Voici le fichier."),
            {"role": "user", "content": "merci"},
        ]
        sortie = h.historique_texte_seul(historique)
        self.assertEqual(sortie, [
            {"role": "user", "content": "lis le fichier"},
            {"role": "assistant", "content": "Voici le fichier."},
            {"role": "user", "content": "merci"},
        ])

    def test_aucun_ancien_marqueur_nulle_part(self):
        historique = [_message([{"nomOutil": "x", "nomLisible": "X", "resultat": "abc"}], contenu="Fait.")]
        journal = h.journal_outils_historique(historique)
        texte_seul = h.historique_texte_seul(historique)[0]["content"]
        for texte in (journal, texte_seul):
            self.assertNotIn("[Résultat de l'outil", texte)
            self.assertNotIn("Réponse donnée à ce moment", texte)
        self.assertNotIn("abc", texte_seul)

    def test_ancien_format_sans_nouveaux_champs_inchange(self):
        historique = [_message([{"nomOutil": "x", "nomLisible": "X", "resultat": "abc"}])]
        journal = h.journal_outils_historique(historique)
        self.assertIn("Outil : X\nRésultat :\nabc", journal)
        self.assertNotIn("Appel :", journal)

    def test_journal_vide_sans_outils(self):
        historique = [{"role": "user", "content": "salut"}, {"role": "assistant", "content": "Bonjour"}]
        self.assertEqual(h.journal_outils_historique(historique), "")
        self.assertEqual(h.journal_outils_historique([]), "")
        self.assertEqual(h.journal_outils_historique(None), "")

    def test_le_journal_rattache_les_outils_a_la_bonne_reponse(self):
        historique = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "Premiere reponse sans outil"},
            {"role": "user", "content": "b"},
            _message([{"nomOutil": "x", "nomLisible": "X", "resultat": "abc"}], contenu="Deuxieme reponse"),
        ]
        journal = h.journal_outils_historique(historique)
        self.assertIn("ta réponse n°2", journal)
        self.assertIn("Deuxieme reponse", journal)
        self.assertNotIn("n°1", journal)

    def test_le_dernier_message_avec_outils_reste_entier_meme_au_dessus_du_seuil(self):
        gros = "z" * (h.SEUIL_CARACTERES_OUTILS_HISTORIQUE + 5000)
        ancien = "a" * 6000
        historique = [
            _message([{"nomOutil": "a", "nomLisible": "Ancien", "resultat": ancien}]),
            {"role": "user", "content": "suite"},
            _message([{"nomOutil": "b", "nomLisible": "Recent", "resultat": gros}]),
        ]
        journal = h.journal_outils_historique(historique)
        self.assertIn(gros, journal)
        self.assertNotIn(ancien, journal)
        self.assertIn("déjà exécuté plus tôt", journal)


if __name__ == "__main__":
    unittest.main()
