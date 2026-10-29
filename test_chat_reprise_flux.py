"""Routes de reprise du flux du chat (api/chat.py) : envoi detache, rattachement, arret par conversation.

Ces tests importent api.main : ils demandent les dependances completes du projet (requirements.txt)
et sont ignores si elles manquent, comme test_plafonds_chat.py. Le fonctionnement du rangement et la
poursuite du travail apres fermeture du lecteur sont testes sans dependances dans
test_tours_detaches.py.
"""
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "http://x.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "eyJhbGciOiJIUzI1NiJ9.e30.x")

try:
    from fastapi.testclient import TestClient
    from api.main import app
    import api.chat as module_chat
    _MANQUE = None
except ImportError as erreur:  # dependances completes absentes
    _MANQUE = f"dependances completes du projet requises : {erreur}"

avec_dependances_completes = unittest.skipIf(_MANQUE is not None, _MANQUE or "")

if _MANQUE is None:
    from core import arret_tour, tours_detaches


def _evenements_factices(payload, user_id, langue_interface="fr"):
    yield 'data: {"type": "reponse", "texte": "Bonjour"}\n\n'
    yield 'data: {"type": "meta", "message_id_user": 1, "message_id_assistant": 2}\n\n'
    yield "data: [DONE]\n\n"


def _donnees(corps):
    return [ligne for ligne in corps.split("\n\n") if ligne]


@avec_dependances_completes
class RoutesRepriseFlux(unittest.TestCase):
    def setUp(self):
        with tours_detaches._verrou:
            tours_detaches._tours.clear()
            tours_detaches._dernier_par_conversation.clear()
        with arret_tour._verrou:
            arret_tour._tours_ouverts.clear()
        self.client = TestClient(app)
        self.utilisateur = {"id": "u1"}
        # La dependance est lue dans api.chat au moment du test : d'autres tests du projet
        # rechargent api.auth, l'objet importe plus haut ne serait alors plus celui des routes.
        self.dependance = module_chat.utilisateur_optionnel
        app.dependency_overrides[self.dependance] = lambda: (
            SimpleNamespace(id=self.utilisateur["id"]) if self.utilisateur["id"] else None
        )
        self.patchs = [
            patch("api.chat._evenements_sse", _evenements_factices),
            patch("api.chat.acces_chat_bloque_pour_mineur", lambda user_id: False),
            patch("api.chat._resoudre_modele_force", lambda agent_id, modele: None),
        ]
        for p in self.patchs:
            p.start()

    def tearDown(self):
        for p in self.patchs:
            p.stop()
        app.dependency_overrides.pop(self.dependance, None)

    def _envoyer(self, **champs):
        corps = {"message": "Salut", "agent_id": "a1", "conversation_id": "c1"}
        corps.update(champs)
        return self.client.post("/api/chat", json=corps)

    def _attendre_fin_du_tour(self, user_id="u1", conversation_id="c1"):
        debut = time.monotonic()
        while True:
            tour = tours_detaches.dernier_de_conversation(user_id, conversation_id)
            if tour is not None and tour.termine:
                return tour
            if time.monotonic() - debut > 5:
                raise AssertionError("le tour ne s'est pas termine")
            time.sleep(0.01)

    def test_envoi_connecte_donne_un_identifiant_de_tour_et_le_meme_flux(self):
        reponse = self._envoyer()
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.headers.get("x-tour-id"))
        donnees = _donnees(reponse.text)
        self.assertEqual(len(donnees), 3)
        self.assertEqual(donnees[-1], "data: [DONE]")

    def test_l_identifiant_de_tour_est_visible_du_navigateur(self):
        reponse = self._envoyer()
        # Le frontend ne peut lire X-Tour-Id depuis un autre domaine que s'il est expose.
        exposes = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
        self.assertTrue(exposes)
        self.assertIn("X-Tour-Id", exposes[0].kwargs["expose_headers"])
        self.assertTrue(reponse.headers.get("x-tour-id"))

    def test_tour_en_cours_apres_un_envoi_decrit_le_message(self):
        self._envoyer(message="Explique les limites", parent_id=7)
        tour = self._attendre_fin_du_tour()
        reponse = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c1"})
        self.assertEqual(reponse.status_code, 200)
        etat = reponse.json()
        self.assertEqual(etat["statut"], "termine")
        self.assertEqual(etat["tour_id"], tour.id)
        self.assertEqual(etat["nb_evenements"], 3)
        # L'evenement "meta" du flux factice annonce l'echange sauvegarde.
        self.assertEqual(etat["ids"], {"message_id_user": 1, "message_id_assistant": 2})
        self.assertEqual(
            etat["resume"],
            {"type": "message", "message": "Explique les limites", "automatique": False, "parent_id": 7},
        )

    def test_resume_d_une_regeneration_et_d_une_reprise(self):
        self._envoyer(regenerer=True, parent_id=5)
        self._attendre_fin_du_tour()
        etat = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c1"}).json()
        self.assertEqual(etat["resume"], {"type": "regeneration", "parent_id": 5})

        self._envoyer(conversation_id="c2", message=None, reprise={"etat_reprise": {}, "approuve": True})
        self._attendre_fin_du_tour(conversation_id="c2")
        etat = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c2"}).json()
        self.assertEqual(etat["resume"], {"type": "reprise", "message": None})

        self._envoyer(
            conversation_id="c3", message=None,
            reprise={"etat_reprise": {}, "approuve": True, "message_utilisateur": "Continue en plus court"},
        )
        self._attendre_fin_du_tour(conversation_id="c3")
        etat = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c3"}).json()
        self.assertEqual(etat["resume"], {"type": "reprise", "message": "Continue en plus court"})

    def test_message_enregistre_remplace_le_message_dans_le_resume(self):
        self._envoyer(message="consignes plus question", message_enregistre="question")
        self._attendre_fin_du_tour()
        etat = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c1"}).json()
        self.assertEqual(etat["resume"]["message"], "question")

    def test_rattachement_rejoue_a_partir_du_numero_demande(self):
        self._envoyer()
        tour = self._attendre_fin_du_tour()
        tout = self.client.get(f"/api/chat/flux/{tour.id}")
        self.assertEqual(tout.status_code, 200)
        self.assertEqual(len(_donnees(tout.text)), 3)
        suite = self.client.get(f"/api/chat/flux/{tour.id}", params={"depuis": 2})
        self.assertEqual(_donnees(suite.text), ["data: [DONE]"])
        rien = self.client.get(f"/api/chat/flux/{tour.id}", params={"depuis": 99})
        self.assertEqual(rien.text, "")

    def test_le_flux_rejoue_est_identique_a_l_original(self):
        original = self._envoyer()
        tour = self._attendre_fin_du_tour()
        rejoue = self.client.get(f"/api/chat/flux/{tour.id}")
        self.assertEqual(rejoue.text, original.text)

    def test_aucun_tour_pour_une_conversation_inconnue(self):
        reponse = self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "inconnue"})
        self.assertEqual(reponse.json(), {"statut": "aucun"})

    def test_un_autre_compte_ne_voit_ni_ne_rejoint_le_tour(self):
        self._envoyer()
        tour = self._attendre_fin_du_tour()
        self.utilisateur["id"] = "u2"
        self.assertEqual(
            self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c1"}).json(),
            {"statut": "aucun"},
        )
        reponse = self.client.get(f"/api/chat/flux/{tour.id}")
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.json()["detail"]["code"], "TOUR_CHAT_INTROUVABLE")

    def test_visiteur_non_connecte_garde_le_flux_direct(self):
        self.utilisateur["id"] = None
        reponse = self._envoyer()
        self.assertEqual(reponse.status_code, 200)
        self.assertIsNone(reponse.headers.get("x-tour-id"))
        self.assertEqual(len(_donnees(reponse.text)), 3)
        self.assertEqual(
            self.client.get("/api/chat/tour-en-cours", params={"conversation_id": "c1"}).json(),
            {"statut": "aucun"},
        )
        self.assertEqual(self.client.get("/api/chat/flux/nimporte").status_code, 404)

    def test_tour_inconnu(self):
        self.assertEqual(self.client.get("/api/chat/flux/inconnu").status_code, 404)

    def test_arreter_une_conversation_laisse_l_autre_continuer(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        b = arret_tour.ouvrir_arret("u1", "c2")
        reponse = self.client.post("/api/chat/arreter", params={"conversation_id": "c1"})
        self.assertEqual(reponse.json(), {"tours_arretes": 1, "attentes_annulees": 0})
        self.assertTrue(arret_tour.arret_demande(a))
        self.assertFalse(arret_tour.arret_demande(b))

    def test_arreter_sans_conversation_arrete_tout_le_compte(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        b = arret_tour.ouvrir_arret("u1", "c2")
        reponse = self.client.post("/api/chat/arreter")
        self.assertEqual(reponse.json()["tours_arretes"], 2)
        self.assertTrue(arret_tour.arret_demande(a) and arret_tour.arret_demande(b))

    def test_arreter_le_dernier_tour_d_une_conversation_previent_l_appli(self):
        a = arret_tour.ouvrir_arret("u1", "c1")
        reponse = self.client.post("/api/chat/arreter", params={"conversation_id": "c1"})
        self.assertEqual(reponse.json()["tours_arretes"], 1)
        self.assertTrue(arret_tour.arret_demande(a))


if __name__ == "__main__":
    unittest.main()
