"""
Texte de ligne des outils appeles par l'enveloppe appeler_outil (26/11/2026, demande de Bourama).

Le schema de l'enveloppe demande le texte de ligne a cote de nom et arguments. Le deballage le jetait,
donc les outils obtenus par demander_outils (Notion, GitHub, Supabase...) retombaient sur le texte
fixe. On verifie que le texte survit au deballage, que celui des arguments garde la priorite et
que rien n'est ajoute quand l'IA n'a rien ecrit.
"""

import json
import os
import sys
import unittest

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

from libelles_activite_ia import PARAMETRE_LIBELLE_OUTIL, libelle_ia_de_l_appel  # noqa: E402
from routage_outils import NOM_OUTIL_APPELER_OUTIL, deballer_appels_appeler_outil  # noqa: E402

OUTIL = {
    "type": "function",
    "function": {"name": "notion-search", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
}
TABLE = {"notion-search": object()}


def _appel(contenu):
    return {"id": "call_1", "name": NOM_OUTIL_APPELER_OUTIL, "arguments": json.dumps(contenu)}


def _deballer(contenu):
    appels, refus = deballer_appels_appeler_outil([_appel(contenu)], [], [OUTIL], TABLE)
    assert not refus, refus
    return appels[0]


class TestLibelleAppelerOutil(unittest.TestCase):
    def test_texte_sur_l_enveloppe_survit(self):
        phrase = "Recherche des pages Notion recentes pour retrouver les notes du dernier cours de maths"
        appel = _deballer({"nom": "notion-search", "arguments": {"query": "maths"}, PARAMETRE_LIBELLE_OUTIL: phrase})
        self.assertEqual(appel["name"], "notion-search")
        self.assertEqual(json.loads(appel["arguments"])["query"], "maths")
        self.assertEqual(libelle_ia_de_l_appel(appel), phrase)

    def test_texte_dans_les_arguments_garde_la_priorite(self):
        appel = _deballer({
            "nom": "notion-search",
            "arguments": {PARAMETRE_LIBELLE_OUTIL: "Texte des arguments"},
            PARAMETRE_LIBELLE_OUTIL: "Texte de l'enveloppe",
        })
        self.assertEqual(libelle_ia_de_l_appel(appel), "Texte des arguments")

    def test_sans_texte_rien_n_est_ajoute(self):
        appel = _deballer({"nom": "notion-search", "arguments": {"query": "x"}})
        self.assertNotIn(PARAMETRE_LIBELLE_OUTIL, json.loads(appel["arguments"]))
        self.assertIsNone(libelle_ia_de_l_appel(appel))


if __name__ == "__main__":
    unittest.main()
