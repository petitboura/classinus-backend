"""Tests des produits publics (28/11/2026) : logique pure, sans réseau.

On vérifie les promesses faites aux gens :
  - une adresse, un nom, une accroche ou un type invalides sont refusés avec un code clair ;
  - une image ne peut venir que du dossier du compte qui publie (jamais celui d'un autre) ;
  - le public ne voit que les produits publiés, et un créateur n'est nommé que s'il a un profil public ;
  - seul l'auteur modifie ou supprime son produit ;
  - une adresse qui vise le réseau interne n'est jamais capturée.
"""
import logging
import os
import unittest
from unittest import mock

os.environ.setdefault("SUPABASE_URL", "https://exemple.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
logging.disable(logging.CRITICAL)

from fastapi import HTTPException

from core import images_produits_publics as images
from core import produits_publics as P

MOI, AUTRE = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
PRODUIT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def valide(**surcharge):
    base = {
        "nom": "Mon produit", "accroche": "Une phrase claire", "description": "",
        "type_produit": "site", "url": "monsite.com", "logo_chemin": None, "images": [], "etiquettes": [],
    }
    base.update(surcharge)
    return base


def code(exc: HTTPException) -> str:
    detail = exc.detail
    return detail.get("code") if isinstance(detail, dict) else str(detail)


class TestValidation(unittest.TestCase):
    def test_adresse_sans_schema_recoit_https(self):
        self.assertEqual(P.normaliser_url("monsite.com/page"), "https://monsite.com/page")

    def test_adresses_refusees(self):
        for mauvaise in ("", "ftp://monsite.com", "https://localhost", "https://monsite", "javascript:alert(1)", "https://x.local"):
            with self.assertRaises(HTTPException, msg=mauvaise) as c:
                P.normaliser_url(mauvaise)
            self.assertEqual(code(c.exception), "PRODUIT_URL_INVALIDE")

    def test_produit_valide(self):
        ligne = P.valider(valide(etiquettes=["IA", " ia ", "Éducation"]), MOI)
        self.assertEqual(ligne["url"], "https://monsite.com")
        self.assertEqual(ligne["etiquettes"], ["ia", "éducation"])

    def test_champs_refuses(self):
        cas = [
            (valide(nom="A"), "PRODUIT_NOM_INVALIDE"),
            (valide(accroche="abc"), "PRODUIT_ACCROCHE_INVALIDE"),
            (valide(description="x" * 5001), "PRODUIT_DESCRIPTION_INVALIDE"),
            (valide(type_produit="jeu"), "PRODUIT_TYPE_INVALIDE"),
            (valide(etiquettes=["a"]), "PRODUIT_ETIQUETTE_INVALIDE"),
            (valide(etiquettes=["un", "deux", "trois", "quatre", "cinq", "six"]), "PRODUIT_ETIQUETTE_INVALIDE"),
        ]
        for donnees, attendu in cas:
            with self.assertRaises(HTTPException) as c:
                P.valider(donnees, MOI)
            self.assertEqual(code(c.exception), attendu)

    def test_image_du_dossier_d_un_autre_refusee(self):
        chez_autre = f"produits/{AUTRE}/a.jpg"
        for donnees in (valide(images=[{"chemin": chez_autre}]), valide(logo_chemin=chez_autre), valide(images=[{"chemin": f"produits/{MOI}/../x.jpg"}])):
            with self.assertRaises(HTTPException) as c:
                P.valider(donnees, MOI)
            self.assertEqual(code(c.exception), "PRODUIT_IMAGE_INVALIDE")

    def test_image_du_compte_acceptee_sans_doublon(self):
        chemin = f"produits/{MOI}/a.jpg"
        ligne = P.valider(valide(images=[{"chemin": chemin, "alt": " Accueil "}, {"chemin": chemin}]), MOI)
        self.assertEqual(ligne["images"], [{"chemin": chemin, "alt": "Accueil"}])

    def test_trop_d_images(self):
        trop = [{"chemin": f"produits/{MOI}/{i}.jpg"} for i in range(9)]
        with self.assertRaises(HTTPException) as c:
            P.valider(valide(images=trop), MOI)
        self.assertEqual(code(c.exception), "PRODUIT_TROP_D_IMAGES")


class TestRecherche(unittest.TestCase):
    def test_mots_surs(self):
        self.assertEqual(P._mots_de_recherche("a, (appli) %outil% x"), ["appli", "outil"])
        self.assertEqual(len(P._mots_de_recherche("un deux trois quatre cinq six sept")), 5)


class TestPresentation(unittest.TestCase):
    def ligne(self):
        return {"id": PRODUIT, "auteur_id": MOI, "nom": "N", "accroche": "Accroche", "type_produit": "appli", "url": "https://n.com",
                "logo_chemin": None, "images": [{"chemin": f"produits/{MOI}/a.jpg", "alt": ""}], "etiquettes": []}

    def test_createur_anonyme_sans_profil_public(self):
        with mock.patch.object(P, "url_image", side_effect=lambda c: f"https://api/{c}" if c else None):
            sortie = P.presenter(self.ligne(), {}, None)
        self.assertIsNone(sortie["createur_nom"])
        self.assertFalse(sortie["est_a_moi"])
        self.assertEqual(sortie["images"][0]["url"], f"https://api/produits/{MOI}/a.jpg")

    def test_createur_nomme_et_reconnu(self):
        with mock.patch.object(P, "url_image", return_value=None):
            sortie = P.presenter(self.ligne(), {MOI: "Awa"}, MOI)
        self.assertEqual(sortie["createur_nom"], "Awa")
        self.assertTrue(sortie["est_a_moi"])


class TestDroits(unittest.TestCase):
    def test_produit_inconnu_ou_retire_donne_404(self):
        with mock.patch.object(P, "_ligne_publiee", return_value=None):
            with self.assertRaises(HTTPException) as c:
                P.obtenir(PRODUIT)
        self.assertEqual(c.exception.status_code, 404)

    def test_identifiant_qui_n_est_pas_un_uuid_donne_404(self):
        self.assertIsNone(P._ligne_publiee("pas-un-uuid"))

    def test_on_ne_modifie_ni_ne_supprime_le_produit_d_un_autre(self):
        ligne = {"id": PRODUIT, "auteur_id": AUTRE}
        with mock.patch.object(P, "_ligne_publiee", return_value=ligne):
            for action in (lambda: P.modifier(PRODUIT, valide(), MOI), lambda: P.supprimer(PRODUIT, MOI)):
                with self.assertRaises(HTTPException) as c:
                    action()
                self.assertEqual(c.exception.status_code, 404)


class TestImages(unittest.TestCase):
    def test_type_non_accepte(self):
        with self.assertRaises(HTTPException) as c:
            images.envoyer_image(MOI, b"x", "image/gif")
        self.assertEqual(code(c.exception), "PRODUIT_IMAGE_TYPE_INVALIDE")

    def test_fichier_illisible(self):
        with self.assertRaises(HTTPException) as c:
            images.envoyer_image(MOI, b"pas une image", "image/png")
        self.assertEqual(code(c.exception), "PRODUIT_IMAGE_ILLISIBLE")

    def test_image_reduite_et_rangee_dans_le_dossier_du_compte(self):
        from io import BytesIO
        from PIL import Image
        tampon = BytesIO()
        Image.new("RGB", (4000, 2000), "white").save(tampon, format="PNG")
        envoyes = {}

        class Faux:
            def upload(self, chemin, contenu, options=None):
                envoyes["chemin"], envoyes["contenu"] = chemin, contenu

            def get_public_url(self, chemin):
                return f"https://api/{chemin}"

        with mock.patch.object(images.stockage_r2, "from_", return_value=Faux()), mock.patch.object(images, "url_image", side_effect=lambda c: f"https://api/{c}"):
            sortie = images.envoyer_image(MOI, tampon.getvalue(), "image/png")
        self.assertTrue(sortie["chemin"].startswith(f"produits/{MOI}/"))
        self.assertEqual(Image.open(BytesIO(envoyes["contenu"])).width, 1800)

    def test_capture_d_une_adresse_interne_refusee(self):
        for interne in ("http://localhost:8000", "http://127.0.0.1", "http://169.254.169.254/latest"):
            with self.assertRaises(HTTPException) as c:
                images.capturer_site(MOI, interne)
            self.assertEqual(code(c.exception), "PRODUIT_URL_INVALIDE")

    def test_quota_de_captures_par_heure(self):
        images._historique_captures.clear()
        for _ in range(images.cfg.CAPTURES_PAR_HEURE_ET_COMPTE):
            images._verifier_quota_capture(MOI)
        with self.assertRaises(HTTPException) as c:
            images._verifier_quota_capture(MOI)
        self.assertEqual(c.exception.status_code, 429)
        images._historique_captures.clear()


if __name__ == "__main__":
    unittest.main()
