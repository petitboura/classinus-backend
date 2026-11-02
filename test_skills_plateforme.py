"""Tests des skills officiels de Classinus : catalogue fusionné, lecture seule, préférence, prompt.

Règles décidées par Bourama le 02/11/2026 : le skill de l'utilisateur gagne toujours ; l'IA peut
signaler le skill officiel et proposer de comparer ; si l'utilisateur demande de ne plus le faire,
c'est mémorisé et respecté.
"""
import logging
import os
import unittest
from unittest import mock

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)

# Fausses base et R2 déjà écrites pour test_skills_api.py : on les réutilise telles quelles.
from test_skills_api import r2, base, _stock  # noqa: E402
from api import skills as S  # noqa: E402
from core import skills_actions as A, skills_catalogue as C, config_skills  # noqa: E402

U1, U2 = "user-1", "user-2"
OFFICIEL_WORD = "off-word"
OFFICIEL_INACTIF = "off-inactif"


def poser_officiel(skill_id=OFFICIEL_WORD, slug="word", nom="Documents Word", description="Quand créer un Word", actif=True, texte="Consignes officielles Word"):
    base.tables.setdefault("skills", []).append({
        "id": skill_id, "owner_id": None, "portee": "plateforme", "slug": slug,
        "nom": nom, "description": description, "actif": actif, "updated_at": "2026-11-02",
    })
    cle = f"plateforme/{skill_id}/v1/SKILL.md"
    r2.objets[cle] = texte.encode("utf-8")
    base.tables.setdefault("skill_files", []).append({
        "skill_id": skill_id, "chemin": "SKILL.md", "cle_stockage": cle,
        "type_mime": "text/markdown", "taille_octets": len(texte),
    })


class Base(unittest.TestCase):
    def setUp(self):
        for faux in (
            mock.patch.object(S, "supabase", base),
            mock.patch.object(S, "stockage_r2", _stock),
            mock.patch.object(C, "supabase", base),
        ):
            faux.start()
            self.addCleanup(faux.stop)
        r2.objets.clear(); r2.echec_upload_sur = None
        base.tables.clear(); base.echec_sur = None
        C.vider_cache_officiels()
        self.addCleanup(C.vider_cache_officiels)


class TestCatalogueOfficiels(Base):
    def test_liste_seulement_les_officiels_actifs(self):
        poser_officiel()
        poser_officiel(OFFICIEL_INACTIF, slug="vieux", actif=False)
        base.tables["skills"].append({"id": "perso", "owner_id": U1, "portee": "compte", "nom": "Perso", "actif": True})
        self.assertEqual([s["id"] for s in C.lister_skills_officiels()], [OFFICIEL_WORD])

    def test_description_trop_longue_est_abregee(self):
        poser_officiel(description="x" * (config_skills.CATALOGUE_DESCRIPTION_MAX + 50))
        d = C.lister_skills_officiels()[0]["description"]
        self.assertEqual(len(d), config_skills.CATALOGUE_DESCRIPTION_MAX)
        self.assertTrue(d.endswith("…"))

    def test_la_liste_est_gardee_en_memoire_puis_rafraichie(self):
        poser_officiel()
        self.assertEqual(len(C.lister_skills_officiels()), 1)
        poser_officiel("off-excel", slug="excel", nom="Excel")
        self.assertEqual(len(C.lister_skills_officiels()), 1, "pas de nouvelle lecture pendant le délai")
        C.vider_cache_officiels()
        self.assertEqual(len(C.lister_skills_officiels()), 2)

    def test_une_erreur_rend_la_derniere_liste_connue_et_n_est_pas_gardee(self):
        poser_officiel()
        self.assertEqual(len(C.lister_skills_officiels()), 1)
        with mock.patch.object(config_skills, "PLATEFORME_CACHE_SECONDES", 0):
            C.vider_cache_officiels()
            self.assertEqual(len(C.lister_skills_officiels()), 1)  # remplit avec expiration immédiate
            base.echec_sur = ("skills", "select")
            self.assertEqual(len(C.lister_skills_officiels()), 1, "dernière liste connue")
        base.echec_sur = None
        C.vider_cache_officiels()
        base.echec_sur = ("skills", "select")
        self.assertEqual(C.lister_skills_officiels(), [], "rien de connu : liste vide, jamais d'exception")

    def test_catalogue_complet_sans_utilisateur_est_vide(self):
        poser_officiel()
        self.assertEqual(C.lister_catalogue_complet(None), {"skills": [], "total": 0, "officiels": [], "ne_plus_proposer": False})

    def test_catalogue_complet_fusionne_les_deux_sources_sans_les_melanger(self):
        poser_officiel()
        base.tables["skills"].append({"id": "perso", "owner_id": U1, "portee": "compte", "nom": "Mon Word", "description": "d", "actif": True})
        res = C.lister_catalogue_complet(U1)
        self.assertEqual([s["id"] for s in res["skills"]], ["perso"])
        self.assertEqual([s["id"] for s in res["officiels"]], [OFFICIEL_WORD])
        self.assertFalse(res["ne_plus_proposer"])

    def test_un_skill_officiel_n_apparait_pas_dans_les_skills_d_un_autre_compte(self):
        poser_officiel()
        self.assertEqual(C.lister_catalogue_complet(U2)["skills"], [])


class TestLectureSeule(Base):
    def test_un_utilisateur_consulte_un_skill_officiel(self):
        poser_officiel()
        texte = A.executer(U1, "consulter", skill_id=OFFICIEL_WORD)
        self.assertIn("skill officiel de Classinus, lecture seule", texte)
        self.assertIn("Consignes officielles Word", texte)

    def test_un_skill_officiel_desactive_n_est_pas_consultable(self):
        poser_officiel(OFFICIEL_INACTIF, slug="vieux", actif=False)
        self.assertTrue(A.executer(U1, "consulter", skill_id=OFFICIEL_INACTIF).startswith("Erreur"))

    def test_consulter_le_skill_prive_d_un_autre_compte_reste_refuse(self):
        A.executer(U1, "creer", nom="Secret", description="d", contenu="contenu prive")
        sid = base.tables["skills"][-1]["id"]
        self.assertTrue(A.executer(U2, "consulter", skill_id=sid).startswith("Erreur"))

    def test_toutes_les_ecritures_sont_refusees_avec_un_message_clair(self):
        poser_officiel()
        essais = [
            ("modifier_infos", dict(nom="Autre")),
            ("ecrire_fichier", dict(chemin="a.md", contenu="x")),
            ("remplacer_texte", dict(chemin="SKILL.md", ancien="Consignes", nouveau="Changé")),
            ("supprimer_fichier", dict(chemin="references/a.md")),
            ("supprimer", dict()),
        ]
        for action, params in essais:
            with self.subTest(action=action):
                texte = A.executer(U1, action, skill_id=OFFICIEL_WORD, **params)
                self.assertTrue(texte.startswith("Erreur : ce skill est un skill officiel de Classinus"), texte)
                self.assertIn("lecture seule", texte)
        ligne = next(l for l in base.tables["skills"] if l["id"] == OFFICIEL_WORD)
        self.assertEqual(ligne["nom"], "Documents Word")
        self.assertEqual(r2.objets[f"plateforme/{OFFICIEL_WORD}/v1/SKILL.md"], b"Consignes officielles Word")

    def test_exporter_un_skill_officiel_donne_un_refus_clair_et_non_un_faux_message_de_vide(self):
        poser_officiel()
        texte = A.executer(U1, "exporter_zip", skill_id=OFFICIEL_WORD)
        self.assertTrue(texte.startswith("Erreur : ce skill est un skill officiel de Classinus"), texte)
        self.assertNotIn("aucun skill à exporter", texte)

    def test_ecrire_sur_un_skill_personnel_marche_toujours(self):
        A.executer(U1, "creer", nom="Perso", description="d", contenu="c")
        sid = base.tables["skills"][-1]["id"]
        self.assertIn("créé", A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="a.md", contenu="x"))

    def test_lister_montre_les_deux_familles(self):
        poser_officiel()
        A.executer(U1, "creer", nom="Mon Word", description="d", contenu="c")
        texte = A.executer(U1, "lister")
        self.assertIn("SKILLS DE L'UTILISATEUR", texte)
        self.assertIn("Mon Word", texte)
        self.assertIn("SKILLS OFFICIELS DE CLASSINUS", texte)
        self.assertIn("Documents Word", texte)

    def test_lister_sans_aucun_skill_garde_l_ancien_message(self):
        self.assertEqual(A.executer(U1, "lister"), "Aucun skill pour l'instant.")


class TestPreference(Base):
    def test_ne_plus_proposer_est_memorise_puis_repris(self):
        self.assertFalse(C.ne_plus_proposer_officiels(U1))
        self.assertIn("mémorisé", A.executer(U1, "ne_plus_proposer_officiels"))
        self.assertTrue(C.ne_plus_proposer_officiels(U1))
        self.assertTrue(C.lister_catalogue_complet(U1)["ne_plus_proposer"])
        self.assertIn("mémorisé", A.executer(U1, "reprendre_propositions_officielles"))
        self.assertFalse(C.ne_plus_proposer_officiels(U1))
        self.assertEqual(len(base.tables["preferences_skills_officiels"]), 1, "une seule ligne par utilisateur")

    def test_la_preference_d_un_compte_ne_touche_pas_les_autres(self):
        A.executer(U1, "ne_plus_proposer_officiels")
        self.assertFalse(C.ne_plus_proposer_officiels(U2))

    def test_une_erreur_de_lecture_de_la_preference_ne_bloque_pas_le_chat(self):
        base.echec_sur = ("preferences_skills_officiels", "select")
        self.assertFalse(C.ne_plus_proposer_officiels(U1))


class TestPrompt(unittest.TestCase):
    """Le prompt annonce les officiels à part, avec la règle de priorité et la préférence."""

    def _prompt(self, catalogue):
        import construction_system_prompt as csp
        with mock.patch.object(csp, "get_system_prompt", return_value="PROMPT_BASE"), mock.patch.object(
            csp, "obtenir_etat_editeur", return_value=None
        ):
            return csp._construire_system_prompt("bonjour", "agent-test", user_id="u1", skills_catalogue=catalogue)

    def _catalogue(self, **extra):
        return {
            "skills": [{"id": "perso-1", "nom": "Mon Word", "description": "mon style"}], "total": 1,
            "officiels": [{"id": "off-1", "nom": "Documents Word", "description": "méthode officielle"}],
            "ne_plus_proposer": False, **extra,
        }

    def test_les_deux_blocs_sont_distincts(self):
        p = self._prompt(self._catalogue())
        self.assertIn("SKILLS OFFICIELS DE CLASSINUS", p)
        self.assertIn("SKILLS DE L'UTILISATEUR", p)
        self.assertLess(p.index("SKILLS OFFICIELS DE CLASSINUS"), p.index("SKILLS DE L'UTILISATEUR"))
        self.assertIn("id=off-1", p)
        self.assertIn("id=perso-1", p)

    def test_la_regle_dit_que_celui_de_l_utilisateur_gagne_et_que_l_on_tranche_ensemble(self):
        p = self._prompt(self._catalogue())
        self.assertIn("utilise TOUJOURS le sien", p)
        self.assertIn("une seule fois", p)
        self.assertIn("vous tranchez ensemble", p)
        self.assertIn("sans son accord", p)
        self.assertIn("ne_plus_proposer_officiels", p)

    def test_preference_active_interdit_de_les_mentionner(self):
        p = self._prompt(self._catalogue(ne_plus_proposer=True))
        self.assertIn("ne les mentionne pas", p)
        self.assertIn("reprendre_propositions_officielles", p)
        self.assertNotIn("vous tranchez ensemble", p)

    def test_sans_skill_perso_les_officiels_sont_quand_meme_annonces(self):
        p = self._prompt({"skills": [], "total": 0, "officiels": [{"id": "off-1", "nom": "Excel", "description": "d"}], "ne_plus_proposer": False})
        self.assertIn("SKILLS OFFICIELS DE CLASSINUS", p)
        self.assertNotIn("SKILLS DE L'UTILISATEUR", p)

    def test_aucun_officiel_ne_change_rien_au_prompt_existant(self):
        p = self._prompt({"skills": [{"id": "perso-1", "nom": "Mon Word", "description": "d"}], "total": 1})
        self.assertNotIn("SKILLS OFFICIELS DE CLASSINUS", p)
        self.assertIn("SKILLS DE L'UTILISATEUR", p)

    def test_catalogue_absent_ne_plante_pas(self):
        self.assertNotIn("SKILLS OFFICIELS", self._prompt(None))


if __name__ == "__main__":
    unittest.main()
