"""
Verifie la reserve de tokens de sortie par modele (01/11/2026, demande de Bourama),
sans appel reseau : Muse Spark Open n'est plus plafonne a 4096, Groq ne change pas.

02/11/2026 : les modeles hors Groq (DeepSeek, modele principal de la cascade) ne sont plus
plafonnes a 4096 non plus, ils recoivent la reserve large reglable par variable d'environnement.
"""

import importlib
import os
import unittest
from unittest.mock import patch

from core.reserve_tokens_sortie import (
    RESERVE_TOKENS_DEFAUT,
    RESERVE_TOKENS_PRINCIPAL_GROQ,
    reserve_tokens_sortie,
)
from core.plafonds_reglables import RESERVE_TOKENS_SORTIE_HORS_GROQ

PRINCIPAL_GROQ = "openai/gpt-oss-120b"
SECOURS_GROQ = ["qwen/qwen3.6-27b", "openai/gpt-oss-20b"]


class ReserveTokensSortieTest(unittest.TestCase):
    def test_muse_spark_open_depasse_l_ancien_plafond(self):
        self.assertEqual(reserve_tokens_sortie("muse-spark-open", PRINCIPAL_GROQ, SECOURS_GROQ), 131072)
        self.assertEqual(reserve_tokens_sortie("muse-spark-open", PRINCIPAL_GROQ), 131072)

    def test_principal_groq_inchange(self):
        self.assertEqual(reserve_tokens_sortie(PRINCIPAL_GROQ, PRINCIPAL_GROQ, SECOURS_GROQ), RESERVE_TOKENS_PRINCIPAL_GROQ)
        self.assertEqual(RESERVE_TOKENS_PRINCIPAL_GROQ, 8192)

    def test_secours_groq_inchanges(self):
        for modele in SECOURS_GROQ:
            with self.subTest(modele=modele):
                self.assertEqual(reserve_tokens_sortie(modele, PRINCIPAL_GROQ, SECOURS_GROQ), RESERVE_TOKENS_DEFAUT)
        self.assertEqual(RESERVE_TOKENS_DEFAUT, 4096)

    def test_deepseek_n_est_plus_plafonne_a_la_reserve_de_groq(self):
        for modele in ("deepseek-v4-flash", "deepseek-v4-pro"):
            with self.subTest(modele=modele):
                reserve = reserve_tokens_sortie(modele, PRINCIPAL_GROQ, SECOURS_GROQ)
                self.assertEqual(reserve, RESERVE_TOKENS_SORTIE_HORS_GROQ)
                self.assertGreater(reserve, RESERVE_TOKENS_PRINCIPAL_GROQ)

    def test_valeur_large_assez_pour_un_gros_fichier_et_sous_le_maximum_deepseek(self):
        self.assertGreaterEqual(RESERVE_TOKENS_SORTIE_HORS_GROQ, 16384)
        # Maximum de sortie documente par DeepSeek (api-docs.deepseek.com) : 384K.
        self.assertLess(RESERVE_TOKENS_SORTIE_HORS_GROQ, 384000)

    def test_sans_la_liste_des_modeles_groq_on_reste_prudent(self):
        # Un appelant qui ne fournit pas la liste ne peut pas distinguer un modele Groq d'un autre :
        # jamais la reserve large, qui ferait refuser l'appel par Groq.
        self.assertEqual(reserve_tokens_sortie("deepseek-v4-flash", PRINCIPAL_GROQ), RESERVE_TOKENS_DEFAUT)
        self.assertEqual(reserve_tokens_sortie("qwen/qwen3.6-27b", PRINCIPAL_GROQ), RESERVE_TOKENS_DEFAUT)

    def test_nom_vide_reste_prudent(self):
        self.assertEqual(reserve_tokens_sortie(None, PRINCIPAL_GROQ, SECOURS_GROQ), RESERVE_TOKENS_DEFAUT)
        self.assertEqual(reserve_tokens_sortie("", PRINCIPAL_GROQ, SECOURS_GROQ), RESERVE_TOKENS_DEFAUT)


class ReglageParVariableTest(unittest.TestCase):
    """La valeur se change sans toucher au code, une valeur invalide retombe sur le defaut."""

    def _valeur_avec(self, valeur):
        import core.plafonds_reglables as plafonds
        env = {} if valeur is None else {"CLASSINUS_RESERVE_TOKENS_SORTIE_HORS_GROQ": valeur}
        with patch.dict(os.environ, env, clear=False):
            if valeur is None:
                os.environ.pop("CLASSINUS_RESERVE_TOKENS_SORTIE_HORS_GROQ", None)
            recharge = importlib.reload(plafonds)
            resultat = recharge.RESERVE_TOKENS_SORTIE_HORS_GROQ
        importlib.reload(plafonds)
        return resultat

    def test_defaut(self):
        self.assertEqual(self._valeur_avec(None), 32768)

    def test_valeur_personnalisee(self):
        self.assertEqual(self._valeur_avec("65536"), 65536)

    def test_valeurs_invalides_retombent_sur_le_defaut(self):
        for brut in ("", "abc", "0", "-5"):
            with self.subTest(brut=brut):
                self.assertEqual(self._valeur_avec(brut), 32768)


if __name__ == "__main__":
    unittest.main()
