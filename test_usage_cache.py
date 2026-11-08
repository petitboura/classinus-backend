"""
Tests de la mesure des tokens et du cache de prompt (07/11/2026, demande Bourama : l'entree
coutait beaucoup trop cher). Aucun appel reseau : tout est simule.
Lancer avec : PYTHONPATH=core:. python3 -m pytest test_usage_cache.py
"""
import os
import types
import unittest
from unittest import mock

from core.usage_llm import normaliser_usage, ligne_usage, ouvrir_flux_avec_usage
from core import adaptateur_claude as claude


class NormaliserUsage(unittest.TestCase):
    def test_anthropic_additionne_le_cache_a_l_entree(self):
        u = types.SimpleNamespace(input_tokens=100, output_tokens=40, cache_read_input_tokens=900, cache_creation_input_tokens=50)
        self.assertEqual(normaliser_usage(u), {"entree": 1050, "cache_lu": 900, "cache_ecrit": 50, "sortie": 40})

    def test_responses_garde_l_entree_telle_quelle(self):
        u = types.SimpleNamespace(input_tokens=1000, output_tokens=20, input_tokens_details=types.SimpleNamespace(cached_tokens=800))
        self.assertEqual(normaliser_usage(u), {"entree": 1000, "cache_lu": 800, "cache_ecrit": 0, "sortie": 20})

    def test_chat_completions_detail_standard(self):
        u = types.SimpleNamespace(prompt_tokens=500, completion_tokens=10, prompt_tokens_details=types.SimpleNamespace(cached_tokens=300))
        self.assertEqual(normaliser_usage(u)["cache_lu"], 300)

    def test_deepseek_direct(self):
        u = {"prompt_tokens": 500, "completion_tokens": 10, "prompt_cache_hit_tokens": 450, "prompt_cache_miss_tokens": 50}
        self.assertEqual(normaliser_usage(u), {"entree": 500, "cache_lu": 450, "cache_ecrit": 0, "sortie": 10})

    def test_gemini(self):
        u = types.SimpleNamespace(prompt_token_count=700, cached_content_token_count=600, candidates_token_count=30, thoughts_token_count=5)
        self.assertEqual(normaliser_usage(u), {"entree": 700, "cache_lu": 600, "cache_ecrit": 0, "sortie": 35})

    def test_usage_absent(self):
        self.assertIsNone(normaliser_usage(None))
        self.assertIn("non rapporté", ligne_usage("m", None))

    def test_ligne_donne_la_part_de_cache(self):
        u = {"prompt_tokens": 1000, "completion_tokens": 5, "prompt_cache_hit_tokens": 250}
        self.assertIn("part_cache=25%", ligne_usage("m", u, messages=3))
        self.assertIn("messages=3", ligne_usage("m", u, messages=3))


class OptionUsageDuFlux(unittest.TestCase):
    def test_demande_l_usage_en_streaming(self):
        appels = []
        ouvrir_flux_avec_usage(lambda **a: appels.append(a) or "flux", {"model": "m", "stream": True})
        self.assertEqual(appels[0]["stream_options"], {"include_usage": True})

    def test_fournisseur_qui_refuse_l_option_est_rouvert_sans(self):
        appels = []

        def creer(**a):
            appels.append(a)
            if "stream_options" in a:
                raise RuntimeError("Unknown parameter: stream_options")
            return "flux"

        self.assertEqual(ouvrir_flux_avec_usage(creer, {"model": "m", "stream": True}), "flux")
        self.assertEqual(len(appels), 2)
        self.assertNotIn("stream_options", appels[1])

    def test_autre_erreur_remonte(self):
        def creer(**a):
            raise RuntimeError("quota depasse")
        with self.assertRaises(RuntimeError):
            ouvrir_flux_avec_usage(creer, {"model": "m", "stream": True})


def _outil(nom):
    return {"type": "function", "function": {"name": nom, "description": "d", "parameters": {"type": "object", "properties": {}}}}


class CacheClaude(unittest.TestCase):
    MESSAGES = [
        {"role": "system", "content": "SYSTEME FIXE"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "r1"},
        {"role": "system", "content": "PARTIE VARIABLE"},
        {"role": "user", "content": "q2"},
    ]

    def _arguments(self, messages=None, outils=None):
        systeme, converti, fin = claude._convertir_messages(messages or self.MESSAGES)
        arguments = {"model": "m", "messages": converti, "system": systeme}
        if outils:
            arguments["tools"] = claude._convertir_outils(outils)
        return claude.poser_points_de_cache(arguments, fin)

    def test_quatre_marqueurs_au_bon_endroit(self):
        a = self._arguments(outils=[_outil("a"), _outil("b")])
        self.assertNotIn("cache_control", a["tools"][0])
        self.assertIn("cache_control", a["tools"][-1])
        self.assertIn("cache_control", a["system"][0])
        # fin de l'historique = la reponse r1, juste avant la partie variable
        self.assertEqual(a["messages"][1]["content"][-1]["text"], "r1")
        self.assertIn("cache_control", a["messages"][1]["content"][-1])
        # dernier message = la question en cours (avec la partie variable devant)
        self.assertIn("cache_control", a["messages"][-1]["content"][-1])
        total = sum("cache_control" in b for m in a["messages"] for b in m["content"]) + 2
        self.assertLessEqual(total, 4)

    def test_la_partie_variable_reste_apres_la_fin_de_l_historique(self):
        a = self._arguments()
        textes = [b["text"] for b in a["messages"][-1]["content"]]
        self.assertTrue(textes[0].endswith("PARTIE VARIABLE"))
        self.assertEqual(textes[-1], "q2")

    def test_sans_partie_variable_pas_de_marqueur_d_historique(self):
        messages = [m for m in self.MESSAGES if m["content"] != "PARTIE VARIABLE"]
        a = self._arguments(messages=messages)
        marques = [i for i, m in enumerate(a["messages"]) if any("cache_control" in b for b in m["content"])]
        self.assertEqual(marques, [len(a["messages"]) - 1])

    def test_le_cache_ne_modifie_pas_l_etat_fournisseur(self):
        bloc = {"type": "tool_use", "id": "t1", "name": "a", "input": {}}
        messages = [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "function": {"name": "a", "arguments": "{}"}}],
             claude.CLE_ETAT_FOURNISSEUR: {"blocs": [bloc]}},
            {"role": "tool", "tool_call_id": "t1", "content": "res"},
        ]
        self._arguments(messages=messages)
        self.assertNotIn("cache_control", bloc)

    def test_interrupteur_coupe_le_cache(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CACHE_PROMPT": "0"}):
            a = self._arguments(outils=[_outil("a")])
        self.assertIsInstance(a["system"], str)
        self.assertNotIn("cache_control", a["tools"][-1])

    def test_duree_une_heure(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CACHE_TTL": "1h"}):
            a = self._arguments()
        self.assertEqual(a["system"][0]["cache_control"], {"type": "ephemeral", "ttl": "1h"})


if __name__ == "__main__":
    unittest.main()


class GarderOutilsSansEnum(unittest.TestCase):
    """garder_outils : definition fixe (cache de prompt), noms controles cote serveur."""

    def setUp(self):
        import os as _os
        _os.environ.setdefault("SUPABASE_URL", "http://localhost")
        _os.environ.setdefault("SUPABASE_SECRET", "test")
        import routage_outils as ro
        self.ro = ro

    def test_la_definition_ne_depend_plus_des_outils_disponibles(self):
        a = self.ro._outil_garder_outils(["x", "y"])
        b = self.ro._outil_garder_outils(["autre"])
        c = self.ro._outil_garder_outils()
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertNotIn("enum", a["function"]["parameters"]["properties"]["outils"]["items"])

    def test_valide_contre_les_outils_reels_du_moment(self):
        outils = [_outil("chercher"), _outil("lire"), self.ro._outil_garder_outils()]
        valides, ignores = self.ro._valider_noms_a_garder(["lire", "inconnu", "garder_outils", "lire"], outils)
        self.assertEqual(valides, ["lire"])
        self.assertEqual(ignores, ["inconnu", "garder_outils"])

    def test_un_outil_ajoute_en_cours_de_tour_peut_etre_garde(self):
        avant = [_outil("chercher")]
        self.assertEqual(self.ro._valider_noms_a_garder(["vercel_deploy"], avant), ([], ["vercel_deploy"]))
        apres = avant + [_outil("vercel_deploy")]
        self.assertEqual(self.ro._valider_noms_a_garder(["vercel_deploy"], apres), (["vercel_deploy"], []))

    def test_entrees_bizarres(self):
        self.assertEqual(self.ro._valider_noms_a_garder(None, None), ([], []))
        self.assertEqual(self.ro._valider_noms_a_garder([3, None, "a"], [_outil("a")]), (["a"], []))
