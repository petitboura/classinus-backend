"""Parent des lignes d'historique (core/persistance_echanges.py) : tests sans base ni reseau.

Verifie la reparation du 31/10/2026 : dans un fil qui a deja des lignes,
un parent absent ou introuvable ne doit plus creer une deuxieme racine
invisible a la reouverture.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))


class _Resultat:
    def __init__(self, data):
        self.data = data


class _Requete:
    def __init__(self, faux, table):
        self._faux = faux
        self._table = table
        self._filtres = {}
        self._insertion = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, colonne, valeur):
        self._filtres[colonne] = valeur
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, charge):
        self._insertion = charge
        return self

    def execute(self):
        faux = self._faux
        if self._insertion is not None:
            if isinstance(self._insertion, list):
                return _Resultat(list(self._insertion))
            faux.insertions.append((self._table, dict(self._insertion)))
            faux.prochain_id += 1
            return _Resultat([{**self._insertion, "id": faux.prochain_id, "created_at": "2026-10-31T00:00:00Z"}])
        if "id" in self._filtres:
            return _Resultat([{"id": self._filtres["id"]}] if faux.parent_existe else [])
        return _Resultat([{"id": faux.derniere_id}] if faux.derniere_id else [])


class _FauxSupabase:
    def __init__(self):
        self.parent_existe = False
        self.derniere_id = None
        self.insertions = []
        self.prochain_id = 100

    def table(self, nom):
        return _Requete(self, nom)


FAUX = _FauxSupabase()

_constantes = types.ModuleType("constantes_agent")
_constantes.supabase = FAUX
sys.modules["constantes_agent"] = _constantes

_profils = types.ModuleType("profils_agents")
_profils._mettre_a_jour_profil_utilisateur_si_besoin = lambda *_a, **_k: None
sys.modules["profils_agents"] = _profils

import persistance_echanges  # noqa: E402


class ParentEffectifTest(unittest.TestCase):
    def setUp(self):
        FAUX.parent_existe = False
        FAUX.derniere_id = None
        FAUX.insertions = []
        FAUX.prochain_id = 100

    def test_parent_absent_repere_sur_derniere_ligne(self):
        FAUX.derniere_id = 42
        self.assertEqual(persistance_echanges._parent_effectif("u1", "clovis", "conv1", None), 42)

    def test_parent_valide_respecte_meme_ancien(self):
        FAUX.parent_existe = True
        FAUX.derniere_id = 42
        self.assertEqual(persistance_echanges._parent_effectif("u1", "clovis", "conv1", 7), 7)

    def test_parent_introuvable_repere_sur_derniere_ligne(self):
        FAUX.parent_existe = False
        FAUX.derniere_id = 42
        self.assertEqual(persistance_echanges._parent_effectif("u1", "clovis", "conv1", 999), 42)

    def test_premier_message_du_fil_reste_sans_parent(self):
        self.assertIsNone(persistance_echanges._parent_effectif("u1", "clovis", "conv1", None))

    def test_sans_conversation_id_aucune_reparation(self):
        FAUX.derniere_id = 42
        self.assertIsNone(persistance_echanges._parent_effectif("u1", "clovis", None, None))
        self.assertEqual(persistance_echanges._parent_effectif("u1", "clovis", None, 7), 7)

    def test_sauvegarde_ecrit_le_parent_repare(self):
        FAUX.derniere_id = 42
        ids = persistance_echanges._sauvegarder_echange(
            "u1", "clovis", "question", "reponse", conversation_id="conv1", parent_id=None
        )
        historique = [charge for table, charge in FAUX.insertions if table == "historique_conversations"]
        self.assertEqual(len(historique), 2)
        self.assertEqual(historique[0]["parent_id"], 42)
        self.assertEqual(historique[1]["parent_id"], 101)
        self.assertEqual(ids["message_id_user"], 101)


if __name__ == "__main__":
    unittest.main()
