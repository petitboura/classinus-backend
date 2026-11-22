"""Tests du parcours d'inscription vocal de la page bambara (22/11/2026).

Règles verrouillées : un profil du parcours range le nom dit à voix haute dans `prenom` (nom vide) avec son genre
et sa présentation facultative ; un genre autre que femme ou homme est refusé ; les phrases lues par la voix viennent
uniquement de la table bambara_parcours_textes (aucune dans le code, une phrase inactive ou vide est ignorée) ;
chaque erreur existe en français et en anglais ; la migration crée la table et les colonnes. Un faux client suffit.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.bambara_profils import (
    LONGUEUR_MAX_PRESENTATION,
    MAX_PROFILS_PAR_COMPTE,
    ErreurBambara,
    creer_profil_parcours,
    lister_profils,
    lister_textes_parcours,
)
from core.erreurs import MESSAGES_EN, MESSAGES_FR
from test_bambara_profils import _FauxClient

RACINE = Path(__file__).parent


class TestProfilParcours(unittest.TestCase):
    def test_cree_un_profil_avec_nom_genre_et_presentation(self):
        c = _FauxClient()
        p = creer_profil_parcours(c, "u1", "  Fanta   Diarra ", "femme", " Je suis  enseignante. ")
        self.assertEqual((p["prenom"], p["nom"], p["genre"]), ("Fanta Diarra", "", "femme"))
        ligne = c.tables["bambara_profils"][0]
        self.assertEqual(ligne["presentation"], "Je suis enseignante.")
        self.assertEqual([x["id"] for x in lister_profils(c, "u1")], [p["id"]])

    def test_presentation_facultative(self):
        c = _FauxClient()
        creer_profil_parcours(c, "u1", "Moussa", "homme", None)
        self.assertNotIn("presentation", c.tables["bambara_profils"][0])

    def test_nom_vide_ou_trop_long_refuse(self):
        c = _FauxClient()
        for nom in ("", "   ", None, "x" * 61):
            with self.assertRaises(ErreurBambara) as e:
                creer_profil_parcours(c, "u1", nom, "femme", None)
            self.assertEqual(e.exception.code, "BAMBARA_NOM_PARLE_INVALIDE")

    def test_genre_invalide_refuse(self):
        c = _FauxClient()
        for genre in ("", "autre", None, "FEMME"):
            with self.assertRaises(ErreurBambara) as e:
                creer_profil_parcours(c, "u1", "Awa", genre, None)
            self.assertEqual(e.exception.code, "BAMBARA_PROFIL_GENRE_INVALIDE")

    def test_presentation_trop_longue_refusee(self):
        c = _FauxClient()
        with self.assertRaises(ErreurBambara) as e:
            creer_profil_parcours(c, "u1", "Awa", "femme", "a" * (LONGUEUR_MAX_PRESENTATION + 1))
        self.assertEqual(e.exception.code, "BAMBARA_PRESENTATION_INVALIDE")

    def test_nombre_maximum_de_profils(self):
        c = _FauxClient()
        for i in range(MAX_PROFILS_PAR_COMPTE):
            creer_profil_parcours(c, "u1", f"P{i}", "homme", None)
        with self.assertRaises(ErreurBambara) as e:
            creer_profil_parcours(c, "u1", "de plus", "homme", None)
        self.assertEqual(e.exception.code, "BAMBARA_TROP_DE_PROFILS")


class TestTextesParcours(unittest.TestCase):
    def _client(self):
        c = _FauxClient()
        c.tables["bambara_parcours_textes"] = [
            {"cle": "nom_demande", "langue": "bm", "texte": "texte un", "actif": True},
            {"cle": "genre_demande", "langue": "bm", "texte": "texte deux", "actif": True},
            {"cle": "fin", "langue": "bm", "texte": "texte trois", "actif": False},
            {"cle": "presentation_demande", "langue": "bm", "texte": "   ", "actif": True},
            {"cle": "nom_demande", "langue": "fr", "texte": "autre langue", "actif": True},
        ]
        return c

    def test_seuls_les_textes_actifs_non_vides_de_la_langue(self):
        self.assertEqual(lister_textes_parcours(self._client()), {"nom_demande": "texte un", "genre_demande": "texte deux"})
        self.assertEqual(lister_textes_parcours(self._client(), "fr"), {"nom_demande": "autre langue"})

    def test_table_vide_donne_aucun_texte(self):
        self.assertEqual(lister_textes_parcours(_FauxClient()), {})

    def test_aucune_phrase_du_parcours_dans_le_code(self):
        # Les clés sont des identifiants, pas des phrases : le serveur ne contient aucune consigne à lire.
        source = (RACINE / "core" / "bambara_profils.py").read_text(encoding="utf-8")
        self.assertNotIn("Quel est ton nom", source)


class TestMessagesEtMigration(unittest.TestCase):
    def test_chaque_code_existe_en_francais_et_en_anglais(self):
        for code in ("BAMBARA_NOM_PARLE_INVALIDE", "BAMBARA_PROFIL_GENRE_INVALIDE", "BAMBARA_PRESENTATION_INVALIDE"):
            self.assertIn(code, MESSAGES_FR, code)
            self.assertIn(code, MESSAGES_EN, code)
            self.assertNotIn("--", MESSAGES_FR[code])
            self.assertNotIn("--", MESSAGES_EN[code])

    def test_migration_cree_la_table_et_les_colonnes(self):
        sql = (RACINE / "migrations" / "2026_11_22_bambara_parcours_inscription.sql").read_text(encoding="utf-8")
        for morceau in ("bambara_parcours_textes", "add column if not exists genre", "add column if not exists presentation", "enable row level security"):
            self.assertIn(morceau, sql, morceau)


if __name__ == "__main__":
    unittest.main()
