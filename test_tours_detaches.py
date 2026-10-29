"""Tours de chat detaches de la connexion (core/tours_detaches.py) et arret par conversation
(core/arret_tour.py) : tests sans base ni reseau.

Dependances minimales : bibliotheque standard seulement, plus core.plafonds_reglables.
"""
import threading
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from core import arret_tour, tours_detaches
from core.tours_detaches import LIGNE_FIN, LIGNE_SIGNE_VIE


def _ligne(n):
    return f'data: {{"n": {n}}}\n\n'


def _fabrique_lente(nombre, porte=None, pause=0.01):
    """Fabrique de lignes SSE : `nombre` evenements, puis la fin. `porte` bloque la production
    tant qu'elle n'est pas ouverte, pour simuler un travail long."""

    def fabrique():
        for n in range(nombre):
            if porte is not None and n == 1:
                porte.wait(timeout=5)
            time.sleep(pause)
            yield _ligne(n)
        yield LIGNE_FIN

    return fabrique


def _attendre_fin(tour, delai=5):
    debut = time.monotonic()
    while not tour.termine:
        if time.monotonic() - debut > delai:
            raise AssertionError("le tour ne s'est pas termine")
        time.sleep(0.01)


class TourDetacheTest(unittest.TestCase):
    def setUp(self):
        with tours_detaches._verrou:
            tours_detaches._tours.clear()
            tours_detaches._dernier_par_conversation.clear()

    def test_lecture_complete_dans_l_ordre(self):
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(3))
        lignes = list(tour.lire(0))
        self.assertEqual(lignes, [_ligne(0), _ligne(1), _ligne(2), LIGNE_FIN])

    def test_reprise_a_la_position_demandee(self):
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(4))
        _attendre_fin(tour)
        self.assertEqual(list(tour.lire(2)), [_ligne(2), _ligne(3), LIGNE_FIN])
        self.assertEqual(list(tour.lire(99)), [])

    def test_le_travail_continue_quand_le_lecteur_se_ferme(self):
        """Le coeur de la fonction : une connexion qui se ferme ne coupe plus le travail."""
        porte = threading.Event()
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(4, porte=porte))
        lecteur = tour.lire(0)
        self.assertEqual(next(lecteur), _ligne(0))
        lecteur.close()  # le navigateur part (rechargement, changement de conversation)
        self.assertFalse(tour.termine)
        porte.set()
        _attendre_fin(tour)
        # Un nouveau lecteur retrouve tout ce qui s'est passe pendant l'absence.
        self.assertEqual(list(tour.lire(1)), [_ligne(1), _ligne(2), _ligne(3), LIGNE_FIN])

    def test_un_lecteur_suit_le_travail_en_direct(self):
        porte = threading.Event()
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(3, porte=porte))
        recus = []

        def lire():
            recus.extend(tour.lire(0))

        fil = threading.Thread(target=lire)
        fil.start()
        time.sleep(0.1)
        self.assertEqual(recus, [_ligne(0)])
        porte.set()
        fil.join(timeout=5)
        self.assertEqual(recus, [_ligne(0), _ligne(1), _ligne(2), LIGNE_FIN])

    def test_signe_de_vie_pendant_le_silence_mais_pas_par_defaut(self):
        porte = threading.Event()
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(3, porte=porte))
        lecteur = tour.lire(0, signe_vie=0.05)
        self.assertEqual(next(lecteur), _ligne(0))
        self.assertEqual(next(lecteur), LIGNE_SIGNE_VIE)
        lecteur.close()
        porte.set()
        _attendre_fin(tour)
        # Sans delai de signe de vie (flux d'origine), aucune ligne de commentaire n'est ajoutee.
        self.assertNotIn(LIGNE_SIGNE_VIE, list(tour.lire(0)))

    def test_erreur_du_travail_donne_un_message_et_une_fin(self):
        def fabrique():
            raise RuntimeError("panne")
            yield  # pragma: no cover

        tour = tours_detaches.demarrer("u1", "c1", fabrique, message_erreur="Panne.")
        lignes = list(tour.lire(0))
        self.assertEqual(len(lignes), 2)
        self.assertIn("Panne.", lignes[0])
        self.assertEqual(lignes[1], LIGNE_FIN)
        self.assertTrue(tour.termine)

    def test_un_tour_n_est_visible_que_de_son_compte(self):
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1))
        self.assertIs(tours_detaches.trouver(tour.id, "u1"), tour)
        self.assertIsNone(tours_detaches.trouver(tour.id, "u2"))
        self.assertIs(tours_detaches.dernier_de_conversation("u1", "c1"), tour)
        self.assertIsNone(tours_detaches.dernier_de_conversation("u2", "c1"))
        self.assertIsNone(tours_detaches.dernier_de_conversation("u1", "autre"))

    def test_le_dernier_tour_d_une_conversation_remplace_le_precedent(self):
        premier = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1))
        second = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1))
        self.assertIs(tours_detaches.dernier_de_conversation("u1", "c1"), second)
        self.assertIs(tours_detaches.trouver(premier.id, "u1"), premier)

    def test_les_identifiants_de_l_echange_sont_lus_dans_l_evenement_meta(self):
        def fabrique():
            yield 'data: {"type": "reponse", "texte": "Bonjour"}\n\n'
            yield 'data: {"type": "meta", "message_id_user": 11, "message_id_assistant": 12, "modele": "x"}\n\n'
            yield LIGNE_FIN

        tour = tours_detaches.demarrer("u1", "c1", fabrique)
        _attendre_fin(tour)
        self.assertEqual(tour.ids, {"message_id_user": 11, "message_id_assistant": 12})

    def test_pas_d_identifiants_tant_que_l_echange_n_est_pas_sauvegarde(self):
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(2))
        _attendre_fin(tour)
        self.assertIsNone(tour.ids)

    def test_un_texte_qui_ressemble_a_meta_ne_donne_pas_d_identifiants(self):
        def fabrique():
            yield 'data: {"type": "reponse", "texte": "\\"type\\": \\"meta\\""}\n\n'
            yield "data: pas du json\n\n"
            yield LIGNE_FIN

        tour = tours_detaches.demarrer("u1", "c1", fabrique)
        _attendre_fin(tour)
        self.assertIsNone(tour.ids)

    def test_le_resume_est_conserve(self):
        tour = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1), resume={"type": "message", "message": "Salut"})
        self.assertEqual(tour.resume, {"type": "message", "message": "Salut"})

    def test_les_tours_termines_trop_vieux_sont_oublies(self):
        ancien = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1))
        _attendre_fin(ancien)
        ancien.termine_a -= 3600
        with patch.object(tours_detaches, "CONSERVATION_TOUR_DETACHE", timedelta(minutes=30)):
            tours_detaches.demarrer("u1", "c2", _fabrique_lente(1))
        self.assertIsNone(tours_detaches.trouver(ancien.id, "u1"))
        self.assertIsNone(tours_detaches.dernier_de_conversation("u1", "c1"))

    def test_un_tour_en_cours_n_est_jamais_oublie(self):
        porte = threading.Event()
        long = tours_detaches.demarrer("u1", "c1", _fabrique_lente(3, porte=porte))
        with patch.object(tours_detaches, "CONSERVATION_TOUR_DETACHE", timedelta(seconds=0)), patch.object(
            tours_detaches, "MAX_TOURS_DETACHES_CONSERVES", 1
        ):
            for i in range(3):
                tours_detaches.demarrer("u1", f"x{i}", _fabrique_lente(1))
        self.assertIs(tours_detaches.trouver(long.id, "u1"), long)
        porte.set()
        _attendre_fin(long)

    def test_plafond_du_nombre_de_tours_termines_gardes(self):
        tours = []
        for i in range(4):
            t = tours_detaches.demarrer("u1", f"c{i}", _fabrique_lente(1))
            _attendre_fin(t)
            tours.append(t)
        with patch.object(tours_detaches, "MAX_TOURS_DETACHES_CONSERVES", 2):
            tours_detaches.demarrer("u1", "dernier", _fabrique_lente(1))
        gardes = [t for t in tours if tours_detaches.trouver(t.id, "u1") is not None]
        self.assertLessEqual(len(gardes), 2)
        self.assertIn(tours[-1], gardes)

    def test_oublier_utilisateur_retire_ses_tours_seulement(self):
        a = tours_detaches.demarrer("u1", "c1", _fabrique_lente(1))
        b = tours_detaches.demarrer("u2", "c1", _fabrique_lente(1))
        self.assertEqual(tours_detaches.oublier_utilisateur("u1"), 1)
        self.assertIsNone(tours_detaches.trouver(a.id, "u1"))
        self.assertIs(tours_detaches.trouver(b.id, "u2"), b)

    def test_le_contexte_de_la_requete_est_copie_dans_le_thread(self):
        import contextvars

        variable = contextvars.ContextVar("test_tours_detaches", default="absent")
        variable.set("present")

        def fabrique():
            yield f"data: {variable.get()}\n\n"
            yield LIGNE_FIN

        tour = tours_detaches.demarrer("u1", "c1", fabrique)
        self.assertEqual(list(tour.lire(0))[0], "data: present\n\n")


class ArretParConversationTest(unittest.TestCase):
    def setUp(self):
        with arret_tour._verrou:
            arret_tour._tours_ouverts.clear()

    def test_arret_d_une_conversation_laisse_les_autres(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        b = arret_tour.ouvrir_arret("u1", "c2")
        self.assertEqual(arret_tour.demander_arret_utilisateur("u1", "c1"), 1)
        self.assertTrue(arret_tour.arret_demande(a))
        self.assertFalse(arret_tour.arret_demande(b))
        self.assertTrue(arret_tour.autres_tours_en_cours("u1"))

    def test_sans_conversation_tout_le_compte_s_arrete(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        b = arret_tour.ouvrir_arret("u1", "c2")
        c = arret_tour.ouvrir_arret("u2", "c1")
        self.assertEqual(arret_tour.demander_arret_utilisateur("u1"), 2)
        self.assertTrue(arret_tour.arret_demande(a) and arret_tour.arret_demande(b))
        self.assertFalse(arret_tour.arret_demande(c))
        self.assertFalse(arret_tour.autres_tours_en_cours("u1"))

    def test_plus_d_autre_tour_une_fois_le_dernier_arrete_ou_ferme(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        b = arret_tour.ouvrir_arret("u1", "c2")
        arret_tour.demander_arret_utilisateur("u1", "c1")
        arret_tour.fermer_arret(b)
        self.assertFalse(arret_tour.autres_tours_en_cours("u1"))
        arret_tour.fermer_arret(a)
        self.assertFalse(arret_tour.autres_tours_en_cours("u1"))

    def test_visiteur_non_connecte(self):
        self.assertIsNone(arret_tour.ouvrir_arret(None, "c1"))
        self.assertEqual(arret_tour.demander_arret_utilisateur(None, "c1"), 0)
        self.assertFalse(arret_tour.autres_tours_en_cours(None))

    def test_appel_historique_a_un_seul_argument(self):
        a = arret_tour.ouvrir_arret("u1")
        self.assertEqual(arret_tour.demander_arret_utilisateur("u1"), 1)
        self.assertTrue(arret_tour.arret_demande(a))


if __name__ == "__main__":
    unittest.main()
