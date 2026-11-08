"""
Le debut du prompt doit rester identique d'un message a l'autre (07/11/2026, demande Bourama :
l'entree coutait beaucoup trop cher parce que le cache des fournisseurs ne relit que le debut
identique d'une requete). Aucun appel reseau.
Lancer avec : PYTHONPATH=core:. python3 -m pytest test_prompt_cache.py
"""
import os
import unittest
from unittest import mock

# Le constructeur de prompt cree ses clients Supabase a l'import : de fausses valeurs suffisent,
# aucun appel reseau n'est fait (meme principe que test_boucle_adaptateurs.py).
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import construction_system_prompt as csp  # noqa: E402


def construire(message, **kwargs):
    with mock.patch.object(csp, "get_system_prompt", return_value="PAGE DE L'AGENT"):
        return csp._construire_system_prompt(message, "clovis", "user-1", **kwargs)


class SeparationDuPrompt(unittest.TestCase):
    def test_un_seul_marqueur(self):
        self.assertEqual(construire("bonjour").count(csp.MARQUEUR_PARTIE_VARIABLE), 1)

    def test_la_tete_ne_depend_ni_du_message_ni_de_l_heure_ni_des_reglages(self):
        a = construire("bonjour", longueur_reponse="courte", fuseau_horaire="Africa/Tunis")
        with mock.patch.object(csp, "datetime") as faux:
            # une autre minute, un autre reglage de longueur, la recherche forcee, des notions pertinentes
            import datetime as vrai
            faux.now.return_value = vrai.datetime(2026, 11, 8, 3, 17, tzinfo=vrai.timezone.utc)
            b = construire(
                "tout autre message", longueur_reponse="longue", recherche_forcee=True, fuseau_horaire="UTC",
                notions_pertinentes=[{"nom": "Limites", "similarite": 0.9, "statut": "a_venir", "regle": None, "consigne": None}],
                reponses_qcm_recentes=None,
            )
        tete_a, queue_a = csp.separer_partie_variable(a)
        tete_b, queue_b = csp.separer_partie_variable(b)
        self.assertEqual(tete_a, tete_b)
        self.assertNotEqual(queue_a, queue_b)

    def test_tete_contient_la_page_de_l_agent_et_queue_la_date(self):
        tete, queue = csp.separer_partie_variable(construire("bonjour"))
        self.assertIn("PAGE DE L'AGENT", tete)
        self.assertNotIn("Nous sommes le", tete)
        self.assertIn("Nous sommes le", queue)

    def test_rien_n_est_perdu(self):
        complet = construire("bonjour")
        tete, queue = csp.separer_partie_variable(complet)
        self.assertEqual(tete + csp.MARQUEUR_PARTIE_VARIABLE + queue, complet)

    def test_sans_marqueur_tout_reste_en_tete(self):
        self.assertEqual(csp.separer_partie_variable("texte"), ("texte", ""))
        self.assertEqual(csp.separer_partie_variable(None), ("", ""))


if __name__ == "__main__":
    unittest.main()
