"""Tests hors ligne du dossier bambara-bouche : aucun modèle téléchargé, PyTorch inutile.

Lancer depuis ce dossier : python3 -m unittest test_app
"""
import base64
import io
import json
import os
import sys
import types
import unittest
import urllib.error
import wave
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["PRECHARGER"] = "0"  # aucun téléchargement au démarrage pendant les tests

import numpy as np  # noqa: E402

import voix  # noqa: E402


class _Sortie:
    def __init__(self, signal):
        self.waveform = _Tenseur(signal)


class _Tenseur:
    def __init__(self, signal):
        self.signal = np.asarray(signal, dtype="float32")

    def squeeze(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.signal


class _FauxModele:
    def __init__(self):
        self.config = types.SimpleNamespace(sampling_rate=16000)
        self.appels = []

    def __call__(self, **kwargs):
        self.appels.append(kwargs)
        return _Sortie([0.0, 0.5, -0.5, 1.5, -1.5])


def _faux_tokenizer(texte, return_tensors=None):
    _faux_tokenizer.dernier_texte = texte
    return {"input_ids": [1, 2, 3]}


@contextmanager
def _voix_pretes(modele=None):
    modele = modele or _FauxModele()
    modeles = {i: (_faux_tokenizer, modele) for i in voix.VOIX}
    etats = {i: {"pret": True, "chargement": False, "erreur": None} for i in voix.VOIX}
    faux_torch = types.ModuleType("torch")

    @contextmanager
    def inference_mode():
        yield

    faux_torch.inference_mode = inference_mode
    with mock.patch.object(voix, "_modeles", modeles), mock.patch.object(voix, "_etat", etats), \
            mock.patch.dict(sys.modules, {"torch": faux_torch}):
        yield modele


class CatalogueTests(unittest.TestCase):
    def test_toutes_les_voix_par_defaut(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("VOIX_ACTIVES", None)
            self.assertEqual(voix.voix_actives(), list(voix.VOIX))

    def test_voix_choisies_et_inconnues_ignorees(self):
        with mock.patch.dict(os.environ, {"VOIX_ACTIVES": "bam_vits, nexiste_pas"}):
            self.assertEqual([v["id"] for v in voix.lister_voix()], ["bam_vits"])

    def test_description_sans_texte_a_traduire(self):
        for v in voix.lister_voix():
            self.assertEqual(set(v), {"id", "nom", "depot", "locuteurs", "licence", "experimental"})

    def test_voix_non_commerciale_signalee(self):
        statuts = {v["id"]: v["licence"] for v in voix.lister_voix()}
        self.assertEqual(statuts["mms_sudoping01"], "non_commercial")
        self.assertEqual(statuts["mms_meta"], "non_commercial")

    def test_voix_a_un_seul_locuteur_sans_speaker_id(self):
        for v in voix.lister_voix():
            if v["id"] in ("ekodi_femme", "mms_meta", "bam_fintech"):
                self.assertEqual(v["locuteurs"], 1)

    def test_texte_max_variable_et_valeur_invalide(self):
        with mock.patch.dict(os.environ, {"TEXTE_MAX": "42"}):
            self.assertEqual(voix.texte_max(), 42)
        with mock.patch.dict(os.environ, {"TEXTE_MAX": "abc"}):
            self.assertEqual(voix.texte_max(), voix.TEXTE_MAX_DEFAUT)


class ValidationTests(unittest.TestCase):
    def _statut(self, *args):
        with self.assertRaises(voix.ErreurVoix) as ctx:
            voix.valider(*args)
        return ctx.exception.statut

    def test_bruit_variable_et_valeur_invalide(self):
        with mock.patch.dict(os.environ, {"BRUIT_SCALE": "0.1", "BRUIT_DUREE": "abc"}):
            self.assertEqual(voix.bruit_scale(), 0.1)
            self.assertEqual(voix.bruit_duree(), voix.BRUIT_DUREE_DEFAUT)
        with mock.patch.dict(os.environ, {"BRUIT_SCALE": "5"}):
            self.assertEqual(voix.bruit_scale(), voix.BRUIT_DEFAUT)
        with mock.patch.dict(os.environ, {"BRUIT_SCALE": "0"}):
            self.assertEqual(voix.bruit_scale(), 0.0)

    def test_cas_refuses(self):
        self.assertEqual(self._statut("nexiste_pas", "An ka taa", 0), 404)
        self.assertEqual(self._statut("bam_vits", "   ", 0), 400)
        self.assertEqual(self._statut("bam_vits", "An ka taa", 20), 400)
        self.assertEqual(self._statut("bam_vits", "An ka taa", -1), 400)
        self.assertEqual(self._statut("mms_sudoping01", "An ka taa", 1), 400)
        with mock.patch.dict(os.environ, {"TEXTE_MAX": "5"}):
            self.assertEqual(self._statut("bam_vits", "123456", 0), 400)

    def test_voix_non_activee(self):
        with mock.patch.dict(os.environ, {"VOIX_ACTIVES": "mms_sudoping01"}):
            self.assertEqual(self._statut("bam_vits", "An ka taa", 0), 404)

    def test_demande_valide(self):
        self.assertEqual(voix.valider("bam_vits", "  An ka taa.  ", 19), ("An ka taa.", 19))


class SyntheseTests(unittest.TestCase):
    def test_wav_valide_et_signal_borne(self):
        audio = voix.encoder_wav([0.0, 0.5, -0.5, 1.5, -1.5], 16000)
        with wave.open(io.BytesIO(audio)) as f:
            self.assertEqual((f.getnchannels(), f.getsampwidth(), f.getframerate()), (1, 2, 16000))
            valeurs = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
        self.assertEqual((valeurs.max(), valeurs.min()), (32767, -32767))

    def test_multi_locuteurs_recoit_le_locuteur_et_des_minuscules(self):
        with _voix_pretes() as modele:
            audio = voix.synthetiser("bam_vits", "An Ka Taa", 7)
        self.assertEqual(modele.appels[0]["speaker_id"], 7)
        self.assertEqual(_faux_tokenizer.dernier_texte, "an ka taa")
        self.assertTrue(audio.startswith(b"RIFF"))

    def test_mono_locuteur_sans_speaker_id_et_casse_conservee(self):
        with _voix_pretes() as modele:
            voix.synthetiser("mms_sudoping01", "An Ka Taa", 0)
        self.assertNotIn("speaker_id", modele.appels[0])
        self.assertEqual(_faux_tokenizer.dernier_texte, "An Ka Taa")

    def test_voix_en_chargement_donne_503(self):
        etats = {i: {"pret": False, "chargement": True, "erreur": None} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("bam_vits", "An ka taa", 0)
        self.assertEqual(ctx.exception.statut, 503)

    def test_voix_en_echec_renvoie_le_detail(self):
        etats = {i: {"pret": False, "chargement": False, "erreur": "OSError: hors ligne"} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("bam_vits", "An ka taa", 0)
        self.assertEqual((ctx.exception.statut, ctx.exception.detail), (500, "OSError: hors ligne"))

    def test_chargement_qui_echoue_garde_l_erreur(self):
        faux = types.ModuleType("transformers")
        faux.AutoTokenizer = types.SimpleNamespace(from_pretrained=mock.Mock(side_effect=OSError("hors ligne")))
        faux.VitsModel = types.SimpleNamespace(from_pretrained=mock.Mock())
        etats = {i: {"pret": False, "chargement": False, "erreur": None} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats), mock.patch.dict(sys.modules, {"transformers": faux}):
            voix.charger("bam_vits")
        self.assertFalse(etats["bam_vits"]["pret"])
        self.assertIn("hors ligne", etats["bam_vits"]["erreur"])

    def test_chargement_signale_les_poids_manquants(self):
        faux_modele = _FauxModele()
        faux_modele.eval = lambda: None
        faux = types.ModuleType("transformers")
        faux.AutoTokenizer = types.SimpleNamespace(from_pretrained=mock.Mock(return_value=_faux_tokenizer))
        faux.VitsModel = types.SimpleNamespace(
            from_pretrained=mock.Mock(return_value=(faux_modele, {"missing_keys": ["decoder.b", "decoder.a"]}))
        )
        etats = {i: {"pret": False, "chargement": False, "erreur": None} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats), mock.patch.object(voix, "_modeles", {}), \
                mock.patch.dict(sys.modules, {"transformers": faux}):
            voix.charger("bam_vits")
        self.assertTrue(etats["bam_vits"]["pret"])
        self.assertEqual((etats["bam_vits"]["nb_manquantes"], etats["bam_vits"]["manquantes"]), (2, ["decoder.a", "decoder.b"]))

    def test_echec_du_modele_donne_un_detail(self):
        class Casse(_FauxModele):
            def __call__(self, **kwargs):
                raise ZeroDivisionError("boom")

        with _voix_pretes(Casse()):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("bam_vits", "An ka taa", 0)
        self.assertEqual(ctx.exception.statut, 500)
        self.assertIn("ZeroDivisionError", ctx.exception.detail)


class _FausseReponse:
    def __init__(self, contenu: dict):
        self._octets = json.dumps(contenu).encode("utf-8")

    def read(self):
        return self._octets

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _reponse_audio(octets: bytes, mime: str = "audio/wav"):
    donnees = base64.b64encode(octets).decode("ascii")
    return _FausseReponse({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime, "data": donnees}}]}}]})


def _erreur_http(code: int):
    return urllib.error.HTTPError("https://exemple", code, "erreur", {}, io.BytesIO(b'{"error": "detail de test"}'))


class GeminiTests(unittest.TestCase):
    def test_voix_au_catalogue_avec_modele_de_la_variable(self):
        statuts = {v["id"]: v for v in voix.lister_voix()}
        self.assertEqual(statuts["gemini_tts"]["licence"], "service_google")
        self.assertEqual(statuts["gemini_tts"]["locuteurs"], 1)
        self.assertEqual(statuts["gemini_tts"]["depot"], "gemini-3.8-flash-tts")
        with mock.patch.dict(os.environ, {"GEMINI_TTS_MODELE": "gemini-3.8-flash-lite-tts"}):
            self.assertEqual({v["id"]: v for v in voix.lister_voix()}["gemini_tts"]["depot"], "gemini-3.8-flash-lite-tts")

    def test_charger_sans_cle_garde_l_erreur(self):
        etats = {i: {"pret": False, "chargement": False, "erreur": None} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            voix.charger("gemini_tts")
        self.assertFalse(etats["gemini_tts"]["pret"])
        self.assertIn("GOOGLE_API_KEY", etats["gemini_tts"]["erreur"])

    def test_charger_avec_cle_est_pret_sans_telechargement(self):
        etats = {i: {"pret": False, "chargement": False, "erreur": None} for i in voix.VOIX}
        with mock.patch.object(voix, "_etat", etats), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test"}):
            voix.charger("gemini_tts")
        self.assertTrue(etats["gemini_tts"]["pret"])

    def test_synthese_envoie_texte_voix_modele_et_cle(self):
        wav = voix.encoder_wav([0.0, 0.5], 24000)
        with _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test", "GEMINI_TTS_VOIX": "Puck"}), \
                mock.patch.object(voix.urllib.request, "urlopen", return_value=_reponse_audio(wav)) as appel:
            audio = voix.synthetiser("gemini_tts", "  An ka taa  ", 0)
        requete = appel.call_args.args[0]
        self.assertIn("gemini-3.8-flash-tts:generateContent", requete.full_url)
        self.assertEqual(requete.get_header("X-goog-api-key"), "cle-de-test")
        corps = json.loads(requete.data.decode("utf-8"))
        self.assertEqual(corps["contents"][0]["parts"][0]["text"], "An ka taa")
        self.assertEqual(corps["generationConfig"]["speechConfig"]["voiceConfig"]["voice"], "Puck")
        self.assertEqual(corps["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(audio, wav)

    def test_pcm_brut_enveloppe_dans_un_wav_a_la_frequence_annoncee(self):
        pcm = np.array([0, 1000, -1000], dtype="<i2").tobytes()
        with _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test"}), \
                mock.patch.object(voix.urllib.request, "urlopen", return_value=_reponse_audio(pcm, "audio/L16;codec=pcm;rate=16000")):
            audio = voix.synthetiser("gemini_tts", "An ka taa", 0)
        with wave.open(io.BytesIO(audio)) as f:
            self.assertEqual((f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getnframes()), (1, 2, 16000, 3))

    def test_cle_absente_donne_500(self):
        with _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("gemini_tts", "An ka taa", 0)
        self.assertEqual(ctx.exception.statut, 500)
        self.assertIn("GOOGLE_API_KEY", ctx.exception.message)

    def test_erreurs_google_en_messages_lisibles(self):
        attendus = {429: "quota", 403: "refusé la clé", 404: "ne connaît pas ce modèle", 500: "erreur (500)"}
        for code, extrait in attendus.items():
            with self.subTest(code=code), _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test"}), \
                    mock.patch.object(voix.urllib.request, "urlopen", side_effect=_erreur_http(code)):
                with self.assertRaises(voix.ErreurVoix) as ctx:
                    voix.synthetiser("gemini_tts", "An ka taa", 0)
            self.assertEqual(ctx.exception.statut, 502)
            self.assertIn(extrait, ctx.exception.message)
            self.assertIn("detail de test", ctx.exception.detail)
            self.assertNotIn("cle-de-test", ctx.exception.message + ctx.exception.detail)

    def test_reponse_sans_son_donne_502_avec_detail(self):
        vide = _FausseReponse({"candidates": [{"finishReason": "OTHER"}], "promptFeedback": {"blockReason": "SAFETY"}})
        with _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test"}), \
                mock.patch.object(voix.urllib.request, "urlopen", return_value=vide):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("gemini_tts", "An ka taa", 0)
        self.assertEqual(ctx.exception.statut, 502)
        self.assertIn("aucun son", ctx.exception.message)
        self.assertIn("SAFETY", ctx.exception.detail)

    def test_reseau_coupe_donne_502(self):
        with _voix_pretes(), mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "cle-de-test"}), \
                mock.patch.object(voix.urllib.request, "urlopen", side_effect=OSError("hors ligne")):
            with self.assertRaises(voix.ErreurVoix) as ctx:
                voix.synthetiser("gemini_tts", "An ka taa", 0)
        self.assertEqual(ctx.exception.statut, 502)
        self.assertIn("hors ligne", ctx.exception.message)


class ServeurTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        import app as application

        self.client = TestClient(application.app)

    def test_la_page_est_servie(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Test bambara", r.text)

    def test_etat_liste_les_voix(self):
        donnees = self.client.get("/etat").json()
        self.assertEqual(set(donnees["voix"]), set(voix.VOIX))
        self.assertFalse(donnees["protege"])

    def test_liste_et_synthese(self):
        self.assertEqual({v["id"] for v in self.client.get("/voix").json()["voix"]}, set(voix.VOIX))
        with _voix_pretes():
            r = self.client.post("/synthese", json={"voix": "bam_vits", "texte": "An ka taa", "locuteur": 3})
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "audio/wav"))
        self.assertTrue(r.content.startswith(b"RIFF"))

    def test_erreur_de_validation_en_json_lisible(self):
        r = self.client.post("/synthese", json={"voix": "nexiste_pas", "texte": "An ka taa"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("n'existe pas", r.json()["erreur"])

    def test_jeton_exige_quand_defini(self):
        with mock.patch.dict(os.environ, {"TEST_ACCESS_TOKEN": "secret"}):
            self.assertTrue(self.client.get("/etat").json()["protege"])
            self.assertEqual(self.client.get("/voix").status_code, 401)
            self.assertEqual(self.client.get("/voix", headers={"X-Test-Token": "faux"}).status_code, 401)
            self.assertEqual(self.client.get("/voix", headers={"X-Test-Token": "secret"}).status_code, 200)
            corps = {"voix": "bam_vits", "texte": "An ka taa"}
            self.assertEqual(self.client.post("/synthese", json=corps).status_code, 401)


if __name__ == "__main__":
    unittest.main()
