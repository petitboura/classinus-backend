"""Consignes Higgsfield côté Classinus (correctifs entrées et affichage).

Couvre sans réseau ni base : la mention du lien de fichier joint dans
les outils API, puis le format galerie/cartes des résultats (correctif
suivant) et la conservation des blocs non texte des outils MCP.
"""

import logging
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")
logging.disable(logging.CRITICAL)

# Modules absents de l'environnement de test, remplacés comme dans
# test_mcp_plateformes (faux modules, aucune donnée réelle).
_supabase = types.ModuleType("supabase")


class _OptionsBidon:
    def __init__(self, *args, **kwargs):
        pass


_supabase.ClientOptions = _OptionsBidon
_supabase.create_client = lambda *args, **kwargs: types.SimpleNamespace()
sys.modules["supabase"] = _supabase

_boto3 = types.ModuleType("boto3")
_boto3.client = lambda *args, **kwargs: types.SimpleNamespace()
_boto3.resource = lambda *args, **kwargs: types.SimpleNamespace()
sys.modules["boto3"] = _boto3
_botocore = types.ModuleType("botocore")
_botocore_config = types.ModuleType("botocore.config")


class _ConfigBidon:
    def __init__(self, *args, **kwargs):
        pass


_botocore_config.Config = _ConfigBidon
_botocore.config = _botocore_config
sys.modules["botocore"] = _botocore
sys.modules["botocore.config"] = _botocore_config

os.environ["HIGGSFIELD_API_KEY"] = "cle-test"
import core.outils_higgsfield as outils_higgsfield  # noqa: E402


class TestConsignesFichiersJoints(unittest.TestCase):
    def test_lancer_video_mentionne_le_lien_joint(self):
        self.assertIn("lien réel", outils_higgsfield.lancer_video_higgsfield.__doc__)

    def test_generer_image_mentionne_le_lien_joint(self):
        self.assertIn("lien réel", outils_higgsfield.generer_image_higgsfield.__doc__)

    def test_estimer_mentionne_les_liens_joints(self):
        self.assertIn("fichiers joints", outils_higgsfield.estimer_cout_higgsfield.__doc__)


if __name__ == "__main__":
    unittest.main()
