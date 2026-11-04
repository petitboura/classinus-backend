"""
Vérifie le routage DeepSeek par Vultr sans appel réseau (04/11/2026).

Interrupteur OFF = route habituelle comme avant (Baseten ou direct). ON (+ clé + identifiant) :
Vultr reçoit l'identifiant Vultr. Crédit, quota, clé ou modèle refusés par Vultr = repli aussitôt
sur la route habituelle, sans erreur, avec mise à l'écart de Vultr pour 10 minutes. Toute autre
erreur remonte comme avant. Le palier pro, sans identifiant Vultr, ne passe jamais par Vultr.
"""

import copy
import sys
import types
import unittest
from unittest.mock import patch

from core import adaptateur_baseten
from core import adaptateur_vultr_deepseek
from core import fournisseurs_llm
from core.adaptateur_baseten import BASE_URL_BASETEN, BASE_URL_DEEPSEEK_DIRECT, reinitialiser_circuit_baseten
from core.adaptateur_vultr_deepseek import (
    ClientVultrDeepseek,
    est_erreur_repli_vultr,
    reinitialiser_circuit_vultr,
    vultr_circuit_ouvert,
)

NS = types.SimpleNamespace

FLASH_DIRECT = "deepseek-v4-flash"
FLASH_VULTR = "deepseek-v4.1-flash-1017"
PRO_DIRECT = "deepseek-v4-pro"
FLASH_BASETEN = "deepseek-ai/DeepSeek-V4-Flash-0731"
URL_VULTR = fournisseurs_llm.ADRESSE_VULTR_PAR_DEFAUT


class ErreurStatut(Exception):
    def __init__(self, statut, message):
        super().__init__(message)
        self.status_code = statut


class FauxCompletions:
    """Enregistre les appels et rejoue une réponse ou une erreur programmée."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.appels = []
        self.effet = lambda **kw: {"route": base_url, "model": kw.get("model")}

    def create(self, **arguments):
        self.appels.append(arguments)
        return self.effet(**arguments)


class FauxClientOpenAI:
    instances = []

    def __init__(self, api_key=None, base_url=None, **reste):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = NS(completions=FauxCompletions(base_url))
        FauxClientOpenAI.instances.append(self)


def faux_client(base_url):
    trouves = [c for c in FauxClientOpenAI.instances if c.base_url == base_url]
    assert len(trouves) == 1, f"attendu 1 client {base_url}, vu {len(trouves)}"
    return trouves[0]


def clients_a(base_url):
    return [c for c in FauxClientOpenAI.instances if c.base_url == base_url]


def refuse(statut, message):
    def effet(**kw):
        raise ErreurStatut(statut, message)
    return effet


CLES_TOUTES = {"DEEPSEEK_API_KEY": "d", "BASETEN_API_KEY": "b", "VULTR_INFERENCE_API_KEY": "v"}


class RoutageVultr(unittest.TestCase):
    def setUp(self):
        FauxClientOpenAI.instances = []
        reinitialiser_circuit_vultr()
        reinitialiser_circuit_baseten()
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        self.addCleanup(reinitialiser_circuit_vultr)
        self.addCleanup(reinitialiser_circuit_baseten)
        self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)

    def client_avec(self, vultr_actif, env, baseten_actif=False, sans_identifiant=False, modele=FLASH_DIRECT):
        config = copy.deepcopy(fournisseurs_llm._config_modeles_de_repli())
        config["fournisseurs"]["deepseek"]["vultr_actif"] = vultr_actif
        config["fournisseurs"]["deepseek"]["baseten_actif"] = baseten_actif
        # Identifiants Baseten posés ici, jamais lus de la configuration partagée du code : un autre
        # test (test_baseten_deepseek, sans_slug) les y supprime pour toute la suite de tests.
        for palier, slug in (("essentiel", FLASH_BASETEN), ("avance", FLASH_BASETEN), ("pro", "deepseek-ai/DeepSeek-V4-Pro-0813")):
            config["modeles"]["deepseek"][palier]["baseten"] = slug
        if not sans_identifiant:
            for palier in ("essentiel", "avance"):
                config["modeles"]["deepseek"][palier]["vultr"] = FLASH_VULTR
        parches = [
            patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=config),
            patch.dict("os.environ", env, clear=True),
            patch.object(adaptateur_baseten, "OpenAI", FauxClientOpenAI),
            patch("openai.OpenAI", FauxClientOpenAI),
            # Le projet importe ses modules des deux façons (core.x et x à plat) : selon les autres
            # tests déjà passés, creer_client_deepseek prendrait une copie que ce test ne règle pas.
            # None dans sys.modules force l'import "core." (celui que ce test règle).
            patch.dict(sys.modules, {"adaptateur_baseten": None, "adaptateur_vultr_deepseek": None}),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        return fournisseurs_llm.creer_client_deepseek(modele)

    def test_interrupteur_eteint_la_route_habituelle_sert(self):
        client = self.client_avec(False, CLES_TOUTES)
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(clients_a(URL_VULTR), [])

    def test_interrupteur_allume_vultr_recoit_l_identifiant_vultr(self):
        client = self.client_avec(True, CLES_TOUTES)
        self.assertIsInstance(client, ClientVultrDeepseek)
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        vultr = faux_client(URL_VULTR)
        self.assertEqual(len(vultr.chat.completions.appels), 1)
        self.assertEqual(vultr.chat.completions.appels[0]["model"], FLASH_VULTR)
        self.assertEqual(reponse["route"], URL_VULTR)
        self.assertEqual(clients_a(BASE_URL_DEEPSEEK_DIRECT)[0].chat.completions.appels, [])

    def test_sans_cle_vultr_la_route_habituelle_sert_meme_si_on(self):
        client = self.client_avec(True, {"DEEPSEEK_API_KEY": "d"})
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(clients_a(URL_VULTR), [])

    def test_sans_identifiant_vultr_la_route_habituelle_sert(self):
        client = self.client_avec(True, CLES_TOUTES, sans_identifiant=True)
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)

    def test_le_palier_pro_ne_passe_jamais_par_vultr(self):
        client = self.client_avec(True, CLES_TOUTES, modele=PRO_DIRECT)
        reponse = client.chat.completions.create(model=PRO_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(faux_client(BASE_URL_DEEPSEEK_DIRECT).chat.completions.appels[0]["model"], PRO_DIRECT)
        self.assertTrue(all(not c.chat.completions.appels for c in clients_a(URL_VULTR)))

    def test_credit_epuise_repart_sur_la_route_habituelle_sans_erreur(self):
        client = self.client_avec(True, CLES_TOUTES)
        vultr = faux_client(URL_VULTR)
        direct = faux_client(BASE_URL_DEEPSEEK_DIRECT)
        vultr.chat.completions.effet = refuse(402, "Insufficient credits")
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)
        self.assertEqual(len(vultr.chat.completions.appels), 1)
        self.assertEqual(direct.chat.completions.appels[0]["model"], FLASH_DIRECT)
        # Disjoncteur : l'appel suivant va directement à la route habituelle.
        self.assertTrue(vultr_circuit_ouvert())
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(len(vultr.chat.completions.appels), 1)
        self.assertEqual(len(direct.chat.completions.appels), 2)

    def test_modele_retire_chez_vultr_replie(self):
        client = self.client_avec(True, CLES_TOUTES)
        faux_client(URL_VULTR).chat.completions.effet = refuse(404, "model not found")
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)

    def test_erreur_technique_vultr_remonte_sans_repli(self):
        client = self.client_avec(True, CLES_TOUTES)
        faux_client(URL_VULTR).chat.completions.effet = refuse(500, "Internal error")
        with self.assertRaises(ErreurStatut):
            client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(faux_client(BASE_URL_DEEPSEEK_DIRECT).chat.completions.appels, [])
        self.assertFalse(vultr_circuit_ouvert())

    def test_message_de_quota_sans_statut_replie(self):
        client = self.client_avec(True, CLES_TOUTES)
        faux_client(URL_VULTR).chat.completions.effet = lambda **kw: (_ for _ in ()).throw(
            Exception("quota exceeded for this key")
        )
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_DEEPSEEK_DIRECT)

    def test_les_deux_interrupteurs_vultr_refuse_baseten_prend_le_relais(self):
        client = self.client_avec(True, CLES_TOUTES, baseten_actif=True)
        faux_client(URL_VULTR).chat.completions.effet = refuse(429, "rate limit")
        reponse = client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        self.assertEqual(reponse["route"], BASE_URL_BASETEN)
        self.assertEqual(
            faux_client(BASE_URL_BASETEN).chat.completions.appels[0]["model"],
            FLASH_BASETEN,
        )
        self.assertEqual(faux_client(BASE_URL_DEEPSEEK_DIRECT).chat.completions.appels, [])

    def test_vultr_seul_sans_autre_route_donne_la_patience_longue_et_l_erreur_remonte(self):
        client = self.client_avec(True, {"VULTR_INFERENCE_API_KEY": "v"})
        self.assertIsInstance(client, ClientVultrDeepseek)
        client.chat.completions.create(model=FLASH_DIRECT, messages=[])
        appel = faux_client(URL_VULTR).chat.completions.appels[0]
        self.assertEqual(appel["timeout"], adaptateur_vultr_deepseek.DELAI_APPEL_FOURNISSEUR_SECONDES)
        faux_client(URL_VULTR).chat.completions.effet = refuse(402, "no credit")
        with self.assertRaises(ErreurStatut):
            client.chat.completions.create(model=FLASH_DIRECT, messages=[])

    def test_effort_max_de_deepseek_part_en_high_chez_vultr(self):
        client = self.client_avec(True, CLES_TOUTES)
        client.chat.completions.create(model=FLASH_DIRECT, messages=[], reasoning_effort="max")
        client.chat.completions.create(model=FLASH_DIRECT, messages=[], reasoning_effort="low")
        appels = faux_client(URL_VULTR).chat.completions.appels
        self.assertEqual(appels[0]["reasoning_effort"], "high")
        self.assertEqual(appels[1]["reasoning_effort"], "low")

    def test_sans_aucune_cle_pas_de_client(self):
        self.assertIsNone(self.client_avec(True, {}))
        self.assertIsNone(self.client_avec(False, {}))
        self.assertEqual(FauxClientOpenAI.instances, [])

    def test_le_classifieur_distribue_bien(self):
        for statut in (401, 402, 403, 404, 429):
            self.assertTrue(est_erreur_repli_vultr(ErreurStatut(statut, "refus")), statut)
        self.assertFalse(est_erreur_repli_vultr(ErreurStatut(500, "Boom")))
        self.assertFalse(est_erreur_repli_vultr(ErreurStatut(400, "Bad request")))
        self.assertTrue(est_erreur_repli_vultr(Exception("insufficient balance")))
        enveloppee = Exception("erreur enveloppee")
        enveloppee.response = NS(status_code=403)
        self.assertTrue(est_erreur_repli_vultr(enveloppee))

    def test_le_repli_du_code_a_l_interrupteur_eteint_et_aucun_identifiant_vultr(self):
        config = fournisseurs_llm._config_modeles_de_repli()
        self.assertFalse(config["fournisseurs"]["deepseek"]["vultr_actif"])
        self.assertEqual(fournisseurs_llm.correspondance_vultr(config), {})
        self.assertNotIn("vultr", config["fournisseurs"])
        self.assertNotIn("vultr", fournisseurs_llm.ORDRE_DISTRIBUTEURS)


class LectureSupabase(unittest.TestCase):
    """La configuration lue dans Supabase porte l'interrupteur et l'identifiant Vultr."""

    class Requete:
        def __init__(self, lignes, colonnes_absentes):
            self.lignes = lignes
            self.colonnes_absentes = colonnes_absentes
            self.colonnes = ""

        def select(self, colonnes):
            self.colonnes = colonnes
            return self

        def order(self, *_):
            return self

        def execute(self):
            if any(c in self.colonnes for c in self.colonnes_absentes):
                raise RuntimeError("column does not exist")
            return NS(data=self.lignes)

    class FauxSupabase:
        def __init__(self, tables, colonnes_absentes):
            self.tables = tables
            self.colonnes_absentes = colonnes_absentes

        def table(self, nom):
            return LectureSupabase.Requete(self.tables.get(nom, []), self.colonnes_absentes)

    def tables(self):
        return {
            "fournisseurs_llm": [
                {"distributeur": "deepseek", "ordre": 4, "bientot": False, "cle_api_requise": True,
                 "variable_cle_api": "DEEPSEEK_API_KEY", "nom_affiche": "DeepSeek",
                 "baseten_actif": False, "vultr_actif": True},
            ],
            "modeles_llm": [
                {"distributeur": "deepseek", "palier": "essentiel", "niveau": 1, "modele_id": FLASH_DIRECT,
                 "label": "DeepSeek V4 Flash", "actif": True, "modele_id_baseten": None,
                 "modele_id_vultr": FLASH_VULTR},
                {"distributeur": "deepseek", "palier": "pro", "niveau": 3, "modele_id": PRO_DIRECT,
                 "label": "DeepSeek V4 Pro", "actif": True, "modele_id_baseten": None,
                 "modele_id_vultr": None},
            ],
            "textes_modeles_llm": [{"cle": "bientot", "langue": "fr", "texte": "Bientôt"}],
        }

    def lire(self, colonnes_absentes=()):
        faux = self.FauxSupabase(self.tables(), colonnes_absentes)
        with patch.dict("os.environ", {"SUPABASE_URL": "u", "SUPABASE_SECRET": "s"}, clear=True), \
                patch.object(fournisseurs_llm, "_client_supabase_config_modeles", return_value=faux), \
                patch.object(fournisseurs_llm, "_lire_acces_anticipe", return_value={}):
            return fournisseurs_llm._lire_config_modeles_supabase()

    def test_l_interrupteur_et_l_identifiant_arrivent_dans_la_config(self):
        config = self.lire()
        self.assertTrue(config["fournisseurs"]["deepseek"]["vultr_actif"])
        self.assertEqual(fournisseurs_llm.correspondance_vultr(config), {FLASH_DIRECT: FLASH_VULTR})
        self.assertNotIn("vultr", config["modeles"]["deepseek"]["pro"])

    def test_migration_pas_appliquee_interrupteur_eteint_rien_ne_casse(self):
        config = self.lire(colonnes_absentes=("vultr_actif", "modele_id_vultr"))
        self.assertFalse(config["fournisseurs"]["deepseek"]["vultr_actif"])
        self.assertEqual(fournisseurs_llm.correspondance_vultr(config), {})
        self.assertEqual(config["modeles"]["deepseek"]["essentiel"]["id"], FLASH_DIRECT)


if __name__ == "__main__":
    unittest.main()
