"""Tests de non-régression pour la localisation FR/EN."""
import asyncio
import json
import re
import unittest

from core.erreurs import MESSAGES_EN, MESSAGES_FR
from core.localisation import MiddlewareLangueErreurs, _prefer_anglais, _traduire_enveloppe
from core.libelles_outils_anglais import traduire_libelle_outil


class TestLocalisation(unittest.TestCase):
    def test_chaque_code_erreur_a_une_traduction_anglaise(self):
        self.assertTrue(set(MESSAGES_FR).issubset(MESSAGES_EN))

    def test_les_traductions_conservent_les_parametres(self):
        def parametres(message):
            return set(re.findall(r"(?<!\\{)\\{([A-Za-z_]\\w*)\\}(?!\\})", message))

        divergences = {
            code: {
                "fr": sorted(parametres(message_fr)),
                "en": sorted(parametres(MESSAGES_EN[code])),
            }
            for code, message_fr in MESSAGES_FR.items()
            if parametres(message_fr) != parametres(MESSAGES_EN[code])
        }
        self.assertEqual(divergences, {})

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
                "message": MESSAGES_FR["AGENT_NOM_DEJA_PROCHE"].format(agent_id="agent-456"),
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
                "message": MESSAGES_FR["AGENT_NOM_DEJA_PROCHE"].format(agent_id="agent-123"),
                "params": {"agent_id": "agent-123"},
            }
        }
        self.assertTrue(_traduire_enveloppe(enveloppe))
        self.assertIn("agent-123", enveloppe["detail"]["message"])
        self.assertIn("already exists", enveloppe["detail"]["message"])

    def test_message_personnalise_est_preserve(self):
        enveloppe = {"detail": {"code": "AGENT_NOM_DEJA_PROCHE", "message": "Détail spécifique en français", "params": {"agent_id": "agent-123"}}}
        avant = {"detail": dict(enveloppe["detail"])}
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)

    def test_erreur_historique_sans_entree_francaise_est_traduite(self):
        enveloppe = {
            "detail": {
                "code": "URL_MANQUANTE",
                "message": MESSAGES_FR["ERREUR_INCONNUE"],
            }
        }
        self.assertTrue(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe["detail"]["message"], MESSAGES_EN["URL_MANQUANTE"])

    def test_erreur_historique_personnalisee_reste_inchangee(self):
        enveloppe = {
            "detail": {
                "code": "URL_MANQUANTE",
                "message": "Un message spécifique doit rester intact.",
            }
        }
        avant = {"detail": dict(enveloppe["detail"])}
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)

    def test_libelle_outil_est_traduit(self):
        self.assertEqual(traduire_libelle_outil("Recherche web"), "Web search")

    def test_statut_dynamique_est_traduit(self):
        self.assertEqual(traduire_libelle_outil("Recherche web..."), "Web search...")
        self.assertEqual(
            traduire_libelle_outil("Recherche (Ma bibliothèque) effectuée"),
            "Search (My library) completed",
        )

    def test_statuts_de_lecture_image_sont_traduits(self):
        self.assertEqual(
            traduire_libelle_outil("Lecture de l'image a échoué"),
            "Image reading failed",
        )

    def test_texte_non_reconnu_reste_inchange(self):
        texte = "Le résultat du document utilisateur."
        self.assertEqual(traduire_libelle_outil(texte), texte)

    def test_ancien_detail_texte_catalogue_est_traduit(self):
        enveloppe = {"detail": MESSAGES_FR["CET_AGENT_NE_T_APPARTIENT_PAS"]}
        self.assertTrue(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe["detail"], MESSAGES_EN["CET_AGENT_NE_T_APPARTIENT_PAS"])

    def test_ancien_detail_texte_personnalise_est_preserve(self):
        enveloppe = {"detail": "Ce message est propre à cette route."}
        avant = dict(enveloppe)
        self.assertFalse(_traduire_enveloppe(enveloppe))
        self.assertEqual(enveloppe, avant)

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
