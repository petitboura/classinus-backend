"""Persistance en base des tours detaches (core/persistance_tours.py) : tests avec un faux
client Supabase en memoire, aucune vraie base ni reseau.

constantes_agent est remplace avant l'import : le vrai module cree un client Supabase
des son chargement, ce que ces tests ne veulent pas.
"""
import sys
import types
import unittest

# Faux client remplace plus bas, avant tout usage reel.
_faux_module = types.ModuleType("constantes_agent")
_faux_module.supabase = None
sys.modules.setdefault("constantes_agent", _faux_module)
sys.path.insert(0, "core")

from core import persistance_tours  # noqa: E402


class _Reponse:
    def __init__(self, data):
        self.data = data


class _Requete:
    """Mini constructeur facon supabase-py : insert/update/select/delete + eq/lt/neq + order/limit."""

    def __init__(self, base, table):
        self.base = base
        self.table = table
        self.operation = None
        self.charge = None
        self.filtres = []
        self.tri = None
        self.limite = None

    def insert(self, charge):
        self.operation, self.charge = "insert", charge
        return self

    def update(self, charge):
        self.operation, self.charge = "update", charge
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def select(self, *_args):
        self.operation = "select"
        return self

    def eq(self, colonne, valeur):
        self.filtres.append((colonne, "eq", valeur))
        return self

    def lt(self, colonne, valeur):
        self.filtres.append((colonne, "lt", valeur))
        return self

    def neq(self, colonne, valeur):
        self.filtres.append((colonne, "neq", valeur))
        return self

    def order(self, colonne, desc=False):
        self.tri = (colonne, desc)
        return self

    def limit(self, nombre):
        self.limite = nombre
        return self

    def _correspond(self, ligne):
        for colonne, operateur, valeur in self.filtres:
            actuel = ligne.get(colonne)
            if operateur == "eq" and actuel != valeur:
                return False
            if operateur == "neq" and actuel == valeur:
                return False
            if operateur == "lt" and not (actuel is not None and actuel < valeur):
                return False
        return True

    def execute(self):
        lignes = self.base.setdefault(self.table, [])
        if self.operation == "insert":
            lignes.append(dict(self.charge))
            return _Reponse([dict(self.charge)])
        correspondantes = [l for l in lignes if self._correspond(l)]
        if self.operation == "update":
            for ligne in correspondantes:
                ligne.update(self.charge)
            return _Reponse([dict(l) for l in correspondantes])
        if self.operation == "delete":
            self.base[self.table] = [l for l in lignes if not self._correspond(l)]
            return _Reponse([])
        resultat = [dict(l) for l in correspondantes]
        if self.tri:
            colonne, desc = self.tri
            resultat.sort(key=lambda l: l.get(colonne), reverse=desc)
        if self.limite is not None:
            resultat = resultat[: self.limite]
        return _Reponse(resultat)


class _FauxSupabase:
    def __init__(self):
        self.base = {}

    def table(self, nom):
        return _Requete(self.base, nom)


class PersistanceToursTest(unittest.TestCase):
    def setUp(self):
        self.faux = _FauxSupabase()
        persistance_tours.supabase = self.faux

    def test_un_tour_complet_est_persiste_par_paquets(self):
        persistance = persistance_tours.PersistanceTour(
            "tour1", "11111111-1111-1111-1111-111111111111", "conv1", {"type": "message", "message": "Salut"}
        )
        persistance.demarrer()
        persistance.ajouter('data: {"n": 0}\n\n')
        persistance.ajouter(
            'data: {"type": "meta", "message_id_user": 1, "message_id_assistant": 2}\n\n',
            {"message_id_user": 1, "message_id_assistant": 2},
        )
        persistance.clore({"message_id_user": 1, "message_id_assistant": 2})
        persistance._fil.join(timeout=5)

        tour = persistance_tours.lire_tour_persiste("tour1", "11111111-1111-1111-1111-111111111111")
        self.assertIsNotNone(tour)
        self.assertEqual(tour["statut"], "termine")
        self.assertEqual(tour["nb_evenements"], 2)
        self.assertEqual(tour["ids_echange"], {"message_id_user": 1, "message_id_assistant": 2})
        self.assertEqual(len(tour["lignes"]), 2)
        self.assertIn('"n": 0', tour["lignes"][0])

    def test_un_tour_n_est_lisible_que_par_son_compte(self):
        self.faux.base[persistance_tours.TABLE_TOURS] = [
            {"id": "tour1", "user_id": "u1", "conversation_id": "c1", "statut": "termine",
             "resume": {}, "ids_echange": None, "nb_evenements": 0}
        ]
        self.assertIsNone(persistance_tours.lire_tour_persiste("tour1", "autre"))
        self.assertIsNotNone(persistance_tours.lire_tour_persiste("tour1", "u1"))

    def test_dernier_tour_d_une_conversation(self):
        self.faux.base[persistance_tours.TABLE_TOURS] = [
            {"id": "vieux", "user_id": "u1", "conversation_id": "c1", "statut": "termine",
             "resume": {}, "ids_echange": None, "nb_evenements": 1, "cree_le": "2026-10-31T01:00:00+00:00"},
            {"id": "recent", "user_id": "u1", "conversation_id": "c1", "statut": "interrompu",
             "resume": {}, "ids_echange": None, "nb_evenements": 3, "cree_le": "2026-10-31T02:00:00+00:00"},
        ]
        dernier = persistance_tours.dernier_tour_persiste("u1", "c1")
        self.assertEqual(dernier["id"], "recent")

    def test_les_paquets_sont_rejoues_dans_l_ordre_depuis_une_position(self):
        paquets = [
            {"a_partir_de": 2, "lignes": ["c", "d"]},
            {"a_partir_de": 0, "lignes": ["a", "b"]},
        ]
        self.assertEqual(persistance_tours._lignes_depuis_paquets(paquets, 1), ["b", "c", "d"])
        self.assertEqual(persistance_tours._lignes_depuis_paquets(paquets, 0), ["a", "b", "c", "d"])

    def test_les_orphelins_sans_signe_de_vie_sont_marques_interrompus(self):
        self.faux.base[persistance_tours.TABLE_TOURS] = [
            {"id": "mort", "user_id": "u1", "conversation_id": "c1", "statut": "en_cours",
             "maj_le": "2020-01-01T00:00:00+00:00", "cree_le": "2020-01-01T00:00:00+00:00"},
            {"id": "vivant", "user_id": "u1", "conversation_id": "c1", "statut": "en_cours",
             "maj_le": "2999-01-01T00:00:00+00:00", "cree_le": "2999-01-01T00:00:00+00:00"},
        ]
        # La purge des vieux tours touches aussi "mort" apres marquage (cree en 2020) :
        # on verifie le marquage via le compteur et l'etat de "vivant".
        marques = persistance_tours.marquer_tours_orphelins()
        self.assertEqual(marques, 1)
        restants = {l["id"]: l for l in self.faux.base[persistance_tours.TABLE_TOURS]}
        self.assertEqual(restants["vivant"]["statut"], "en_cours")


if __name__ == "__main__":
    unittest.main()
