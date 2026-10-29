"""Consignes Higgsfield côté Classinus (correctifs entrées et affichage).

Couvre sans réseau ni base : la mention du lien de fichier joint dans
les outils API, puis le format galerie/cartes des résultats (correctif
suivant) et la conservation des blocs non texte des outils MCP.
"""

import json
import logging
import os
import sys
import types
import unittest
from unittest.mock import patch

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

_paquet_connexions = types.ModuleType("connexions")
_paquet_connexions.__path__ = []
sys.modules.setdefault("connexions", _paquet_connexions)
for _nom_connexion in ("notion", "higgsfield_mcp", "platform_mcp_oauth"):
    _module_connexion = types.ModuleType(f"connexions.{_nom_connexion}")
    _module_connexion.obtenir_token_valide = lambda *args, **kwargs: None
    sys.modules[f"connexions.{_nom_connexion}"] = _module_connexion

os.environ["HIGGSFIELD_API_KEY"] = "cle-test"
import core.outils_higgsfield as outils_higgsfield  # noqa: E402
import core.mcp_tools as mcp_tools  # noqa: E402

# Les faux modules ne doivent pas fuir vers les autres fichiers de test
# exécutés dans le même processus : retirés sitôt les imports faits
# (les modules importés gardent leurs références, rien ne change pour eux).
for _nom_faux in (
    "supabase",
    "boto3",
    "botocore",
    "botocore.config",
    "connexions",
    "connexions.notion",
    "connexions.higgsfield_mcp",
    "connexions.platform_mcp_oauth",
):
    sys.modules.pop(_nom_faux, None)


class TestConsignesFichiersJoints(unittest.TestCase):
    def test_lancer_video_mentionne_le_lien_joint(self):
        self.assertIn("lien réel", outils_higgsfield.lancer_video_higgsfield.__doc__)

    def test_generer_image_mentionne_le_lien_joint(self):
        self.assertIn("lien réel", outils_higgsfield.generer_image_higgsfield.__doc__)

    def test_estimer_mentionne_les_liens_joints(self):
        self.assertIn("fichiers joints", outils_higgsfield.estimer_cout_higgsfield.__doc__)


class TestSuiviGalerie(unittest.TestCase):
    def _suivi(self, etat, url, genre):
        with (
            patch.object(
                outils_higgsfield,
                "statut_generation",
                return_value={"etat": etat, "url": url, "erreur": None},
            ),
            patch.object(outils_higgsfield, "_sauvegarder_generation_bibliotheque"),
        ):
            return outils_higgsfield._texte_suivi("rid1", "Mon titre", genre, ctx=None)

    def test_video_terminee_renvoie_json_videos(self):
        resultat = json.loads(self._suivi("terminee", "https://cdn.test/v.mp4", "video"))
        self.assertEqual(resultat["videos"][0]["url"], "https://cdn.test/v.mp4")
        self.assertEqual(resultat["videos"][0]["titre"], "Mon titre")

    def test_image_terminee_renvoie_json_images(self):
        resultat = json.loads(self._suivi("terminee", "https://cdn.test/i.png", "image"))
        self.assertEqual(resultat["images"][0]["url"], "https://cdn.test/i.png")
        self.assertEqual(resultat["images"][0]["titre"], "Mon titre")

    def test_sans_url_reste_texte(self):
        self.assertIn("pas encore disponible", self._suivi("terminee", None, "video"))

    def test_echec_reste_texte(self):
        self.assertIn("facturée", self._suivi("echec", None, "video"))


class TestBlocsMcp(unittest.TestCase):
    def test_textes_joints(self):
        blocs = [types.SimpleNamespace(text="bonjour"), types.SimpleNamespace(text="le monde")]
        self.assertEqual(mcp_tools._texte_depuis_blocs_mcp(blocs), "bonjour\nle monde")

    def test_image_native_devient_galerie(self):
        blocs = [
            types.SimpleNamespace(text="voici"),
            types.SimpleNamespace(data="QUJD", mimeType="image/png"),
        ]
        resultat = json.loads(mcp_tools._texte_depuis_blocs_mcp(blocs))
        self.assertEqual(resultat["text"], "voici")
        self.assertEqual(resultat["images"][0]["url"], "data:image/png;base64,QUJD")

    def test_image_seule_sans_texte(self):
        blocs = [types.SimpleNamespace(data="QUJD", mimeType="image/jpeg")]
        resultat = json.loads(mcp_tools._texte_depuis_blocs_mcp(blocs))
        self.assertNotIn("text", resultat)
        self.assertEqual(resultat["images"][0]["url"], "data:image/jpeg;base64,QUJD")

    def test_son_reste_lisible_en_texte(self):
        blocs = [types.SimpleNamespace(data="QUJD", mimeType="audio/mp3")]
        texte = mcp_tools._texte_depuis_blocs_mcp(blocs)
        self.assertIn("data:audio/mp3;base64,QUJD", texte)

    def test_ressource_embarquee_par_son_adresse(self):
        ressource = types.SimpleNamespace(uri="https://fichiers.test/doc.pdf")
        blocs = [types.SimpleNamespace(resource=ressource)]
        self.assertIn("https://fichiers.test/doc.pdf", mcp_tools._texte_depuis_blocs_mcp(blocs))

    def test_vide_renvoie_vide(self):
        self.assertEqual(mcp_tools._texte_depuis_blocs_mcp(None), "")
        self.assertEqual(mcp_tools._texte_depuis_blocs_mcp([]), "")
        self.assertEqual(mcp_tools._texte_depuis_blocs_mcp([object()]), "")


class TestMoissonHiggsfield(unittest.TestCase):
    def test_autre_serveur_inchange(self):
        texte = "voir https://cdn.test/i.png"
        self.assertEqual(mcp_tools._enveloppe_medias_higgsfield("notion-search", texte), texte)

    def test_sans_lien_inchange(self):
        texte = "Travail lancé (id: abc123)."
        self.assertEqual(mcp_tools._enveloppe_medias_higgsfield("higgsfield_generate_video", texte), texte)

    def test_lien_image_en_galerie(self):
        texte = '{"status": "completed", "rawUrl": "https://cdn.test/i.png"}'
        resultat = json.loads(mcp_tools._enveloppe_medias_higgsfield("higgsfield_generate_image", texte))
        self.assertEqual(resultat["text"], texte)
        self.assertEqual(resultat["images"][0]["url"], "https://cdn.test/i.png")

    def test_lien_video_en_cartes(self):
        texte = "Terminé : https://cdn.test/v.mp4 (voir aussi https://cdn.test/v.mp4)."
        resultat = json.loads(mcp_tools._enveloppe_medias_higgsfield("higgsfield_generate_video", texte))
        self.assertEqual(len(resultat["videos"]), 1)
        self.assertEqual(resultat["videos"][0]["url"], "https://cdn.test/v.mp4")

    def test_deja_en_galerie_inchange(self):
        texte = '{"images": [{"titre": "x", "url": "https://cdn.test/i.png"}]}'
        self.assertEqual(mcp_tools._enveloppe_medias_higgsfield("higgsfield_generate_image", texte), texte)


if __name__ == "__main__":
    unittest.main()
