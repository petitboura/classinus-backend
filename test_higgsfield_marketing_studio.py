"""Verifie la construction et la lecture des reponses Marketing Studio, sans reseau ni base."""
import sys
import types
import unittest

# La connexion au compte partage lit Supabase a l'import : on la remplace, ces tests n'ont besoin ni de reseau ni de base.
_faux = types.ModuleType("connexions.higgsfield_mcp")
_faux.MCP_URL = "https://exemple.invalide/mcp"
_faux.etat_service = lambda: {"configure": False}
_faux.obtenir_token_service = lambda: None
sys.modules.setdefault("connexions.higgsfield_mcp", _faux)

from core import higgsfield_marketing_studio as ms
from core.higgsfield_requetes import ErreurHiggsfield

PRESET = "941ef07a-c2ab-5a0e-ac67-4e6c762c8ef2"
MEDIA = "11111111-1111-4111-8111-111111111111"
AVATAR = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"


class TestCreation(unittest.TestCase):
    def test_product_shot_minimal(self):
        a = ms.construire_creation(PRESET, "product_shots", "Ice Cube Hover", MEDIA, "", "", "", "")
        self.assertEqual(a["format_slug"], "standalone")
        self.assertEqual(a["product_media_id"], MEDIA)
        self.assertNotIn("prompt", a)  # le prompt est facultatif : absent s'il est vide
        self.assertNotIn("avatar_media_id", a)

    def test_format_slug_par_type(self):
        attendus = {"product_shots_people": "with-model", "hypermotion": "hypermotion",
                    "mixed_media": "mixed-media", "2d_motion": "2d-product-motion", "saas_motion": "saas"}
        for type_, slug in attendus.items():
            self.assertEqual(ms.construire_creation(PRESET, type_, "", MEDIA, "", "", "", "")["format_slug"], slug)

    def test_people_accepte_une_personne(self):
        a = ms.construire_creation(PRESET, "product_shots_people", "", MEDIA, AVATAR, "", " Style chaud ", "9:16")
        self.assertEqual(a["avatar_media_id"], AVATAR)
        self.assertEqual(a["prompt"], "Style chaud")
        self.assertEqual(a["aspect_ratio"], "9:16")

    def test_personne_refusee_hors_people(self):
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "hypermotion", "", MEDIA, AVATAR, "", "", "")

    def test_saas_avec_site_sans_image(self):
        a = ms.construire_creation(PRESET, "saas_motion", "", "", "", "https://exemple.com", "", "")
        self.assertEqual(a["brand_url"], "https://exemple.com")
        self.assertNotIn("product_media_id", a)

    def test_site_refuse_hors_saas_et_http(self):
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "hypermotion", "", MEDIA, "", "https://exemple.com", "", "")
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "saas_motion", "", "", "", "http://exemple.com", "", "")

    def test_refus_sans_image(self):
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "product_shots", "", "", "", "", "", "")

    def test_refus_type_inconnu_preset_invalide_format_invalide(self):
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "ugc", "", MEDIA, "", "", "", "")
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation("pas-un-uuid", "product_shots", "", MEDIA, "", "", "", "")
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "product_shots", "", MEDIA, "", "", "", "carre")

    def test_prompt_trop_long(self):
        with self.assertRaises(ErreurHiggsfield):
            ms.construire_creation(PRESET, "product_shots", "", MEDIA, "", "", "x" * 5001, "")


class TestStatut(unittest.TestCase):
    def _res(self, statut, **autres):
        return {"structuredContent": {"jobs": [{"id": JOB, "status": statut, **autres}]}}

    def test_en_cours(self):
        for statut in ("queued", "in_progress", "processing", "pending"):
            self.assertEqual(ms.interpreter_statut(self._res(statut), JOB)["etat"], "en_cours")

    def test_terminee_avec_adresse(self):
        r = ms.interpreter_statut(self._res("completed", result={"url": "https://cdn.exemple.com/a.mp4?x=1"}), JOB)
        self.assertEqual(r["etat"], "terminee")
        self.assertEqual(r["url"], "https://cdn.exemple.com/a.mp4?x=1")

    def test_terminee_sans_adresse_reste_en_cours(self):
        self.assertEqual(ms.interpreter_statut(self._res("completed"), JOB)["etat"], "en_cours")

    def test_echec(self):
        r = ms.interpreter_statut(self._res("failed"), JOB)
        self.assertEqual(r["etat"], "echec")
        self.assertIsNone(r["url"])

    def test_ne_lit_pas_le_job_d_un_autre(self):
        autre = "44444444-4444-4444-8444-444444444444"
        res = {"structuredContent": {"jobs": [
            {"id": autre, "status": "completed", "url": "https://cdn.exemple.com/autre.mp4"},
            {"id": JOB, "status": "queued"},
        ]}}
        self.assertEqual(ms.interpreter_statut(res, JOB)["etat"], "en_cours")


class TestUuid(unittest.TestCase):
    def test_trouver_uuid_prefere_la_cle(self):
        donnees = {"a": MEDIA, "job": {"job_id": JOB}}
        self.assertEqual(ms.trouver_uuid(donnees, ("job",)), JOB)
        self.assertEqual(ms.trouver_uuid({"x": MEDIA}, ("media",)), MEDIA)
        self.assertIsNone(ms.trouver_uuid({"x": "rien"}, ("job",)))


if __name__ == "__main__":
    unittest.main()
