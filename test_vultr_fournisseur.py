"""Vérifie le branchement de Vultr Serverless Inference (03/11/2026), sans appel réseau."""

import contextlib
import os
import sys
import unittest
from unittest.mock import patch

from core import fournisseurs_llm
from core.clients_outils_llm import client_avec_outils, modele_a_des_outils
from core.efforts_modeles import effort_valide_pour_modele, efforts_pour_modele, est_modele_avec_adaptateur
from core.fournisseurs_llm import (
    ADRESSE_VULTR_PAR_DEFAUT,
    _STREAMERS_PAR_DISTRIBUTEUR,
    _config_modeles_de_repli,
    _stream_vultr,
    adresse_vultr,
    creer_client_vultr,
    modele_id_est_autorise,
    modeles_disponibles_pour_agent,
    reinitialiser_cache_config_modeles,
)

# Identifiant de test inventé, jamais un vrai modèle : les vrais identifiants se testent avec de
# vrais appels (scripts/sonder_vultr.py) puis se posent dans Supabase.
MODELE_TEST = "modele-test-vultr"


def _config_avec_modele_vultr(config):
    config["modeles"]["vultr"] = {"avance": {"id": MODELE_TEST, "label": "Modèle test Vultr"}}


def _instances_du_module():
    """Le module fournisseurs_llm, et sa copie "a plat" si un autre test l'a deja importee
    (le projet l'importe des deux facons : core.fournisseurs_llm et fournisseurs_llm)."""
    instances = [fournisseurs_llm]
    plat = sys.modules.get("fournisseurs_llm")
    if plat is not None and plat is not fournisseurs_llm:
        instances.append(plat)
    return instances


@contextlib.contextmanager
def _avec_vultr_dans_supabase():
    config = _config_modeles_de_repli()
    _config_avec_modele_vultr(config)
    with contextlib.ExitStack() as pile:
        for instance in _instances_du_module():
            instance.reinitialiser_cache_config_modeles()
            pile.enter_context(patch.object(instance, "_lire_config_modeles_supabase", return_value=config))
        yield
        for instance in _instances_du_module():
            instance.reinitialiser_cache_config_modeles()


class FauxOpenAI:
    """Remplace openai.OpenAI : note l'adresse et la clé, renvoie un flux d'un seul morceau."""

    dernier = {}

    def __init__(self, api_key=None, base_url=None, **options):
        FauxOpenAI.dernier = {"cle": api_key, "base_url": base_url, "options": options, "appels": []}
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        FauxOpenAI.dernier["appels"].append(kwargs)
        delta = type("D", (), {"content": "bonjour"})()
        morceau = type("M", (), {"choices": [type("C", (), {"delta": delta})()]})()
        return iter([morceau])


class VultrBase(unittest.TestCase):
    def setUp(self):
        reinitialiser_cache_config_modeles()
        self.addCleanup(reinitialiser_cache_config_modeles)


class Configuration(VultrBase):
    def test_vultr_est_le_dernier_de_la_hierarchie_et_sa_cle_est_connue(self):
        config = _config_modeles_de_repli()
        self.assertEqual(config["distributeurs"][-1], "vultr")
        self.assertEqual(config["fournisseurs"]["vultr"]["variable_cle_api"], "VULTR_INFERENCE_API_KEY")
        # Aucun identifiant de modèle codé en dur : tout vient de Supabase.
        self.assertNotIn("vultr", config["modeles"])

    def test_adresse_par_defaut_et_reglable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(adresse_vultr(), ADRESSE_VULTR_PAR_DEFAUT)
        with patch.dict(os.environ, {"VULTR_INFERENCE_BASE_URL": "https://exemple.test/v1"}, clear=True):
            self.assertEqual(adresse_vultr(), "https://exemple.test/v1")

    def test_streamer_enregistre(self):
        self.assertIn("vultr", _STREAMERS_PAR_DISTRIBUTEUR)


class DansLeSelecteur(VultrBase):
    def test_sans_cle_le_fournisseur_reste_invisible(self):
        with _avec_vultr_dans_supabase(), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(modeles_disponibles_pour_agent("claude", "pro"), [])
            self.assertFalse(modele_id_est_autorise(MODELE_TEST, "claude", "pro"))

    def test_avec_cle_le_modele_est_choisissable_sans_reglage_d_effort(self):
        with _avec_vultr_dans_supabase(), patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "v"}, clear=True):
            disponibles = modeles_disponibles_pour_agent("claude", "pro")
            self.assertEqual([m["modele_id"] for m in disponibles], [MODELE_TEST])
            self.assertEqual(disponibles[0]["distributeur"], "vultr")
            self.assertEqual(disponibles[0]["efforts"], [])
            self.assertIsNone(disponibles[0]["effort_defaut"])
            self.assertTrue(modele_id_est_autorise(MODELE_TEST, "claude", "pro"))

    def test_un_agent_debloque_a_meta_voit_vultr_car_il_est_dernier(self):
        with _avec_vultr_dans_supabase(), patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "v"}, clear=True):
            self.assertEqual({m["distributeur"] for m in modeles_disponibles_pour_agent("meta", "pro")}, {"vultr"})
            self.assertEqual({m["distributeur"] for m in modeles_disponibles_pour_agent("vultr", "pro")}, {"vultr"})


class ClientsEtOutils(VultrBase):
    def test_client_pointe_sur_vultr_avec_la_cle(self):
        with patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "cle-test"}, clear=True), patch("openai.OpenAI", FauxOpenAI):
            client = creer_client_vultr()
        self.assertIsNotNone(client)
        self.assertEqual(FauxOpenAI.dernier["cle"], "cle-test")
        self.assertEqual(FauxOpenAI.dernier["base_url"], ADRESSE_VULTR_PAR_DEFAUT)

    def test_sans_cle_pas_de_client(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(creer_client_vultr())

    def test_modele_vultr_recoit_les_outils_avec_un_client_openai(self):
        with _avec_vultr_dans_supabase(), patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "cle-test"}, clear=True), \
                patch("openai.OpenAI", FauxOpenAI):
            self.assertTrue(modele_a_des_outils(MODELE_TEST))
            self.assertTrue(est_modele_avec_adaptateur(MODELE_TEST))
            client = client_avec_outils(MODELE_TEST)
        self.assertIsInstance(client, FauxOpenAI)
        self.assertEqual(FauxOpenAI.dernier["base_url"], ADRESSE_VULTR_PAR_DEFAUT)

    def test_sans_cle_pas_d_outils(self):
        with _avec_vultr_dans_supabase(), patch.dict(os.environ, {}, clear=True):
            self.assertFalse(modele_a_des_outils(MODELE_TEST))
            self.assertIsNone(client_avec_outils(MODELE_TEST))

    def test_aucun_effort_envoye_pour_un_modele_vultr(self):
        # La boucle d'agent (core/boucle_agent.py:_effort_reflexion) passe par ces deux fonctions
        # pour tout modele "avec adaptateur" : None veut dire que reasoning_effort n'est pas envoye.
        with _avec_vultr_dans_supabase():
            self.assertEqual(efforts_pour_modele(MODELE_TEST, "vultr"), [])
            self.assertIsNone(effort_valide_pour_modele(MODELE_TEST, "high"))
            self.assertIsNone(effort_valide_pour_modele(MODELE_TEST, None))


class Flux(VultrBase):
    def test_flux_texte_utilise_l_adresse_vultr(self):
        with patch.dict(os.environ, {"VULTR_INFERENCE_API_KEY": "cle-test"}, clear=True), patch("openai.OpenAI", FauxOpenAI):
            texte = "".join(_stream_vultr(MODELE_TEST, "consigne", [{"role": "user", "content": "salut"}]))
        self.assertEqual(texte, "bonjour")
        appel = FauxOpenAI.dernier["appels"][0]
        self.assertEqual(appel["model"], MODELE_TEST)
        self.assertEqual(appel["messages"][0], {"role": "system", "content": "consigne"})
        self.assertTrue(appel["stream"])
        self.assertEqual(FauxOpenAI.dernier["base_url"], ADRESSE_VULTR_PAR_DEFAUT)

    def test_flux_sans_cle_leve_une_erreur_claire(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                list(_stream_vultr(MODELE_TEST, "", [{"role": "user", "content": "salut"}]))


if __name__ == "__main__":
    unittest.main()
