"""
Tests des outils MCP de travail sur les documents joints (21/11/2026) : le chemin complet
d'un outil, du fichier joint retrouvé jusqu'au texte rendu au modèle. Les fichiers sont de
vrais documents ; seuls le stockage et la bibliothèque sont simulés (voir
test_travail_documents.py pour la logique elle-même).
"""

import io
import os
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import core.outils_travail_documents as outils  # noqa: E402
from core import registre_outils  # noqa: E402
from core.libelles_outils_anglais import LIBELLES_OUTILS_EN  # noqa: E402

NOUVEAUX_OUTILS = [
    "modifier_document_conversation", "fusionner_pdf", "decouper_pdf", "tourner_pages_pdf", "remplir_formulaire_pdf",
]


def _ctx(user_id="u1"):
    requete = SimpleNamespace(query_params={"user_id": user_id} if user_id else {})
    return SimpleNamespace(request_context=SimpleNamespace(request=requete))


def _pdf(n=3):
    import fitz

    document = fitz.open()
    for i in range(n):
        document.new_page().insert_text((72, 72), f"page {i + 1}")
    octets = document.tobytes()
    document.close()
    return octets


def _docx():
    import docx

    document = docx.Document()
    document.add_paragraph("Bonjour Awa")
    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


@pytest.fixture
def faux_stockage():
    """Fichiers joints simulés {url: (nom, type_mime, octets)} et envois recueillis."""
    fichiers = {}
    envois = []

    def retrouver(url, user_id):
        if url not in fichiers or user_id != "u1":
            return None
        nom, mime, octets = fichiers[url]
        return {"nom_fichier": nom, "type_mime": mime}, octets

    def publier(ctx, octets, extension, type_mime, nom_fichier):
        envois.append((extension, nom_fichier, octets))
        return {"url": f"https://stockage/{len(envois)}.{extension}", "url_apercu": None}

    with mock.patch.object(outils, "retrouver_fichier", retrouver), mock.patch.object(outils, "_publier", publier):
        yield fichiers, envois


def test_modifier_un_word_rend_un_nouveau_fichier_et_garde_l_original(faux_stockage):
    fichiers, envois = faux_stockage
    original = _docx()
    fichiers["http://f/cv.docx"] = ("cv.docx", "", original)
    reponse = outils.modifier_document_conversation(
        _ctx(), "http://f/cv.docx", [{"action": "remplacer_texte", "chercher": "Awa", "remplacer": "Fatou"}]
    )
    assert "Fichier modifié : https://stockage/1.docx" in reponse and "L'original est resté intact" in reponse
    assert envois[0][1] == "cv_modifie.docx"
    import docx

    assert docx.Document(io.BytesIO(envois[0][2])).paragraphs[0].text == "Bonjour Fatou"
    assert fichiers["http://f/cv.docx"][2] == original


def test_une_operation_en_echec_ne_livre_rien(faux_stockage):
    fichiers, envois = faux_stockage
    fichiers["http://f/cv.docx"] = ("cv.docx", "", _docx())
    reponse = outils.modifier_document_conversation(
        _ctx(), "http://f/cv.docx", [{"action": "remplacer_texte", "chercher": "zzz", "remplacer": "a"}]
    )
    assert reponse.startswith("Aucune modification livrée, opération 1") and not envois


def test_ancien_format_office_refuse_avec_une_explication(faux_stockage):
    fichiers, _ = faux_stockage
    fichiers["http://f/vieux.doc"] = ("vieux.doc", "", b"x")
    reponse = outils.modifier_document_conversation(_ctx(), "http://f/vieux.doc", [{"action": "ajouter_paragraphe", "texte": "x"}])
    assert "anciens formats" in reponse


def test_fichier_d_un_autre_compte_ou_inconnu(faux_stockage):
    fichiers, _ = faux_stockage
    fichiers["http://f/a.pdf"] = ("a.pdf", "application/pdf", _pdf())
    assert "introuvable" in outils.fusionner_pdf(_ctx("autre"), ["http://f/a.pdf", "http://f/a.pdf"])
    assert "introuvable" in outils.decouper_pdf(_ctx(), "http://f/inconnu.pdf", ["1"])
    assert "manquant" in outils.decouper_pdf(_ctx(), "", ["1"])


def test_utilisateur_non_authentifie(faux_stockage):
    for reponse in (
        outils.modifier_document_conversation(_ctx(None), "x", []),
        outils.fusionner_pdf(_ctx(None), ["a", "b"]),
        outils.decouper_pdf(_ctx(None), "x"),
        outils.tourner_pages_pdf(_ctx(None), "x", 90),
        outils.remplir_formulaire_pdf(_ctx(None), "x"),
        outils.fusionner_pdf(None, ["a", "b"]),
    ):
        assert "non authentifié" in reponse


def test_fusion_de_deux_pdf(faux_stockage):
    fichiers, envois = faux_stockage
    fichiers["http://f/a.pdf"] = ("a.pdf", "application/pdf", _pdf(2))
    fichiers["http://f/b.pdf"] = ("b.pdf", "", _pdf(1))
    reponse = outils.fusionner_pdf(_ctx(), ["http://f/a.pdf", "http://f/b.pdf"], "Dossier complet")
    assert "2 fichiers, 3 pages" in reponse and envois[0][1] == "Dossier complet.pdf"
    assert "au moins deux" in outils.fusionner_pdf(_ctx(), ["http://f/a.pdf"])


def test_fusion_refuse_un_fichier_qui_n_est_pas_un_pdf(faux_stockage):
    fichiers, envois = faux_stockage
    fichiers["http://f/a.pdf"] = ("a.pdf", "application/pdf", _pdf(1))
    fichiers["http://f/b.docx"] = ("b.docx", "", _docx())
    assert "pas au bon format" in outils.fusionner_pdf(_ctx(), ["http://f/a.pdf", "http://f/b.docx"]) and not envois


def test_decoupage_en_plusieurs_pdf(faux_stockage):
    fichiers, envois = faux_stockage
    fichiers["http://f/cours.pdf"] = ("cours.pdf", "", _pdf(5))
    reponse = outils.decouper_pdf(_ctx(), "http://f/cours.pdf", ["1-2", "3-5"])
    assert "coupé en 2 PDF" in reponse and [e[1] for e in envois] == ["cours_1.pdf", "cours_2.pdf"]
    assert "plages" in outils.decouper_pdf(_ctx(), "http://f/cours.pdf")  # sans consigne : message clair


def test_rotation(faux_stockage):
    fichiers, envois = faux_stockage
    fichiers["http://f/scan.pdf"] = ("scan.pdf", "", _pdf(3))
    reponse = outils.tourner_pages_pdf(_ctx(), "http://f/scan.pdf", 90, "2")
    assert "1 page(s) tournée(s)" in reponse and envois[0][1] == "scan_pivote.pdf"
    assert "multiple de 90" in outils.tourner_pages_pdf(_ctx(), "http://f/scan.pdf", 45)


def test_formulaire_en_deux_temps(faux_stockage):
    import fitz

    fichiers, envois = faux_stockage
    document = fitz.open()
    page = document.new_page()
    champ = fitz.Widget()
    champ.field_name, champ.field_type = "Nom", fitz.PDF_WIDGET_TYPE_TEXT
    champ.rect = fitz.Rect(72, 72, 300, 100)
    page.add_widget(champ)
    fichiers["http://f/form.pdf"] = ("form.pdf", "", document.tobytes())

    liste = outils.remplir_formulaire_pdf(_ctx(), "http://f/form.pdf")
    assert "Nom (type Text, page 1" in liste and not envois  # premier temps : aucun fichier créé

    rempli = outils.remplir_formulaire_pdf(_ctx(), "http://f/form.pdf", {"Nom": "Awa", "Fantome": "x"})
    assert "1 champ(s) : Nom" in rempli and "introuvables, non remplis : Fantome" in rempli
    assert envois[0][1] == "form_rempli.pdf"

    fichiers["http://f/plat.pdf"] = ("plat.pdf", "", _pdf(1))
    assert "aucun champ de formulaire" in outils.remplir_formulaire_pdf(_ctx(), "http://f/plat.pdf")


def test_fichier_trop_gros(faux_stockage):
    fichiers, _ = faux_stockage
    fichiers["http://f/a.pdf"] = ("a.pdf", "", _pdf(1))
    with mock.patch.object(outils, "taille_max_document_travail_octets", lambda: 10):
        assert "trop gros" in outils.decouper_pdf(_ctx(), "http://f/a.pdf", ["1"])


def test_une_panne_du_stockage_donne_une_erreur_propre(faux_stockage):
    fichiers, _ = faux_stockage
    fichiers["http://f/a.pdf"] = ("a.pdf", "", _pdf(3))
    with mock.patch.object(outils, "_publier", side_effect=RuntimeError("stockage en panne")):
        assert outils.tourner_pages_pdf(_ctx(), "http://f/a.pdf", 90) == outils.ERREUR_GENERALE


# Branchement : jamais un outil sans libellé, sans version anglaise ni catégorie

@pytest.mark.parametrize("nom", NOUVEAUX_OUTILS)
def test_chaque_outil_a_libelle_icone_categorie_et_version_anglaise(nom):
    entree = registre_outils.REGISTRE_AFFICHAGE_OUTILS[nom]
    assert len(entree["label"]) <= 28  # une ligne sur téléphone
    assert entree["label"] in LIBELLES_OUTILS_EN
    assert nom in registre_outils.CATEGORIES_OUTILS["document_joint"]
    assert nom in registre_outils.CATEGORIES_OUTILS["generation_documents"]
    assert "--" not in entree["label"] and "--" not in LIBELLES_OUTILS_EN[entree["label"]]


def test_les_outils_sont_enregistres_sur_le_serveur_mcp():
    import core.serveur_mcp_generation  # noqa: F401  # l'import enregistre les outils

    from core.outils_generation_commun import mcp_generation

    import asyncio

    noms = {t.name for t in asyncio.run(mcp_generation.list_tools())}
    assert set(NOUVEAUX_OUTILS) <= noms


def test_la_migration_declare_les_cinq_outils():
    texte = open("migrations/2026_11_21_outils_travail_documents.sql", encoding="utf-8").read()
    for nom in NOUVEAUX_OUTILS:
        assert f"'{nom}'" in texte
