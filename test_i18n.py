"""Tests de non-régression pour la localisation FR/EN."""
import asyncio
import json
import unittest

from core.erreurs import MESSAGES_EN, MESSAGES_FR
from core.localisation import MiddlewareLangueErreurs, _prefer_anglais, _traduire_enveloppe


class TestLocalisation(unittest.TestCase):
    def test_chaque_code_erreur_a_une_traduction_anglaise(self):
        self.assertEqual(set(MESSAGES_FR), set(MESSAGES_EN))

    def test_entete_anglais_simple(self):
        self.assertTrue(_prefer_anglais({"headers": [(b"accept-language", b"en")]}))

    def test_entete_anglais_region_et_qualite(self):
        self.assertTrue(
            _prefer_anglais(
                {"headers": [(b"accept-language", b"en-US,en;q=0.9,fr;q=0.8")]}
            )
        )

    def test_entete_francais(self):
        self.assertFalse(_prefer_anglais({"headers": [(b"accept-language", b"fr")]}))

    def test_entete_absent_reste_francais(self):
        self.assertFalse(_prefer_anglais({"headers": []}))

    def test_entete_donne_la_priorite_a_la_premiere_langue_a_qualite_egale(self):
        self.assertTrue(
            _prefer_anglais({"headers": [(b"accept-language", b"en,fr")]})
        )

    def test_middleware_traduit_erreur_json_et_actualise_les_entetes(self):
        corps = {
            "detail": {
                "code": "AGENT_NOM_DEJA_PROCHE",
                "message": "Texte français",
                "params": {"agent_id": "agent-456"},
            }
        }

        async def application(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 409,
                "headers": [(b"content-type", b"application/json; charset=utf-8")],
            })
            await send({
                "type": "http.response.body",
                "body": json.dumps(corps).encode("utf-8"),
                "more_body": False,
            })

        async def verifier():
            envoyes = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                envoyes.append(message)

            scope = {
                "type": "http",
                "headers": [(b"accept-language", b"en")],
            }
            await MiddlewareLangueErreurs(application)(scope, receive, send)
            debut = next(x for x in envoyes if x["type"] == "http.response.start")
            body = next(x for x in envoyes if x["type"] == "http.response.body")
            donnees = json.loads(body["body"].decode("utf-8"))
            self.assertIn("already exists", donnees["detail"]["message"])
            self.assertIn("agent-456", donnees["detail"]["message"])
            entetes = dict(debut["headers"])
            self.assertEqual(entetes[b"content-length"], str(len(body["body"])).encode("ascii"))
            self.assertIn(b"accept-language", entetes[b"vary"].lower())

        asyncio.run(verifier())

    def test_middleware_ne_recrit_pas_une_reponse_de_succes(self):
        payload = b'{"message":"contenu"}'

        async def application(scope, receive, send):
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": payload, "more_body": False})

        async def verifier():
            envoyes = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                envoyes.append(message)

            await MiddlewareLangueErreurs(application)(
                {"type": "http", "headers": [(b"accept-language", b"en")]},
                receive,
                send,
            )
            body = next(x for x in envoyes if x["type"] == "http.response.body")
            self.assertEqual(body["body"], payload)

        asyncio.run(verifier())

    def test_traduction_erreur_avec_parametre(self):
        enveloppe = {
            "detail": {
                "code": "AGENT_NOM_DEJA_PROCHE",
                "message": "Texte français",
                "params": {"agent_id": "agent-123"},
            }
        }
        self.assertTrue(_traduire_enveloppe(enveloppe))
        self.assertIn("agent-123", enveloppe["detail"]["message"])
        self.assertIn("already exists", enveloppe["detail"]["message"])

    def test_code_inconnu_est_inchange(self):
        enveloppe = {"detail": {"code": "CODE_INCONNU", "message": "message français"}}
        avant = {"detail": dict(enveloppe["detail"])}
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)

    def test_payload_non_structure_est_inchange(self):
        enveloppe = {"detail": "Message français"}
        avant = dict(enveloppe)
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)


if __name__ == "__main__":
    unittest.main()
