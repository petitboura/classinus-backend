"""La clé privée VAPID est lue sous ses trois formes (20/10/2026)."""

import base64
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from core import notifications_push


def _pem():
    cle = ec.generate_private_key(ec.SECP256R1())
    return cle.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")


class CleVapid(unittest.TestCase):
    def _lire(self, valeur):
        with patch.object(notifications_push, "_get_secret", return_value=valeur):
            return notifications_push._pem_prive()

    def _charge(self, pem):
        serialization.load_pem_private_key(pem.encode("ascii"), password=None)

    def test_pem_en_base64_comme_prevu(self):
        pem = _pem()
        self._charge(self._lire(base64.b64encode(pem.encode()).decode()))

    def test_pem_colle_tel_quel(self):
        self._charge(self._lire(_pem()))

    def test_pem_avec_retours_a_la_ligne_litteraux_et_guillemets(self):
        pem = _pem().strip().replace("\n", "\\n")
        self._charge(self._lire(f'"{pem}"'))

    def test_base64_d_un_pem_a_retours_litteraux(self):
        pem = _pem().strip().replace("\n", "\\n")
        self._charge(self._lire(base64.b64encode(pem.encode()).decode()))


class EnvoiWebPushReel(unittest.TestCase):
    """
    Ajouté le 24/10/2026 : le test précédent ne chargeait la clé qu'avec `cryptography`, jamais via
    pywebpush. Or `webpush()` lit une chaîne comme du base64 DER, pas comme du PEM : une clé PEM
    pourtant valide faisait échouer chaque envoi avec « ASN.1 parsing error: invalid length »,
    et le rappel restait non envoyé, retenté chaque minute. Ce test passe par l'envoi réel.
    """

    def _envoyer(self, valeur_cle):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        b64 = lambda b: base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
        abonnement = {"endpoint": "https://push.example.test/abc", "p256dh": b64(pub), "auth": b64(b"0123456789abcdef")}

        supabase = MagicMock()
        supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
            data=[abonnement]
        )
        secrets = {"VAPID_PRIVATE_KEY_PEM_B64": valeur_cle, "VAPID_PUBLIC_KEY": "publique"}
        reponse = SimpleNamespace(status_code=201, reason="Created", text="")

        with patch.object(notifications_push, "supabase", supabase), patch.object(
            notifications_push, "_get_secret", side_effect=lambda cle: secrets.get(cle)
        ), patch("pywebpush.WebPusher.send", return_value=reponse):
            return notifications_push.envoyer_notification_push("utilisateur", "Rappel", "contenu")

    def test_envoi_avec_pem_en_base64(self):
        self.assertEqual(self._envoyer(base64.b64encode(_pem().encode()).decode()), 1)

    def test_envoi_avec_pem_colle_tel_quel(self):
        self.assertEqual(self._envoyer(_pem()), 1)

    def test_envoi_avec_retours_litteraux_et_guillemets(self):
        pem = _pem().strip().replace("\n", "\\n")
        self.assertEqual(self._envoyer(f'"{pem}"'), 1)


if __name__ == "__main__":
    unittest.main()
