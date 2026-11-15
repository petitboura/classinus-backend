"""
Les outils forces par le contexte ne sont plus dans la liste d'outils envoyee au modele (16/11/2026,
demande Bourama : cette liste part en tete de requete, la changer d'un message a l'autre fait tout
relire au prix plein). Ils arrivent comme un outil trouve par demander_outils : fiche a la fin du
prompt, appel par appeler_outil. Aucun appel reseau.
Lancer avec : PYTHONPATH=core:. python3 -m pytest test_outils_forces_differes.py
"""
import os
import unittest

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import routage_outils as ro  # noqa: E402


def outil(nom, description="Fait quelque chose.", parametres=None):
    return {"type": "function", "function": {
        "name": nom, "description": description,
        "parameters": parametres or {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    }}


def noms(liste):
    return [o["function"]["name"] for o in liste]


class DifferrerOutilsForces(unittest.TestCase):
    def test_les_outils_forces_sortent_de_la_liste_et_ont_une_fiche(self):
        liste = [outil("web_search"), outil("rappeler_resultat_outil", "Relit un resultat.")]
        restants, texte = ro.differer_outils_forces(liste, ["rappeler_resultat_outil"])
        self.assertEqual(noms(restants), ["web_search"])
        self.assertIn("rappeler_resultat_outil : Relit un resultat.", texte)
        self.assertIn("appeler_outil(nom, arguments)", texte)
        self.assertIn('"required":["x"]', texte)  # le schema reel est dans la fiche

    def test_la_liste_ne_depend_plus_des_outils_forces(self):
        # le point du correctif : avec ou sans outil force, la liste envoyee est la meme
        base = [outil("web_search")]
        sans_force, _ = ro.differer_outils_forces(list(base), [])
        avec_force, _ = ro.differer_outils_forces(
            base + [outil("verifier_consignes_code_actif"), outil("changer_mode_conversation")],
            ["verifier_consignes_code_actif", "changer_mode_conversation"],
        )
        self.assertEqual(noms(sans_force), noms(avec_force))

    def test_un_outil_choisi_par_l_utilisateur_reste_dans_la_liste(self):
        liste = [outil("generer_code"), outil("lire_media_conversation")]
        restants, texte = ro.differer_outils_forces(
            liste, ["generer_code", "lire_media_conversation"], ["generer_code"],
        )
        self.assertEqual(noms(restants), ["generer_code"])
        self.assertIn("lire_media_conversation", texte)
        self.assertNotIn("generer_code", texte)

    def test_un_outil_force_non_autorise_est_ignore(self):
        liste = [outil("web_search")]
        restants, texte = ro.differer_outils_forces(liste, ["outil_absent"])
        self.assertEqual(noms(restants), ["web_search"])
        self.assertEqual(texte, "")

    def test_rien_a_differer(self):
        self.assertEqual(ro.differer_outils_forces([], ["a"]), ([], ""))
        self.assertEqual(ro.differer_outils_forces(None, None), (None, ""))

    def test_la_fiche_porte_le_libelle_comme_demander_outils(self):
        _, texte = ro.differer_outils_forces([outil("gerer_skill")], ["gerer_skill"])
        self.assertIn("libelle", texte.lower())

    def test_la_liste_d_origine_n_est_pas_modifiee(self):
        liste = [outil("a"), outil("b")]
        ro.differer_outils_forces(liste, ["a"])
        self.assertEqual(noms(liste), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
