"""Tests du script de synchronisation des skills officiels (dossier skills_plateforme/ vers base et R2)."""
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault(
    "SUPABASE_SECRET",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x",
)
logging.disable(logging.CRITICAL)

from test_skills_api import r2, base, _stock  # noqa: E402
from api import skills as S  # noqa: E402
from core import skills_catalogue as C, skills_actions as A  # noqa: E402
from scripts import synchroniser_skills_plateforme as SYNC  # noqa: E402

DEPOT = Path(__file__).resolve().parent / "skills_plateforme"
SLUGS = ["documents-excel", "documents-powerpoint", "documents-word"]
U1 = "user-1"


class TestSynchronisation(unittest.TestCase):
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
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.dossier = self.tmp / "skills_plateforme"
        shutil.copytree(DEPOT, self.dossier)

    def test_les_trois_fiches_du_depot_sont_valides(self):
        bilan = SYNC.synchroniser(False, DEPOT)
        self.assertEqual(bilan["erreurs"], [])
        self.assertEqual(sorted(bilan["crees"]), SLUGS)

    def test_simuler_n_ecrit_rien(self):
        SYNC.synchroniser(False, self.dossier)
        self.assertEqual(base.tables.get("skills", []), [])
        self.assertEqual(r2.objets, {})

    def test_appliquer_cree_les_skills_officiels_lisibles_par_tous(self):
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(sorted(bilan["crees"]), SLUGS)
        lignes = base.tables["skills"]
        self.assertEqual(len(lignes), 3)
        for l in lignes:
            self.assertIsNone(l["owner_id"])
            self.assertEqual(l["portee"], "plateforme")
            self.assertTrue(l["actif"])
        self.assertTrue(all(k.startswith("plateforme/") for k in r2.objets))
        officiels = C.lister_skills_officiels()
        self.assertEqual(sorted(o["nom"] for o in officiels), ["Documents Excel", "Documents PowerPoint", "Documents Word"])
        sid = next(o["id"] for o in officiels if o["nom"] == "Documents Word")
        texte = A.executer(U1, "consulter", skill_id=sid)
        self.assertFalse(texte.startswith("Erreur"))
        self.assertIn("# Documents Word (.docx)", texte)

    def test_relancer_sans_changement_ne_touche_a_rien(self):
        SYNC.synchroniser(True, self.dossier)
        cles = dict(r2.objets)
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(sorted(bilan["inchanges"]), SLUGS)
        self.assertEqual(bilan["crees"] + bilan["mis_a_jour"], [])
        self.assertEqual(r2.objets, cles)

    def test_un_changement_met_a_jour_et_retire_l_ancienne_version(self):
        SYNC.synchroniser(True, self.dossier)
        anciennes = set(r2.objets)
        fiche = self.dossier / "documents-word" / "SKILL.md"
        fiche.write_text(fiche.read_text(encoding="utf-8") + "\nNouvelle règle.\n", encoding="utf-8")
        (self.dossier / "documents-word" / "references").mkdir()
        (self.dossier / "documents-word" / "references" / "exemple.md").write_text("Exemple", encoding="utf-8")
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(bilan["mis_a_jour"], ["documents-word"])
        self.assertEqual(sorted(bilan["inchanges"]), ["documents-excel", "documents-powerpoint"])
        nouvelles = set(r2.objets) - anciennes
        self.assertEqual(len(nouvelles), 2)
        self.assertFalse(any("documents" in k for k in r2.objets))  # clés par identifiant, jamais par nom
        sid = next(l["id"] for l in base.tables["skills"] if l["slug"] == "documents-word")
        self.assertIn("Nouvelle règle.", A.executer(U1, "consulter", skill_id=sid))
        self.assertIn("Exemple", A.executer(U1, "consulter", skill_id=sid, chemin="references/exemple.md"))
        self.assertEqual(len(base.tables["skills"]), 3, "pas de doublon")

    def test_le_cache_est_vide_apres_une_synchronisation(self):
        self.assertEqual(C.lister_skills_officiels(), [])
        SYNC.synchroniser(True, self.dossier)
        self.assertEqual(len(C.lister_skills_officiels()), 3)

    def test_un_skill_absent_du_dossier_est_signale_jamais_supprime(self):
        SYNC.synchroniser(True, self.dossier)
        shutil.rmtree(self.dossier / "documents-excel")
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(bilan["absents"], ["documents-excel"])
        self.assertEqual(len(base.tables["skills"]), 3)
        self.assertTrue(all(l["actif"] for l in base.tables["skills"]))

    def test_un_dossier_invalide_est_signale_sans_bloquer_les_autres(self):
        (self.dossier / "sans-fiche").mkdir()
        (self.dossier / "sans-entete").mkdir()
        (self.dossier / "sans-entete" / "SKILL.md").write_text("juste du texte", encoding="utf-8")
        (self.dossier / "binaire").mkdir()
        (self.dossier / "binaire" / "SKILL.md").write_text("---\nname: \"B\"\ndescription: \"d\"\n---\ncorps", encoding="utf-8")
        (self.dossier / "binaire" / "image.png").write_bytes(b"\x89PNG\xff\xfe")
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(len(bilan["erreurs"]), 3)
        self.assertEqual(sorted(bilan["crees"]), SLUGS)

    def test_dossier_introuvable_donne_une_erreur_claire(self):
        bilan = SYNC.synchroniser(True, self.tmp / "nexiste-pas")
        self.assertEqual(len(bilan["erreurs"]), 1)
        self.assertIn("introuvable", bilan["erreurs"][0])

    def test_un_echec_d_ecriture_est_signale_et_nettoie_r2(self):
        base.echec_sur = ("skills", "insert")
        bilan = SYNC.synchroniser(True, self.dossier)
        self.assertEqual(len(bilan["erreurs"]), 3)
        self.assertEqual(r2.objets, {}, "aucun objet orphelin dans R2")

    def test_le_mode_par_defaut_est_la_simulation(self):
        with mock.patch.object(SYNC, "synchroniser", return_value={"crees": [], "mis_a_jour": [], "inchanges": [], "absents": [], "erreurs": []}) as faux:
            self.assertEqual(SYNC.main([]), 0)
            faux.assert_called_once_with(False)
            faux.reset_mock()
            SYNC.main(["appliquer"])
            faux.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
