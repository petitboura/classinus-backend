"""
Verifie les modeles servis UNIQUEMENT par Vultr (04/11/2026, demande de Bourama) : Z.ai (GLM),
Alibaba (Qwen), NVIDIA (Nemotron) et Muse Glimmer de Meta. Sans appel reseau.
"""

import types
import unittest
from unittest.mock import patch

from core import adaptateur_vultr
from core import clients_outils_llm
from core import efforts_modeles
from core import fournisseurs_llm

NS = types.SimpleNamespace

CLES = {"VULTR_INFERENCE_API_KEY": "v", "DEEPSEEK_API_KEY": "d"}


class FauxModeles:
    def __init__(self, ids, erreur=None):
        self._ids = ids
        self._erreur = erreur
        self.appels = 0

    def list(self):
        self.appels += 1
        if self._erreur:
            raise self._erreur
        return NS(data=[NS(id=i) for i in self._ids])


class FauxClientVultr:
    def __init__(self, ids=()):
        self.models = FauxModeles(ids)
        self.appels = []
        self.chat = NS(completions=NS(create=self._creer))

    def _creer(self, **arguments):
        self.appels.append(arguments)
        return {"ok": True}


class Base(unittest.TestCase):
    def setUp(self):
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        adaptateur_vultr.reinitialiser_catalogue_vultr()
        parche = patch.object(fournisseurs_llm, "_lire_config_modeles_supabase", return_value=None)
        parche.start()
        self.addCleanup(parche.stop)
        self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)
        self.addCleanup(adaptateur_vultr.reinitialiser_catalogue_vultr)


class Catalogue(Base):
    def test_identifiant_exact_garde(self):
        client = FauxClientVultr(["glm-5.3", "glm-5.3-flash"])
        self.assertEqual(adaptateur_vultr.resoudre_identifiant_vultr(client, "glm-5.3"), "glm-5.3")

    def test_suffixe_de_date_retrouve_le_plus_recent(self):
        client = FauxClientVultr(["qwen3.8-27b-0901", "qwen3.8-27b-1017", "qwen3.8-flash-next"])
        self.assertEqual(adaptateur_vultr.resoudre_identifiant_vultr(client, "qwen3.8-27b"), "qwen3.8-27b-1017")

    def test_absent_du_catalogue_renvoye_tel_quel(self):
        client = FauxClientVultr(["autre"])
        self.assertEqual(adaptateur_vultr.resoudre_identifiant_vultr(client, "glm-5.3"), "glm-5.3")

    def test_catalogue_illisible_renvoye_tel_quel(self):
        client = FauxClientVultr()
        client.models = FauxModeles([], erreur=RuntimeError("reseau"))
        self.assertEqual(adaptateur_vultr.resoudre_identifiant_vultr(client, "glm-5.3"), "glm-5.3")

    def test_catalogue_en_cache(self):
        client = FauxClientVultr(["glm-5.3"])
        adaptateur_vultr.resoudre_identifiant_vultr(client, "glm-5.3")
        adaptateur_vultr.resoudre_identifiant_vultr(client, "glm-5.3")
        self.assertEqual(client.models.appels, 1)


class Client(Base):
    def test_traduit_l_identifiant_et_retire_l_effort(self):
        faux = FauxClientVultr(["nemotron-3-nano-omni-30b-a3b-reasoning"])
        client = adaptateur_vultr.ClientVultr(
            {"nemotron-nano-omni-30b-a3b-reasoning": "nemotron-3-nano-omni-30b-a3b-reasoning"}, faux)
        client.chat.completions.create(model="nemotron-nano-omni-30b-a3b-reasoning", messages=[], reasoning_effort="high")
        envoye = faux.appels[0]
        self.assertEqual(envoye["model"], "nemotron-3-nano-omni-30b-a3b-reasoning")
        self.assertNotIn("reasoning_effort", envoye)
        self.assertGreater(envoye["timeout"], 10)


class Disponibilite(Base):
    def ids(self, distributeur, palier, env):
        with patch.dict("os.environ", env, clear=True):
            return [m["modele_id"] for m in fournisseurs_llm.modeles_disponibles_pour_agent(distributeur, palier)]

    def test_sans_cle_vultr_les_nouveaux_modeles_disparaissent(self):
        ids = self.ids("claude", "pro", {"DEEPSEEK_API_KEY": "d"})
        for modele in ("glm-5.3", "glm-5.3-flash", "qwen3.8-27b", "qwen3.8-flash-next", "muse-glimmer-30b"):
            self.assertNotIn(modele, ids)

    def test_avec_cle_vultr_ils_apparaissent_sans_bientot(self):
        ids = self.ids("claude", "pro", CLES)
        for modele in ("glm-5.3", "glm-5.3-flash", "qwen3.8-27b", "qwen3.8-flash-next",
                       "nemotron-nano-omni-30b-a3b-reasoning", "muse-glimmer-30b"):
            self.assertIn(modele, ids)
        for fournisseur in ("zai", "alibaba", "nvidia"):
            self.assertNotIn(fournisseur, fournisseurs_llm.DISTRIBUTEURS_BIENTOT)
            self.assertFalse(fournisseurs_llm._config_modeles()["fournisseurs"][fournisseur]["bientot"])

    def test_nvidia_sans_palier_pro_ne_casse_rien(self):
        ids = self.ids("claude", "pro", CLES)
        self.assertEqual(ids.count("nemotron-nano-omni-30b-a3b-reasoning"), 1)
        self.assertEqual(self.ids("nvidia", "pro", CLES), ["nemotron-nano-omni-30b-a3b-reasoning"])

    def test_pas_de_bientot_pour_un_modele_vultr_seul(self):
        with patch.dict("os.environ", CLES, clear=True):
            bientot = [m["modele_id"] for m in fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro")]
        self.assertNotIn("muse-glimmer-30b", bientot)
        self.assertNotIn("glm-5.3", bientot)

    def test_les_trois_partagent_la_meme_cle(self):
        for fournisseur in ("zai", "alibaba", "nvidia"):
            self.assertEqual(fournisseurs_llm.VARIABLES_CLE_PAR_DISTRIBUTEUR[fournisseur], "VULTR_INFERENCE_API_KEY")
            self.assertIn(fournisseur, fournisseurs_llm._STREAMERS_PAR_DISTRIBUTEUR)

    def test_aucun_effort_propose(self):
        for modele in ("glm-5.3", "qwen3.8-27b", "nemotron-nano-omni-30b-a3b-reasoning", "muse-glimmer-30b"):
            self.assertEqual(efforts_modeles.efforts_pour_modele(modele), [])
            self.assertIsNone(efforts_modeles.effort_valide_pour_modele(modele, "high"))

    def test_aucun_identifiant_contributor_chez_meta(self):
        for info in fournisseurs_llm.HIERARCHIE_MODELES["meta"].values():
            self.assertNotIn("contributor", info["id"])


class Outils(Base):
    def test_outils_et_client_vultr(self):
        with patch.dict("os.environ", CLES, clear=True):
            self.assertTrue(clients_outils_llm.modele_a_des_outils("glm-5.3"))
            client = clients_outils_llm.client_avec_outils("glm-5.3")
            # Par le nom : la suite complete peut importer le module sous deux chemins (core. ou non).
            self.assertEqual(type(client).__name__, "ClientVultr")
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "d"}, clear=True):
            self.assertFalse(clients_outils_llm.modele_a_des_outils("glm-5.3"))
            self.assertIsNone(clients_outils_llm.client_avec_outils("glm-5.3"))

    def test_flux_texte_passe_par_vultr(self):
        faux = FauxClientVultr()
        faux.chat = NS(completions=NS(create=lambda **kw: iter([
            NS(choices=[NS(delta=NS(content="Bonjour", reasoning_content=None))])])))
        with patch.dict("os.environ", CLES, clear=True), \
                patch.object(fournisseurs_llm, "creer_client_vultr", return_value=faux):
            morceaux = list(fournisseurs_llm.generer_reponse_premium("qwen3.8-27b", "sys", [{"role": "user", "content": "x"}]))
        self.assertEqual(morceaux, ["Bonjour"])


if __name__ == "__main__":
    unittest.main()
