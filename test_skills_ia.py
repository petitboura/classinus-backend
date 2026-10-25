"""Tests du branchement de l'IA aux skills : actions de l'outil gerer_skill et catalogue du prompt."""
import logging
import os
import unittest
from types import SimpleNamespace
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


def creer(nom="Mon skill", description="Quand corriger", contenu="Corps du skill", user=U1):
    texte = A.executer(user, "creer", nom=nom, description=description, contenu=contenu)
    assert texte.startswith("Skill créé"), texte
    return base.tables["skills"][-1]["id"]


class TestActionsSkills(unittest.TestCase):
    def setUp(self):
        for faux in (mock.patch.object(S, "supabase", base), mock.patch.object(S, "stockage_r2", _stock)):
            faux.start()
            self.addCleanup(faux.stop)
        r2.objets.clear(); r2.echec_upload_sur = None
        base.tables.clear(); base.echec_sur = None

    def test_creer_puis_consulter_le_skill_md_avec_son_en_tete(self):
        sid = creer()
        texte = A.executer(U1, "consulter", skill_id=sid)
        self.assertIn('name: "Mon skill"', texte)
        self.assertIn("Corps du skill", texte)

    def test_consulter_liste_les_autres_fichiers(self):
        sid = creer()
        A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="references/guide.md", contenu="Guide")
        texte = A.executer(U1, "consulter", skill_id=sid)
        self.assertIn("references/guide.md", texte)
        self.assertEqual(A.executer(U1, "consulter", skill_id=sid, chemin="references/guide.md").split("\n\n", 1)[1], "Guide")

    def test_consulter_fichier_inexistant_donne_la_liste(self):
        sid = creer()
        texte = A.executer(U1, "consulter", skill_id=sid, chemin="nope.md")
        self.assertTrue(texte.startswith("Erreur"))
        self.assertIn("SKILL.md", texte)

    def test_ecrire_fichier_cree_puis_remplace(self):
        sid = creer()
        self.assertIn("créé", A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="scripts/a.py", contenu="1"))
        self.assertIn("remplacé", A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="scripts/a.py", contenu="2"))
        self.assertTrue(A.executer(U1, "consulter", skill_id=sid, chemin="scripts/a.py").endswith("2"))
        self.assertEqual(len(r2.objets), 2, "pas d'ancienne version laissée dans R2")

    def test_chemin_invalide_refuse(self):
        sid = creer()
        self.assertTrue(A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="../x.md", contenu="1").startswith("Erreur"))
        self.assertTrue(A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="", contenu="1").startswith("Erreur"))

    def test_remplacer_texte(self):
        sid = creer(contenu="un deux trois")
        self.assertIn("remplacé", A.executer(U1, "remplacer_texte", skill_id=sid, chemin="SKILL.md", ancien="deux", nouveau="2"))
        self.assertIn("un 2 trois", A.executer(U1, "consulter", skill_id=sid))

    def test_remplacer_texte_introuvable_ou_multiple(self):
        sid = creer(contenu="zzz zzz")
        self.assertIn("2 fois", A.executer(U1, "remplacer_texte", skill_id=sid, chemin="SKILL.md", ancien="zzz", nouveau="b"))
        self.assertIn("introuvable", A.executer(U1, "remplacer_texte", skill_id=sid, chemin="SKILL.md", ancien="absent du fichier", nouveau="b"))
        self.assertIn("zzz zzz", A.executer(U1, "consulter", skill_id=sid), "rien n'a changé")

    def test_supprimer_fichier_et_refus_du_skill_md(self):
        sid = creer()
        A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="x.md", contenu="1")
        self.assertIn("supprimé", A.executer(U1, "supprimer_fichier", skill_id=sid, chemin="x.md"))
        self.assertNotIn("x.md", A.executer(U1, "consulter", skill_id=sid))
        self.assertTrue(A.executer(U1, "supprimer_fichier", skill_id=sid, chemin="SKILL.md").startswith("Erreur"))

    def test_modifier_infos_garde_les_fichiers_et_met_a_jour_l_en_tete(self):
        sid = creer()
        A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="references/g.md", contenu="G")
        A.executer(U1, "modifier_infos", skill_id=sid, nom="Nouveau nom", description="Nouvelle desc", actif="non")
        texte = A.executer(U1, "consulter", skill_id=sid)
        self.assertIn('name: "Nouveau nom"', texte)
        self.assertFalse(base.tables["skills"][0]["actif"])
        self.assertIn("references/g.md", texte)

    def test_modifier_infos_sans_rien_a_changer(self):
        sid = creer()
        self.assertTrue(A.executer(U1, "modifier_infos", skill_id=sid).startswith("Erreur"))
        self.assertTrue(A.executer(U1, "modifier_infos", skill_id=sid, actif="peut-etre").startswith("Erreur"))

    def test_changer_l_en_tete_dans_le_skill_md_est_signale(self):
        sid = creer()
        texte = A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="SKILL.md", contenu='---\nname: "Autre"\ndescription: "x"\n---\n\nCorps')
        self.assertIn("modifier_infos", texte)
        self.assertEqual(base.tables["skills"][0]["nom"], "Mon skill")

    def test_fichier_non_texte_bloque_toute_modification(self):
        sid = creer()
        A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="a.md", contenu="1")
        ligne = next(l for l in base.tables["skill_files"] if l["chemin"] == "a.md")
        r2.objets[ligne["cle_stockage"]] = b"\xff\xfe\x00\x80"
        for action, extra in (("ecrire_fichier", {"chemin": "b.md", "contenu": "2"}), ("modifier_infos", {"nom": "N"}), ("supprimer_fichier", {"chemin": "a.md"})):
            texte = A.executer(U1, action, skill_id=sid, **extra)
            self.assertIn("n'est pas du texte", texte, action)
        self.assertEqual(len(base.tables["skill_files"]), 2, "aucun fichier perdu")

    def test_le_skill_d_un_autre_utilisateur_est_introuvable(self):
        sid = creer(user=U2)
        for action in ("consulter", "supprimer"):
            self.assertTrue(A.executer(U1, action, skill_id=sid).startswith("Erreur"), action)
        self.assertTrue(A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="a.md", contenu="x").startswith("Erreur"))
        self.assertEqual(len(base.tables["skills"]), 1)

    def test_lister_montre_etat_et_masque_le_besoin_d_id_a_l_utilisateur(self):
        sid = creer()
        A.executer(U1, "modifier_infos", skill_id=sid, actif="non")
        creer(nom="Autre", user=U2)
        texte = A.executer(U1, "lister")
        self.assertIn("Mon skill (désactivé)", texte)
        self.assertNotIn("Autre", texte)
        self.assertIn("ne jamais montrer", texte)
        self.assertEqual(A.executer(U2, "lister").count("- "), 1)

    def test_supprimer_retire_le_skill_et_ses_fichiers(self):
        sid = creer()
        A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="a.md", contenu="1")
        self.assertIn("supprimé", A.executer(U1, "supprimer", skill_id=sid))
        self.assertEqual(base.tables["skills"], [])
        self.assertEqual(r2.objets, {})

    def test_erreurs_claires(self):
        self.assertIn("inconnue", A.executer(U1, "danser"))
        self.assertIn("skill_id", A.executer(U1, "consulter"))
        self.assertTrue(A.executer(U1, "creer", nom="  ").startswith("Erreur"))
        self.assertTrue(A.executer(U1, "creer", nom="x" * 200).startswith("Erreur"))

    def test_echec_technique_ne_fuit_pas_de_json_brut(self):
        sid = creer()
        base.echec_sur = ("skill_files", "select")
        texte = A.executer(U1, "consulter", skill_id=sid)
        self.assertTrue(texte.startswith("Erreur"))
        self.assertNotIn("{", texte)
        self.assertNotIn("echec base", texte)

    def test_aucun_tiret_double_dans_les_textes_renvoyes(self):
        sid = creer()
        sorties = [
            A.executer(U1, "lister"), A.executer(U1, "consulter", skill_id=sid),
            A.executer(U1, "ecrire_fichier", skill_id=sid, chemin="a.md", contenu="1"),
            A.executer(U1, "supprimer_fichier", skill_id=sid, chemin="SKILL.md"),
            A.executer(U1, "danser"),
        ]
        for t in sorties:
            self.assertNotIn("--", t.replace("---\n", ""))


class TestCatalogue(unittest.TestCase):
    def setUp(self):
        faux = mock.patch.object(C, "supabase", base)
        faux.start(); self.addCleanup(faux.stop)
        base.tables.clear(); base.echec_sur = None

    def _ligne(self, i, owner=U1, actif=True, description="d"):
        base.tables.setdefault("skills", []).append({"id": f"id{i}", "owner_id": owner, "nom": f"S{i}", "description": description, "actif": actif})

    def test_seuls_les_skills_actifs_de_l_utilisateur(self):
        self._ligne(1); self._ligne(2, actif=False); self._ligne(3, owner=U2)
        res = C.lister_catalogue_skills(U1)
        self.assertEqual([s["id"] for s in res["skills"]], ["id1"])
        self.assertEqual(res["total"], 1)

    def test_visiteur_sans_compte_et_erreur_donnent_un_catalogue_vide(self):
        self._ligne(1)
        self.assertEqual(C.lister_catalogue_skills(None), {"skills": [], "total": 0})
        base.echec_sur = ("skills", "select")
        self.assertEqual(C.lister_catalogue_skills(U1), {"skills": [], "total": 0})

    def test_description_tronquee(self):
        self._ligne(1, description="x" * 5000)
        d = C.lister_catalogue_skills(U1)["skills"][0]["description"]
        self.assertLessEqual(len(d), config_skills.CATALOGUE_DESCRIPTION_MAX)
        self.assertTrue(d.endswith("…"))


class TestDeclaration(unittest.TestCase):
    def test_outil_declare_partout(self):
        from core import registre_outils as R
        self.assertIn("gerer_skill:supprimer", R.OUTILS_SENSIBLES)
        self.assertIn("gerer_skill:supprimer_fichier", R.OUTILS_SENSIBLES)
        self.assertIn("gerer_skill", R.REGISTRE_AFFICHAGE_OUTILS)
        self.assertIn("gerer_skill", R.CATEGORIES_OUTILS["skills"])
        self.assertIn("gerer_configuration", R.CATEGORIES_OUTILS["configuration"])
        self.assertNotIn("gerer_skill", R.CATEGORIES_OUTILS["configuration"])
        self.assertIn("gerer_configuration:supprimer", R.OUTILS_SENSIBLES)
        self.assertNotIn("gerer_comportement", R.REGISTRE_AFFICHAGE_OUTILS)
        from core.libelles_outils_anglais import LIBELLES_OUTILS_EN
        self.assertIn(R.REGISTRE_AFFICHAGE_OUTILS["gerer_skill"]["label"], LIBELLES_OUTILS_EN)
        self.assertIn(R.REGISTRE_AFFICHAGE_OUTILS["gerer_configuration"]["label"], LIBELLES_OUTILS_EN)


if __name__ == "__main__":
    unittest.main()
