"""
Vérifie le routage DeepSeek par Baseten sans appel réseau (29/10/2026).

Interrupteur OFF = direct comme avant. ON (+ clé + slug) = Baseten reçoit le
slug. Crédit/quota/clé refusés par Baseten = repli aussitôt en direct, sans
erreur, avec mise à l'écart de Baseten pour 10 minutes. Toute autre erreur
remonte comme avant.
"""

import types
import unittest
from unittest.mock import patch

from core import adaptateur_baseten
from core import fournisseurs_llm
from core.adaptateur_baseten import (
    BASE_URL_BASETEN,
    BASE_URL_DEEPSEEK_DIRECT,
    ClientBaseten,
    baseten_circuit_ouvert,
    est_erreur_repli_baseten,
    reinitialiser_circuit_baseten,
)

NS = types.SimpleNamespace

FLASH_DIRECT = "deepseek-v4-flash"
FLASH_SLUG = "deepseek-ai/DeepSeek-V4-Flash-0731"


class ErreurStatut(Exception):
    def __init__(self, statut, message):
        super().__init__(message)
        self.status_code = statut


class FauxCompletions:
    """Enregistre les appels et rejoue une réponse ou une erreur programmée."""

    def __init__(self):
        self.appels = []
        self.effet = lambda **kw: {"ok": True, "model": kw.get("model")}

    def create(self, **arguments):
        self.appels.append(arguments)
        return self.effet(**arguments)


class FauxClientOpenAI:
    instances = []

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = NS(completions=FauxCompletions())
        FauxClientOpenAI.instances.append(self)


def faux_client(base_url):
    trouves = [c for c in FauxClientOpenAI.instances if c.base_url == base_url]
    assert len(trouves) == 1, f"attendu 1 client {base_url}, vu {len(trouves)}"
    return trouves[0]


class RoutageBaseten(unittest.TestCase):
    def setUp(self):
        FauxClientOpenAI.instances = []
        reinitialiser_circuit_baseten()
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        self.addCleanup(reinitialiser_circuit_baseten)
        self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)

    def client_avec(self, baseten_actif, env, sans_slug=False):
        config = fournisseurs_llm._config_modeles_de_repli()
        config["fournisseurs"]["deepseek"]["baseten_actif"] = baseten_actif
        if sans_slug:
            for paliers in config["modeles"]["deepseek"].values():
                paliers.pop("baseten", None)
        parche_supabase = patch.object(
            fournisseurs_llm, "_lire_config_modeles_supabase", return_value=config
        )
        parche_env = patch.dict("os.environ", env, clear=True)
        parche_openai = patch.object(adaptateur_baseten, "OpenAI", FauxClientOpenAI)
        parche_supabase.start()
        parche_env.start()
        parche_openai.start()
        self.addCleanup(parche_supabase.stop)
        self.addCleanup(parche_env.stop)
        self.addCleanup(parche_openai.stop)
        return fournisseurs_llm.creer_client_deepseek(FLASH_DIRECT)

    def test_interrupteur_eteint_tout_passe_en_direct(self):
        client = self.client_avec(False, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"})
        self.assertIsInstance(client, ClientBaseten)
        self.assertIsNone(client._client_baseten)
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(len(direct.chat.completions.appels), 1)
        self.assertEqual(direct.chat.completions.appels[0]["model"], FLASH_DIRECT)
        self.assertEqual(reponse["model"], FLASH_DIRECT)

    def test_interrupteur_allume_baseten_recoit_le_slug(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"})
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        baseten = faux_client(BASE_URL_BASETEN)
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(len(baseten.chat.completions.appels), 1)
        self.assertEqual(baseten.chat.completions.appels[0]["model"], FLASH_SLUG)
        self.assertEqual(direct.chat.completions.appels, [])

    def test_sans_cle_baseten_le_direct_sert_meme_si_on(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d"})
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(direct.chat.completions.appels[0]["model"], FLASH_DIRECT)
        self.assertEqual(
            [c for c in FauxClientOpenAI.instances if c.base_url == BASE_URL_BASETEN], []
        )

    def test_sans_slug_le_direct_sert(self):
        client = self.client_avec(
            True, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"}, sans_slug=True
        )
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(direct.chat.completions.appels[0]["model"], FLASH_DIRECT)

    def test_credit_epuise_repart_en_direct_sans_erreur(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"})
        baseten = faux_client(BASE_URL_BASETEN)
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        baseten.chat.completions.effet = lambda **kw: (_ for _ in ()).throw(
            ErreurStatut(402, "Insufficient credits")
        )
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["model"], FLASH_DIRECT)
        self.assertEqual(len(baseten.chat.completions.appels), 1)
        self.assertEqual(len(direct.chat.completions.appels), 1)
        self.assertEqual(direct.chat.completions.appels[0]["model"], FLASH_DIRECT)
        # Disjoncteur : l'appel suivant va directement au direct.
        self.assertTrue(baseten_circuit_ouvert())
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(len(baseten.chat.completions.appels), 1)
        self.assertEqual(len(direct.chat.completions.appels), 2)

    def test_erreur_technique_baseten_remonte_sans_repli(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"})
        baseten = faux_client(BASE_URL_BASETEN)
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        baseten.chat.completions.effet = lambda **kw: (_ for _ in ()).throw(
            ErreurStatut(500, "Internal error")
        )
        with self.assertRaises(ErreurStatut):
            client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(direct.chat.completions.appels, [])
        self.assertFalse(baseten_circuit_ouvert())

    def test_message_de_quota_sans_statut_replie(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b"})
        baseten = faux_client(BASE_URL_BASETEN)
        baseten.chat.completions.effet = lambda **kw: (_ for _ in ()).throw(
            Exception("quota exceeded for this key")
        )
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["model"], FLASH_DIRECT)

    def test_sans_aucune_cle_pas_de_client(self):
        self.assertIsNone(self.client_avec(True, {}))
        self.assertIsNone(self.client_avec(False, {}))
        self.assertEqual(FauxClientOpenAI.instances, [])

    def test_le_classifieur_distribue_bien(self):
        self.assertTrue(est_erreur_repli_baseten(ErreurStatut(401, "Unauthorized")))
        self.assertTrue(est_erreur_repli_baseten(ErreurStatut(402, "Pay up")))
        self.assertTrue(est_erreur_repli_baseten(ErreurStatut(403, "Forbidden")))
        self.assertTrue(est_erreur_repli_baseten(ErreurStatut(429, "Slow down")))
        self.assertFalse(est_erreur_repli_baseten(ErreurStatut(500, "Boom")))
        self.assertFalse(est_erreur_repli_baseten(ErreurStatut(404, "Nope")))
        self.assertTrue(est_erreur_repli_baseten(Exception("insufficient balance")))
        erreur_enveloppee = Exception("erreur enveloppee")
        erreur_enveloppee.response = NS(status_code=403)
        self.assertTrue(est_erreur_repli_baseten(erreur_enveloppee))
        self.assertTrue(est_erreur_repli_baseten(Exception("payment required")))

    def test_le_repli_du_code_contient_l_interrupteur_et_les_slugs(self):
        config = fournisseurs_llm._config_modeles_de_repli()
        self.assertFalse(config["fournisseurs"]["deepseek"]["baseten_actif"])
        flash = config["modeles"]["deepseek"]["essentiel"]
        pro = config["modeles"]["deepseek"]["pro"]
        self.assertEqual(flash["baseten"], FLASH_SLUG)
        self.assertEqual(pro["baseten"], "deepseek-ai/DeepSeek-V4-Pro-0813")


if __name__ == "__main__":
    unittest.main()
