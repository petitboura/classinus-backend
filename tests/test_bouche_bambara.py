"""Tests hors ligne de la bouche bambara : catalogue, validation, WAV, service et relais.

Aucun modèle n'est téléchargé et PyTorch n'est pas nécessaire : le modèle et le tokenizer
sont remplacés par de faux objets. Le relais est testé avec une fausse authentification.
"""
from __future__ import annotations

import io
import os
import sys
import types
import unittest
import wave
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from core import bouche_bambara as bouche  # noqa: E402
from core.erreurs import MESSAGES_EN, MESSAGES_FR  # noqa: E402


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
def _faux_torch():
    faux = types.ModuleType("torch")

    @contextmanager
    def inference_mode():
        yield

    faux.inference_mode = inference_mode
    with mock.patch.dict(sys.modules, {"torch": faux}):
        yield


@contextmanager
def _voix_chargees(modele=None):
    modele = modele or _FauxModele()
    cache = {voix: (_faux_tokenizer, modele) for voix in bouche.VOIX}
    with mock.patch.object(bouche, "_cache", cache), _faux_torch():
        yield modele


class CatalogueTests(unittest.TestCase):
    def test_toutes_les_voix_par_defaut(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOUCHE_VOIX_ACTIVES", None)
            self.assertEqual(bouche.voix_actives(), list(bouche.VOIX))

    def test_voix_choisies_par_variable_et_inconnues_ignorees(self):
        with mock.patch.dict(os.environ, {"BOUCHE_VOIX_ACTIVES": "bam_vits, nexiste_pas"}):
            self.assertEqual(bouche.voix_actives(), ["bam_vits"])
            self.assertEqual([v["id"] for v in bouche.lister_voix()], ["bam_vits"])

    def test_la_voix_non_commerciale_est_signalee(self):
        statuts = {v["id"]: v["licence"] for v in bouche.lister_voix()}
        self.assertEqual(statuts["mms_sudoping01"], "non_commercial")

    def test_la_description_ne_contient_aucun_texte_a_traduire(self):
        for voix in bouche.lister_voix():
            self.assertEqual(set(voix), {"id", "nom", "depot", "locuteurs", "licence", "experimental"})

    def test_texte_max_par_variable_et_valeur_invalide(self):
        with mock.patch.dict(os.environ, {"BOUCHE_TEXTE_MAX": "42"}):
            self.assertEqual(bouche.texte_max(), 42)
        with mock.patch.dict(os.environ, {"BOUCHE_TEXTE_MAX": "abc"}):
            self.assertEqual(bouche.texte_max(), bouche.TEXTE_MAX_DEFAUT)

    def test_tous_les_codes_ont_un_message_fr_et_en(self):
        codes = [c for c in MESSAGES_FR if c.startswith("BOUCHE_")]
        self.assertGreaterEqual(len(codes), 7)
        for code in codes:
            self.assertIn(code, MESSAGES_EN)
            self.assertNotIn("--", MESSAGES_FR[code])
            self.assertNotIn("--", MESSAGES_EN[code])


class ValidationTests(unittest.TestCase):
    def _code(self, *args):
        with self.assertRaises(bouche.BoucheErreur) as ctx:
            bouche.valider_demande(*args)
        return ctx.exception.code

    def test_voix_inconnue(self):
        self.assertEqual(self._code("nexiste_pas", "An ka taa", 0), "BOUCHE_VOIX_INCONNUE")

    def test_voix_non_activee(self):
        with mock.patch.dict(os.environ, {"BOUCHE_VOIX_ACTIVES": "mms_sudoping01"}):
            self.assertEqual(self._code("bam_vits", "An ka taa", 0), "BOUCHE_VOIX_INCONNUE")

    def test_texte_vide_ou_espaces(self):
        self.assertEqual(self._code("bam_vits", "   ", 0), "BOUCHE_TEXTE_VIDE")

    def test_texte_trop_long(self):
        with mock.patch.dict(os.environ, {"BOUCHE_TEXTE_MAX": "5"}):
            self.assertEqual(self._code("bam_vits", "123456", 0), "BOUCHE_TEXTE_TROP_LONG")

    def test_locuteur_hors_limites(self):
        self.assertEqual(self._code("bam_vits", "An ka taa", 20), "BOUCHE_LOCUTEUR_INVALIDE")
        self.assertEqual(self._code("bam_vits", "An ka taa", -1), "BOUCHE_LOCUTEUR_INVALIDE")
        self.assertEqual(self._code("mms_sudoping01", "An ka taa", 1), "BOUCHE_LOCUTEUR_INVALIDE")

    def test_demande_valide_nettoie_le_texte(self):
        self.assertEqual(bouche.valider_demande("bam_vits", "  An ka taa.  ", 19), ("An ka taa.", 19))


class SyntheseTests(unittest.TestCase):
    def test_wav_valide_et_signal_borne(self):
        audio = bouche.encoder_wav([0.0, 0.5, -0.5, 1.5, -1.5], 16000)
        with wave.open(io.BytesIO(audio)) as f:
            self.assertEqual((f.getnchannels(), f.getsampwidth(), f.getframerate()), (1, 2, 16000))
            valeurs = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
        self.assertEqual(valeurs.max(), 32767)
        self.assertEqual(valeurs.min(), -32767)

    def test_voix_multi_locuteurs_recoit_le_locuteur_et_des_minuscules(self):
        with _voix_chargees() as modele:
            audio = bouche.synthetiser("bam_vits", "An Ka Taa", 7)
        self.assertEqual(modele.appels[0]["speaker_id"], 7)
        self.assertEqual(_faux_tokenizer.dernier_texte, "an ka taa")
        self.assertTrue(audio.startswith(b"RIFF"))

    def test_voix_mono_locuteur_sans_speaker_id_et_casse_conservee(self):
        with _voix_chargees() as modele:
            bouche.synthetiser("mms_sudoping01", "An Ka Taa", 0)
        self.assertNotIn("speaker_id", modele.appels[0])
        self.assertEqual(_faux_tokenizer.dernier_texte, "An Ka Taa")

    def test_echec_du_modele_donne_un_code_stable(self):
        modele = _FauxModele()
        modele.__class__ = type("Casse", (_FauxModele,), {"__call__": lambda self, **k: 1 / 0})
        with _voix_chargees(modele):
            with self.assertRaises(bouche.BoucheErreur) as ctx:
                bouche.synthetiser("bam_vits", "An ka taa", 0)
        self.assertEqual(ctx.exception.code, "BOUCHE_SYNTHESE_ECHEC")

    def test_chargement_impossible_donne_indisponible(self):
        faux = types.ModuleType("transformers")
        faux.AutoTokenizer = types.SimpleNamespace(from_pretrained=mock.Mock(side_effect=OSError("hors ligne")))
        faux.VitsModel = types.SimpleNamespace(from_pretrained=mock.Mock())
        with mock.patch.object(bouche, "_cache", {}), mock.patch.dict(sys.modules, {"transformers": faux}):
            with self.assertRaises(bouche.BoucheErreur) as ctx:
                bouche.synthetiser("bam_vits", "An ka taa", 0)
        self.assertEqual(ctx.exception.code, "BOUCHE_INDISPONIBLE")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from api.main_bouche import app

        self.client = TestClient(app)
        self.entetes = {"Authorization": "Bearer secret-test"}
        patcher = mock.patch.dict(os.environ, {"SUPABASE_SECRET": "secret-test"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sante_sans_jeton(self):
        self.assertEqual(self.client.get("/sante").json()["service"], "bouche-bambara")

    def test_voix_et_synthese_refusees_sans_bon_jeton(self):
        self.assertEqual(self.client.get("/voix").status_code, 401)
        self.assertEqual(self.client.get("/voix", headers={"Authorization": "Bearer faux"}).status_code, 401)
        corps = {"voix": "bam_vits", "texte": "An ka taa"}
        self.assertEqual(self.client.post("/synthese", json=corps).status_code, 401)

    def test_sans_secret_configure_tout_est_refuse(self):
        with mock.patch.dict(os.environ, {"SUPABASE_SECRET": ""}):
            self.assertEqual(self.client.get("/voix", headers={"Authorization": "Bearer "}).status_code, 401)

    def test_liste_des_voix(self):
        donnees = self.client.get("/voix", headers=self.entetes).json()
        self.assertEqual({v["id"] for v in donnees["voix"]}, set(bouche.VOIX))
        self.assertEqual(donnees["texte_max"], bouche.texte_max())

    def test_synthese_renvoie_un_wav(self):
        with _voix_chargees():
            r = self.client.post("/synthese", headers=self.entetes, json={"voix": "bam_vits", "texte": "An ka taa", "locuteur": 3})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "audio/wav")
        self.assertTrue(r.content.startswith(b"RIFF"))

    def test_erreur_de_validation_au_format_standard(self):
        r = self.client.post("/synthese", headers=self.entetes, json={"voix": "nexiste_pas", "texte": "An ka taa"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "BOUCHE_VOIX_INCONNUE")


class RelaisTests(unittest.TestCase):
    """Le relais est importé avec une fausse authentification (pas de base Supabase ici)."""

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        self.admin = True
        faux_auth = types.ModuleType("api.auth")
        faux_auth.utilisateur_courant = lambda: types.SimpleNamespace(id="u1")
        faux_perm = types.ModuleType("api.permissions_hierarchie")
        faux_perm._est_admin = lambda _id: self.admin
        modules = {"api.auth": faux_auth, "api.permissions_hierarchie": faux_perm}
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("api.bouche", None)
        self.addCleanup(sys.modules.pop, "api.bouche", None)
        from api import bouche as relais

        self.relais = relais
        app = FastAPI()
        app.include_router(relais.router)
        self.client = TestClient(app)
        env = mock.patch.dict(os.environ, {"BOUCHE_URL": "http://bouche.internal:8000/", "SUPABASE_SECRET": "secret-test"})
        env.start()
        self.addCleanup(env.stop)

    def _reponse(self, statut, json=None, contenu=b""):
        r = mock.Mock()
        r.status_code = statut
        r.json.return_value = json
        r.content = contenu
        return r

    def test_refuse_un_non_admin(self):
        self.admin = False
        r = self.client.get("/api/bouche/voix")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "PAS_LE_DROIT_ADMIN")

    def test_non_configure_sans_url(self):
        with mock.patch.dict(os.environ, {"BOUCHE_URL": ""}):
            r = self.client.get("/api/bouche/voix")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "BOUCHE_NON_CONFIGUREE")

    def test_synthese_relayee_avec_le_jeton_interne(self):
        with mock.patch.object(self.relais.httpx, "post", return_value=self._reponse(200, contenu=b"RIFFxxxx")) as post:
            r = self.client.post("/api/bouche/synthese", json={"voix": "bam_vits", "texte": "An ka taa"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"RIFFxxxx")
        self.assertEqual(post.call_args.args[0], "http://bouche.internal:8000/synthese")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer secret-test"})

    def test_code_d_erreur_du_service_conserve(self):
        corps = {"detail": {"code": "BOUCHE_TEXTE_TROP_LONG", "message": "x"}}
        with mock.patch.object(self.relais.httpx, "post", return_value=self._reponse(400, json=corps)):
            r = self.client.post("/api/bouche/synthese", json={"voix": "bam_vits", "texte": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "BOUCHE_TEXTE_TROP_LONG")

    def test_reponse_inattendue_devient_indisponible(self):
        with mock.patch.object(self.relais.httpx, "post", return_value=self._reponse(502, json=None)):
            r = self.client.post("/api/bouche/synthese", json={"voix": "bam_vits", "texte": "x"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "BOUCHE_INDISPONIBLE")

    def test_service_injoignable(self):
        with mock.patch.object(self.relais.httpx, "get", side_effect=self.relais.httpx.ConnectError("x")):
            r = self.client.get("/api/bouche/voix")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "BOUCHE_INDISPONIBLE")


if __name__ == "__main__":
    unittest.main()
