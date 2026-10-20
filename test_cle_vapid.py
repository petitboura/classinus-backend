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


if __name__ == "__main__":
    unittest.main()
