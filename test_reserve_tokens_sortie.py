"""
Verifie la reserve de tokens de sortie par modele (01/11/2026, demande de Bourama),
sans appel reseau : Muse Spark Open n'est plus plafonne a 4096, Groq ne change pas.
"""

import unittest

from core.reserve_tokens_sortie import (
    RESERVE_TOKENS_DEFAUT,
    RESERVE_TOKENS_PRINCIPAL_GROQ,
    reserve_tokens_sortie,
)

PRINCIPAL_GROQ = "openai/gpt-oss-120b"


class ReserveTokensSortieTest(unittest.TestCase):
    def test_muse_spark_open_depasse_l_ancien_plafond(self):
        self.assertEqual(reserve_tokens_sortie("muse-spark-open", PRINCIPAL_GROQ), 131072)

    def test_principal_groq_inchange(self):
        self.assertEqual(reserve_tokens_sortie(PRINCIPAL_GROQ, PRINCIPAL_GROQ), RESERVE_TOKENS_PRINCIPAL_GROQ)
        self.assertEqual(RESERVE_TOKENS_PRINCIPAL_GROQ, 8192)

    def test_autres_modeles_inchanges(self):
        self.assertEqual(reserve_tokens_sortie("qwen/qwen3.6-27b", PRINCIPAL_GROQ), RESERVE_TOKENS_DEFAUT)
        self.assertEqual(RESERVE_TOKENS_DEFAUT, 4096)


if __name__ == "__main__":
    unittest.main()
