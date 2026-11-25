"""Tests du script de migration des skills historiques (logique pure, sans réseau)."""
import logging
import os
import unittest

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
logging.disable(logging.CRITICAL)

from scripts import migrer_skills_vers_r2 as M
from test_skills_api import FauxR2, FausseBase


class TestMigration(unittest.TestCase):
    def test_skill_classique_devient_prive_avec_entete_coherent(self):
        plan = M.preparer({"id": "c1", "etudiant_id": "u1", "nom": "Mon skill", "description": "d", "texte": "corps", "skill_md": None, "actif": False}, False)
        s = plan["skill"]
        self.assertEqual((s["visibilite"], s["actif"], s["legacy_behavior_id"], s["owner_id"]), ("prive", False, "c1", "u1"))
        self.assertTrue(plan["contenu"].startswith('---\nname: "Mon skill"\ndescription: "d"\n---\n'))
        self.assertTrue(plan["contenu"].endswith("corps"))

    def test_skill_public_publie_garde_ses_compteurs(self):
        plan = M.preparer({"id": "p1", "auteur_id": "u2", "nom": "Pub", "description": "", "texte": "t", "skill_md": "---\nname: x\n---\ncorps",
                           "statut": "publie", "activations_count": 2, "partages_count": 3, "etoiles_count": 0, "cta_count": 0}, True)
        s = plan["skill"]
        self.assertEqual((s["visibilite"], s["actif"], s["activations_count"], s["partages_count"], s["legacy_public_id"]), ("public", True, 2, 3, "p1"))
        self.assertIn('name: "Pub"', plan["contenu"])
        self.assertNotIn("name: x", plan["contenu"])

    def test_skill_public_retire_ne_reapparait_pas_actif(self):
        plan = M.preparer({"id": "p2", "auteur_id": "u2", "nom": "Vieux", "description": "", "texte": "t", "skill_md": "", "statut": "retire", "retire_le": "2026-10-01T00:00:00+00:00"}, True)
        s = plan["skill"]
        self.assertEqual((s["visibilite"], s["actif"], s["retire_le"]), ("retire", False, "2026-10-01T00:00:00+00:00"))

    def test_dossier_du_skill_porte_le_nom_exact(self):
        self.assertEqual(M.dossier_du_skill("Mon cours d'algèbre"), "Mon cours d'algèbre")
        self.assertEqual(M.dossier_du_skill("a/b\\c"), "a b c")
        self.assertEqual(M.dossier_du_skill("  "), "Skill")
        db, bucket = FausseBase(), FauxR2()
        plan = M.preparer({"id": "c1", "etudiant_id": "u1", "nom": "Mon cours", "description": "d", "texte": "t"}, False)
        M.ecrire(db, bucket, plan)
        self.assertEqual(list(bucket.objets), ["u1/c1/Mon cours/SKILL.md"])
        self.assertEqual(db.tables["skill_files"][0]["chemin"], "SKILL.md")

    def test_les_ajouts_existants_sont_relies_sans_doublon(self):
        db = FausseBase()
        db.tables["comportement_public_activations"] = [
            {"comportement_public_id": "p1", "active_par": "u9", "comportement_etudiant_id": "c9"},
            {"comportement_public_id": "p1", "active_par": "u8", "comportement_etudiant_id": "absent"},
            {"comportement_public_id": "p1", "active_par": "u7", "comportement_etudiant_id": None},
        ]
        db.tables["skills"] = [{"id": "p1"}, {"id": "s9", "legacy_behavior_id": "c9"}]
        db.tables["skill_activations"] = []
        self.assertEqual(M.lier_activations(db, executer=False), {"a_lier": 1, "deja_lies": 0, "ignores": 2, "lies": 0})
        self.assertEqual(db.tables["skill_activations"], [])
        self.assertEqual(M.lier_activations(db, executer=True)["lies"], 1)
        lien = db.tables["skill_activations"][0]
        self.assertEqual((lien["skill_source_id"], lien["copie_id"], lien["active_par"], lien["version_copiee"]), ("p1", "s9", "u9", 1))
        self.assertEqual(M.lier_activations(db, executer=True), {"a_lier": 0, "deja_lies": 1, "ignores": 2, "lies": 0})
        self.assertEqual(len(db.tables["skill_activations"]), 1)

    def test_sans_proprietaire_est_ignore(self):
        self.assertIsNone(M.preparer({"id": "x", "etudiant_id": None, "nom": "n"}, False))

    def test_ecriture_complete_puis_annulation_propre_en_cas_d_echec(self):
        db, bucket = FausseBase(), FauxR2()
        plan = M.preparer({"id": "c1", "etudiant_id": "u1", "nom": "N", "description": "", "texte": "t"}, False)
        M.ecrire(db, bucket, plan)
        self.assertEqual(len(db.tables["skills"]), 1)
        self.assertEqual(len(db.tables["skill_files"]), 1)
        self.assertEqual(len(bucket.objets), 1)
        db2, bucket2 = FausseBase(), FauxR2()
        db2.echec_sur = ("skill_files", "insert")
        with self.assertRaises(Exception):
            M.ecrire(db2, bucket2, plan)
        self.assertEqual(db2.tables.get("skills", []), [])
        self.assertEqual(bucket2.objets, {})


if __name__ == "__main__":
    unittest.main()
