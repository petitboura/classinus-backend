"""L'adresse à ouvrir au clic d'une notification suit le chat et arrive aux appareils natifs (05/11/2026).

Le chat est à la racine "/" depuis le 30/09/2026, mais les notifications de fin de réponse et de
minuteur pointaient encore vers "/chat", adresse qui n'existe plus dans l'appli Android. Et FCM
n'envoyait jamais l'adresse à l'appli, qui n'avait donc rien à ouvrir au clic.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

from core import notifications_push


def _reponse_ok():
    reponse = MagicMock()
    reponse.status_code = 200
    return reponse


class UrlDansFcm(unittest.TestCase):
    def _donnees_envoyees(self, **kwargs):
        with patch.object(notifications_push, "_get_secret", return_value="x"), patch.object(
            notifications_push, "_access_token_fcm", return_value="jeton"
        ), patch.object(notifications_push.httpx, "post", return_value=_reponse_ok()) as envoi:
            self.assertTrue(notifications_push._envoyer_fcm("token", "Titre", "Corps", **kwargs))
        return envoi.call_args.kwargs["json"]["message"]["data"]

    def test_url_transmise_a_l_appli(self):
        donnees = self._donnees_envoyees(url="/")
        self.assertEqual(donnees["url"], "/")
        self.assertEqual(donnees["title"], "Titre")

    def test_sans_url_la_cle_est_absente(self):
        self.assertNotIn("url", self._donnees_envoyees())


class UrlDansApns(unittest.TestCase):
    def _payload_envoye(self, **kwargs):
        client = MagicMock()
        client.post.return_value = _reponse_ok()
        contexte = MagicMock()
        contexte.__enter__.return_value = client
        with patch.object(notifications_push, "_jeton_apns", return_value="jeton"), patch.object(
            notifications_push.httpx, "Client", return_value=contexte
        ):
            self.assertTrue(notifications_push._envoyer_apns("token", "Titre", "Corps", **kwargs))
        return client.post.call_args.kwargs["json"]

    def test_url_hors_de_aps(self):
        payload = self._payload_envoye(url="/")
        self.assertEqual(payload["url"], "/")
        self.assertNotIn("url", payload["aps"])

    def test_sans_url_la_cle_est_absente(self):
        self.assertNotIn("url", self._payload_envoye())


class RouteChat(unittest.TestCase):
    def test_route_chat_est_la_racine(self):
        self.assertEqual(notifications_push.ROUTE_CHAT_APPLI, "/")

    def test_envoi_global_transmet_l_url_aux_appareils_natifs(self):
        table = MagicMock()
        table.select.return_value.eq.return_value.execute.return_value.data = [
            {"plateforme": "android", "token": "t-android"},
            {"plateforme": "ios", "token": "t-ios"},
        ]
        supabase_faux = MagicMock()
        supabase_faux.table.return_value = table
        with patch.object(notifications_push, "supabase", supabase_faux), patch.object(
            notifications_push, "notifications_push_disponible", return_value=False
        ), patch.object(notifications_push, "_fcm_disponible", return_value=True), patch.object(
            notifications_push, "_apns_disponible", return_value=True
        ), patch.object(notifications_push, "_envoyer_fcm", return_value=True) as fcm, patch.object(
            notifications_push, "_envoyer_apns", return_value=True
        ) as apns:
            envoyes = notifications_push.envoyer_notification_push(
                "utilisateur", "Classinus", "La réponse est terminée.", notifications_push.ROUTE_CHAT_APPLI
            )
        self.assertEqual(envoyes, 2)
        self.assertEqual(fcm.call_args.kwargs["url"], "/")
        self.assertEqual(apns.call_args.kwargs["url"], "/")


if __name__ == "__main__":
    unittest.main()
