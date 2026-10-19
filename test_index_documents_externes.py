"""
Tests de l'index des categories envoye au modele et des consignes de priorite
des livres et PDF (10/10/2026). Aucun acces reseau.
"""

import sys

sys.path.append("core")  # comme les autres tests

import core.outils_documents_externes as outil  # noqa: E402
import core.routage_outils as routage  # noqa: E402
import core.sources_documents_externes as registre  # noqa: E402
from core.registre_outils import INDEX_CATEGORIES_OUTILS  # noqa: E402


def test_index_cite_toutes_les_sources_actives():
    for nom in registre.noms_sources():
        assert nom in INDEX_CATEGORIES_OUTILS, nom


def test_index_ne_se_limite_plus_a_internet_archive():
    assert "d'Internet Archive, hors de Classinus" not in INDEX_CATEGORIES_OUTILS
    assert "documents_externes" in INDEX_CATEGORIES_OUTILS and "recherche_web" in INDEX_CATEGORIES_OUTILS


def test_description_de_demander_outils_donne_le_reflexe_livres_et_pdf():
    description = routage._outil_demander_outils()["function"]["description"]
    assert "REFLEXE LIVRES ET PDF" in description
    assert "documents_externes" in description and "recherche_web" in description


def test_description_de_l_outil_dit_quand_ajouter_le_web():
    # Le texte passe à la ligne au milieu des phrases : on compare sans les retours.
    texte = " ".join(outil.rechercher_document_externe.__doc__.split())
    for mot in ("premier réflexe", "AVANT la recherche web", "tavily_search", "dis à l'étudiant d'où vient"):
        assert mot in texte, mot


def test_textes_ajoutes_sans_tirets_doubles():
    description = routage._outil_demander_outils()["function"]["description"]
    paragraphe_reflexe = description.split("REFLEXE LIVRES ET PDF")[1].split("PRIORITE")[0]
    for texte in (INDEX_CATEGORIES_OUTILS, paragraphe_reflexe, outil.rechercher_document_externe.__doc__):
        assert "--" not in texte and "—" not in texte
