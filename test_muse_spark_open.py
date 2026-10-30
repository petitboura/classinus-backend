"""
Vérifie Muse Spark Open (30/10/2026, demande de Bourama), sans appel réseau.

Modèle de Meta à poids ouverts, placé au niveau essentiel de Meta (donc affiché après
Muse Spark 1.3). Il est servi UNIQUEMENT par Baseten : ouvert à tout le monde malgré le
Bientôt de Meta, dépend seulement de la clé BASETEN_API_KEY, aucun repli direct.
"""

import types
import unittest
from unittest.mock import patch

from core import adaptateur_baseten
from core import clients_outils_llm
from core import efforts_modeles
from core import fournisseurs_llm
from core.adaptateur_baseten import BASE_URL_BASETEN, ClientBaseten

NS = types.SimpleNamespace

OPEN_ID = "muse-spark-open"
OPEN_SLUG = "meta-models/muse-spark-open-1026"
CLES_AUTRES = {"DEEPSEEK_API_KEY": "d"}  # aucune clé Meta : seul Baseten peut servir Open


class ErreurStatut(Exception):
    def __init__(self, statut, message):
        super().__init__(message)
        self.status_code = statut


class FauxCompletions:
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


def morceau(contenu=None, reflexion=None):
    delta = NS(content=contenu, reasoning_content=reflexion)
    return NS(choices=[NS(delta=delta)])


class BaseTest(unittest.TestCase):
    def setUp(self):
        FauxClientOpenAI.instances = []
        adaptateur_baseten.reinitialiser_circuit_baseten()
        fournisseurs_llm.reinitialiser_cache_config_modeles()
        self.addCleanup(adaptateur_baseten.reinitialiser_circuit_baseten)
        self.addCleanup(fournisseurs_llm.reinitialiser_cache_config_modeles)

    def env(self, variables):
        parche = patch.dict("os.environ", variables, clear=True)
        parche.start()
        self.addCleanup(parche.stop)
        parche_openai = patch.object(adaptateur_baseten, "OpenAI", FauxClientOpenAI)
        parche_openai.start()
        self.addCleanup(parche_openai.stop)


class DansLaListe(BaseTest):
    def test_open_disponible_a_tous_malgre_le_bientot_de_meta(self):
        self.env({**CLES_AUTRES, "BASETEN_API_KEY": "b"})
        for distributeur, palier in (("claude", "pro"), ("deepseek", "essentiel"), ("grok", "avance")):
            disponibles = fournisseurs_llm.modeles_disponibles_pour_agent(distributeur, palier)
            ids_meta = [m["modele_id"] for m in disponibles if m["distributeur"] == "meta"]
            self.assertEqual(ids_meta, [OPEN_ID], (distributeur, palier))

    def test_spark_et_wonder_restent_bientot_et_open_n_y_est_pas(self):
        self.env({**CLES_AUTRES, "BASETEN_API_KEY": "b"})
        bientot = fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro")
        ids_meta = [m["modele_id"] for m in bientot if m["distributeur"] == "meta"]
        self.assertEqual(ids_meta, ["muse-wonder-1.0", "muse-spark-1.3"])

    def test_open_est_choix_valide_cote_serveur(self):
        self.env({**CLES_AUTRES, "BASETEN_API_KEY": "b"})
        self.assertTrue(fournisseurs_llm.modele_id_est_autorise(OPEN_ID, "claude", "pro"))
        self.assertFalse(fournisseurs_llm.modele_id_est_autorise("muse-spark-1.3", "claude", "pro"))

    def test_sans_cle_baseten_open_n_apparait_nulle_part(self):
        self.env(CLES_AUTRES)
        disponibles = fournisseurs_llm.modeles_disponibles_pour_agent("claude", "pro")
        bientot = fournisseurs_llm.modeles_bientot_pour_agent("claude", "pro")
        self.assertNotIn(OPEN_ID, [m["modele_id"] for m in disponibles + bientot])
        self.assertFalse(fournisseurs_llm.modele_id_est_autorise(OPEN_ID, "claude", "pro"))

    def test_agent_sans_selecteur_ne_voit_rien(self):
        self.env({**CLES_AUTRES, "BASETEN_API_KEY": "b"})
        self.assertEqual(fournisseurs_llm.modeles_disponibles_pour_agent("aucun", "pro"), [])

    def test_aucun_reglage_d_effort_pour_open(self):
        self.assertEqual(efforts_modeles.efforts_pour_modele(OPEN_ID, "meta"), [])
        # C'est ce que la boucle d'agent appelle (_effort_reflexion) : rien n'est envoyé à Baseten.
        self.assertTrue(efforts_modeles.est_modele_avec_adaptateur(OPEN_ID))
        self.assertIsNone(efforts_modeles.effort_valide_pour_modele(OPEN_ID, "high"))
        # Muse Spark 1.3 garde ses réglages.
        self.assertIn("high", efforts_modeles.efforts_pour_modele("muse-spark-1.3", "meta"))


class RouteBaseten(BaseTest):
    def test_outils_avec_la_seule_cle_baseten(self):
        self.env({"BASETEN_API_KEY": "b"})
        self.assertTrue(clients_outils_llm.modele_a_des_outils(OPEN_ID))
        client = clients_outils_llm.client_avec_outils(OPEN_ID)
        self.assertIsInstance(client, ClientBaseten)

    def test_sans_cle_baseten_pas_de_client_ni_d_outils(self):
        self.env({"MODEL_API_KEY": "m"})  # la clé Meta ne sert pas à Open
        self.assertFalse(clients_outils_llm.modele_a_des_outils(OPEN_ID))
        self.assertIsNone(clients_outils_llm.client_avec_outils(OPEN_ID))

    def test_baseten_recoit_le_slug_1026_et_jamais_le_direct(self):
        self.env({"BASETEN_API_KEY": "b"})
        client = clients_outils_llm.client_avec_outils(OPEN_ID)
        client.chat.completions.create(model=OPEN_ID, messages=[])
        instances = [c for c in FauxClientOpenAI.instances if c.base_url == BASE_URL_BASETEN]
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].api_key, "b")
        self.assertEqual(instances[0].chat.completions.appels[0]["model"], OPEN_SLUG)
        self.assertEqual(len(FauxClientOpenAI.instances), 1)  # aucun client direct

    def test_refus_de_baseten_remonte_sans_repli(self):
        self.env({"BASETEN_API_KEY": "b"})
        client = clients_outils_llm.client_avec_outils(OPEN_ID)
        baseten = next(c for c in FauxClientOpenAI.instances if c.base_url == BASE_URL_BASETEN)

        def refus(**kw):
            raise ErreurStatut(402, "credit epuise")

        baseten.chat.completions.effet = refus
        with self.assertRaises(ErreurStatut):
            client.chat.completions.create(model=OPEN_ID, messages=[])
        self.assertFalse(adaptateur_baseten.baseten_circuit_ouvert())

    def test_modele_meta_normal_ne_passe_pas_par_baseten(self):
        self.env({"MODEL_API_KEY": "m", "BASETEN_API_KEY": "b"})
        self.assertIsNone(fournisseurs_llm.info_baseten_seul("muse-spark-1.3"))
        self.assertIsNone(fournisseurs_llm.info_baseten_seul("deepseek-v4-flash"))

    def test_flux_texte_seul_passe_par_baseten(self):
        self.env({"BASETEN_API_KEY": "b"})

        def flux(**kw):
            return iter([morceau(reflexion="je reflechis"), morceau("Bon"), morceau("jour"), NS(choices=[])])

        faux = FauxClientOpenAI
        original_init = faux.__init__

        def init_avec_flux(self, api_key=None, base_url=None):
            original_init(self, api_key=api_key, base_url=base_url)
            self.chat.completions.effet = flux

        with patch.object(faux, "__init__", init_avec_flux):
            morceaux = list(fournisseurs_llm.generer_reponse_premium(OPEN_ID, "Sois bref", [{"role": "user", "content": "salut"}]))
        self.assertEqual(morceaux, [{"type": "raisonnement", "texte": "je reflechis"}, "Bon", "jour"])
        baseten = next(c for c in FauxClientOpenAI.instances if c.base_url == BASE_URL_BASETEN)
        appel = baseten.chat.completions.appels[0]
        self.assertEqual(appel["model"], OPEN_SLUG)
        self.assertTrue(appel["stream"])
        self.assertEqual(appel["messages"][0], {"role": "system", "content": "Sois bref"})
        self.assertNotIn("reasoning_effort", appel)


class FauxSupabase:
    """Lecture de configuration simulée ; la colonne baseten_seul peut être absente."""

    def __init__(self, colonne_baseten_seul_presente):
        self.presente = colonne_baseten_seul_presente
        self.colonnes = None
        self.table_courante = None

    def table(self, nom):
        self.table_courante = nom
        return self

    def select(self, colonnes):
        self.colonnes = colonnes
        return self

    def order(self, *_):
        return self

    @property
    def data(self):
        return self._donnees

    def execute(self):
        nom, colonnes = self.table_courante, self.colonnes
        if "baseten_seul" in colonnes and not self.presente:
            raise RuntimeError("column modeles_llm.baseten_seul does not exist")
        if nom == "fournisseurs_llm":
            lignes = [
                {"distributeur": "deepseek", "ordre": 4, "bientot": False, "cle_api_requise": True, "variable_cle_api": "DEEPSEEK_API_KEY", "nom_affiche": "DeepSeek", "baseten_actif": True},
                {"distributeur": "meta", "ordre": 6, "bientot": True, "cle_api_requise": True, "variable_cle_api": "MODEL_API_KEY", "nom_affiche": "Meta", "baseten_actif": False},
            ]
        elif nom == "modeles_llm":
            lignes = [
                {"distributeur": "deepseek", "palier": "essentiel", "niveau": 1, "modele_id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash", "actif": True, "modele_id_baseten": "deepseek-ai/DeepSeek-V4-Flash-0731"},
                {"distributeur": "meta", "palier": "avance", "niveau": 2, "modele_id": "muse-spark-1.3", "label": "Muse Spark 1.3", "actif": True, "modele_id_baseten": None},
                {"distributeur": "meta", "palier": "essentiel", "niveau": 1, "modele_id": OPEN_ID, "label": "Muse Spark Open", "actif": True, "modele_id_baseten": OPEN_SLUG, "baseten_seul": True},
            ]
        elif nom == "textes_modeles_llm":
            lignes = [{"cle": "bientot", "langue": "fr", "texte": "Bientôt"}]
        else:
            lignes = []
        self._donnees = lignes
        return self


class LectureSupabase(BaseTest):
    def lire(self, colonne_presente):
        faux = FauxSupabase(colonne_presente)
        with patch.dict("os.environ", {"SUPABASE_URL": "u", "SUPABASE_SECRET": "s"}, clear=True), \
                patch.object(fournisseurs_llm, "_client_supabase_config_modeles", return_value=faux):
            return fournisseurs_llm._lire_config_modeles_supabase()

    def test_colonne_presente_open_est_baseten_seul(self):
        config = self.lire(True)
        open_ = config["modeles"]["meta"]["essentiel"]
        self.assertTrue(open_["baseten_seul"])
        self.assertEqual(open_["baseten"], OPEN_SLUG)
        self.assertNotIn("baseten_seul", config["modeles"]["meta"]["avance"])

    def test_colonne_absente_deepseek_garde_ses_slugs_et_open_n_est_pas_ouvert(self):
        config = self.lire(False)
        self.assertEqual(config["modeles"]["deepseek"]["essentiel"]["baseten"], "deepseek-ai/DeepSeek-V4-Flash-0731")
        self.assertNotIn("baseten_seul", config["modeles"]["meta"]["essentiel"])


if __name__ == "__main__":
    unittest.main()
