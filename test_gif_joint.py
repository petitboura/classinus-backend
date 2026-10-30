"""GIF accepté en image jointe (correctif Higgsfield : entrées image).

Le gif est refusé à l'envoi alors qu'Higgsfield l'accepte. Après
correction : accepté comme les autres images, et ramené à sa première
image en PNG pour la lecture vision (le fichier gif d'origine reste
accessible par son lien pour les outils).
"""

import io
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

_google = types.ModuleType("google")
_google.genai = types.ModuleType("google.genai")
sys.modules["google"] = _google

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

_postgrest = types.ModuleType("postgrest")
_postgrest_exc = types.ModuleType("postgrest.exceptions")


class _APIErrorBidon(Exception):
    pass


_postgrest_exc.APIError = _APIErrorBidon
_postgrest.exceptions = _postgrest_exc
sys.modules["postgrest"] = _postgrest
sys.modules["postgrest.exceptions"] = _postgrest_exc

# Chaînes d'import trop lourdes pour ces tests (PDF, vectorisation) :
# seuls les noms utilisés par api/uploads.py sont simulés.
_faux_lecture_document = types.ModuleType("core.lecture_document_conversation")
_faux_lecture_document.infos_document = lambda *args, **kwargs: {}
_faux_lecture_document.resume_infos = lambda *args, **kwargs: ""
sys.modules["core.lecture_document_conversation"] = _faux_lecture_document
_faux_import_zip = types.ModuleType("core.import_zip")
_faux_import_zip.est_zip = lambda *args, **kwargs: False
sys.modules["core.import_zip"] = _faux_import_zip
_faux_lecture_media = types.ModuleType("core.lecture_media_conversation")
_faux_lecture_media.lire_infos = lambda *args, **kwargs: {}
_faux_lecture_media.resume_infos = lambda *args, **kwargs: ""
sys.modules["core.lecture_media_conversation"] = _faux_lecture_media
_faux_zip_chat = types.ModuleType("core.zip_chat")
_faux_zip_chat.demarrer_extraction_zip_chat = lambda *args, **kwargs: None
_faux_zip_chat.TAILLE_MAX_ZIP_CHAT_OCTETS = 0
sys.modules["core.zip_chat"] = _faux_zip_chat

import api.uploads as uploads  # noqa: E402
from lecture_urls_externes import _telecharger_image  # noqa: E402

# Les faux modules ne doivent pas fuir vers les autres fichiers de test
# exécutés dans le même processus : retirés sitôt les imports faits
# (les modules importés gardent leurs références, rien ne change pour eux).
for _nom_faux in (
    "supabase",
    "google",
    "boto3",
    "botocore",
    "botocore.config",
    "postgrest",
    "postgrest.exceptions",
    "core.lecture_document_conversation",
    "core.import_zip",
    "core.lecture_media_conversation",
    "core.zip_chat",
):
    sys.modules.pop(_nom_faux, None)


def _gif_test():
    from PIL import Image

    cadre1 = Image.new("RGB", (8, 6), (255, 0, 0))
    cadre2 = Image.new("RGB", (8, 6), (0, 0, 255))
    tampon = io.BytesIO()
    cadre1.save(tampon, format="GIF", save_all=True, append_images=[cadre2], loop=0)
    return tampon.getvalue()


class TestGifJoint(unittest.TestCase):
    def test_types_autorises_contient_gif(self):
        self.assertIn("image/gif", uploads.TYPES_AUTORISES)
        self.assertEqual(uploads.TYPES_AUTORISES["image/gif"], "gif")

    def _telecharger(self, contenu, type_mime):
        reponse = types.SimpleNamespace(
            content=contenu,
            headers={"content-type": type_mime},
            raise_for_status=lambda: None,
        )
        with (
            patch("lecture_urls_externes.valider_url_externe"),
            patch("lecture_urls_externes.requests.get", return_value=reponse),
        ):
            return _telecharger_image("https://fichiers.test/chat/x")

    def test_gif_converti_en_png_pour_la_vision(self):
        from PIL import Image

        contenu, mime = self._telecharger(_gif_test(), "image/gif")
        self.assertEqual(mime, "image/png")
        image = Image.open(io.BytesIO(contenu))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (8, 6))

    def test_jpeg_inchange(self):
        from PIL import Image

        tampon = io.BytesIO()
        Image.new("RGB", (4, 4)).save(tampon, format="JPEG")
        contenu, mime = self._telecharger(tampon.getvalue(), "image/jpeg")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(contenu, tampon.getvalue())

    def test_gif_corrompu_renvoye_tel_quel(self):
        contenu, mime = self._telecharger(b"pas-un-gif", "image/gif")
        self.assertEqual(contenu, b"pas-un-gif")
        self.assertEqual(mime, "image/gif")


if __name__ == "__main__":
    unittest.main()
