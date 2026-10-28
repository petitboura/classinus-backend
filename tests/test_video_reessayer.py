"""Réessayer un montage vidéo : la sélection enregistrée avec la question est relue.

La fonction est chargée depuis api/chat.py avec une fausse base de données, pour
ne pas démarrer tout le chat (modèles, fournisseurs) dans ce test.
"""
from __future__ import annotations

import ast
import logging
import unittest
from pathlib import Path
from typing import Optional

SOURCE = Path(__file__).resolve().parents[1] / "api" / "chat.py"


class FauxPayload:
    def __init__(self, **champs):
        self.champs = champs


class FausseRequete:
    def __init__(self, lignes=None, erreur=None):
        self.filtres = []
        self.lignes = lignes if lignes is not None else []
        self.erreur = erreur

    def table(self, _nom):
        return self

    def select(self, _colonnes):
        return self

    def eq(self, colonne, valeur):
        self.filtres.append((colonne, valeur))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self.erreur:
            raise self.erreur
        return type("Resultat", (), {"data": self.lignes})()


def charger_fonction(base):
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    noeud = next(
        n for n in arbre.body
        if isinstance(n, ast.FunctionDef) and n.name == "_contexte_video_depuis_message"
    )
    espace = {
        "supabase": base,
        "logging": logging,
        "Optional": Optional,
        "ContexteVideoPayload": FauxPayload,
    }
    exec(compile(ast.Module(body=[noeud], type_ignores=[]), str(SOURCE), "exec"), espace)
    return espace["_contexte_video_depuis_message"]


class TestReessayerVideo(unittest.TestCase):
    def test_relit_la_selection_sans_chemin_de_fichier(self):
        base = FausseRequete(lignes=[{"meta": {"contexte_video": {
            "video_id": "v1", "nom_fichier": "cours.mp4", "duree_secondes": 42.5,
            "debut": 1.0, "fin": 5.0, "source_path": "/etc/hostname",
        }}}])
        contexte = charger_fonction(base)("u1", "c1", 42)
        self.assertIsNotNone(contexte)
        self.assertEqual(contexte.champs["video_id"], "v1")
        self.assertEqual(contexte.champs["debut"], 1.0)
        self.assertNotIn("source_path", contexte.champs)

    def test_ne_lit_que_la_question_de_cet_utilisateur_et_de_cette_conversation(self):
        base = FausseRequete(lignes=[])
        charger_fonction(base)("u1", "c1", 42)
        self.assertEqual(
            sorted(base.filtres),
            sorted([("id", 42), ("user_id", "u1"), ("conversation_id", "c1"), ("role", "user")]),
        )

    def test_rien_a_reprendre(self):
        fonction = charger_fonction
        self.assertIsNone(fonction(FausseRequete(lignes=[]))("u1", "c1", 1))
        self.assertIsNone(fonction(FausseRequete(lignes=[{"meta": None}]))("u1", "c1", 1))
        self.assertIsNone(fonction(FausseRequete(lignes=[{"meta": {"automatique": True}}]))("u1", "c1", 1))
        self.assertIsNone(fonction(FausseRequete(lignes=[{"meta": {"contexte_video": "pas un dict"}}]))("u1", "c1", 1))

    def test_erreur_de_base_ne_casse_pas_le_chat(self):
        base = FausseRequete(erreur=RuntimeError("base indisponible"))
        with self.assertLogs(level="ERROR"):
            self.assertIsNone(charger_fonction(base)("u1", "c1", 1))


if __name__ == "__main__":
    unittest.main()
