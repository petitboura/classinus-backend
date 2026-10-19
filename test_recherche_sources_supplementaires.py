"""
Tests des sources arXiv, Zenodo, OpenAlex et Project Gutenberg de la
recherche de documents externes (10/10/2026). Aucun accès réseau : les
réponses ci-dessous sont des EXEMPLES FABRIQUÉS d'après la documentation de
leurs API, pas de vraies réponses (ces services ne sont pas joignables
depuis l'environnement de développement). Ils vérifient la logique de
lecture, pas l'accord avec les vrais services : à confirmer en production.
"""

import sys

import pytest

sys.path.append("core")

import core.recherche_arxiv as arxiv  # noqa: E402
import core.recherche_documents_commun as commun  # noqa: E402
import core.recherche_gutenberg as gutenberg  # noqa: E402
import core.recherche_openalex as openalex  # noqa: E402
import core.recherche_zenodo as zenodo  # noqa: E402
import core.sources_documents_externes as registre  # noqa: E402
from core.recherche_documents_commun import ErreurRechercheSource  # noqa: E402


class Reponse:
    def __init__(self, corps=None, contenu=b""):
        self.status_code = 200
        self._corps = corps
        self.content = contenu

    def json(self):
        if self._corps is None:
            raise ValueError("pas du json")
        return self._corps

    def raise_for_status(self):
        pass


def brancher(monkeypatch, module, reponse):
    appels = []

    def faux(url, params, nom_source):
        appels.append((url, params))
        return reponse

    monkeypatch.setattr(module, "appeler_service", faux)
    return appels


XML_ARXIV = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2101.00001v2</id>
    <published>2021-01-01T10:00:00Z</published>
    <title>Un article
       sur les groupes</title>
    <author><name>Alice Martin</name></author>
    <author><name>Bob Durand</name></author>
    <link href="http://arxiv.org/abs/2101.00001v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2101.00001v2" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://autre-site.example/abs/1</id>
    <title>Sans lien arXiv</title>
  </entry>
</feed>"""


def test_arxiv_lit_les_entrees_et_ignore_les_liens_inconnus(monkeypatch):
    appels = brancher(monkeypatch, arxiv, Reponse(contenu=XML_ARXIV))
    documents = arxiv.rechercher_documents("groupes finis", 5)
    assert len(documents) == 1
    d = documents[0]
    assert d["titre"] == "Un article sur les groupes"
    assert d["auteur"] == "Alice Martin, Bob Durand"
    assert d["annee"] == "2021"
    assert d["url"] == "https://arxiv.org/abs/2101.00001v2"
    assert d["url_fichier"] == "https://arxiv.org/pdf/2101.00001v2"
    assert d["acces"] == "libre"
    assert appels[0][1]["search_query"] == "all:groupes AND all:finis"


def test_arxiv_xml_illisible_et_demande_vide(monkeypatch):
    brancher(monkeypatch, arxiv, Reponse(contenu=b"pas du xml"))
    with pytest.raises(ErreurRechercheSource):
        arxiv.rechercher_documents("groupes", 3)
    appels = brancher(monkeypatch, arxiv, Reponse(contenu=XML_ARXIV))
    assert arxiv.rechercher_documents("   ", 3) == [] and appels == []


JSON_ZENODO = {"hits": {"hits": [
    {"id": 123, "links": {"self_html": "https://zenodo.org/records/123"},
     "metadata": {"title": "Cours d'algèbre", "creators": [{"name": "Dupont, Jean"}],
                  "publication_date": "2020-05-12", "language": "fra"},
     "files": [{"key": "notes.docx"}, {"key": "cours complet.pdf"}]},
    {"id": 124, "links": {"self_html": "https://zenodo.org/records/124"},
     "metadata": {"title": "Jeu de données"}, "files": [{"key": "donnees.csv"}]},
    {"id": 125, "links": {"self_html": "https://autre.example/records/125"},
     "metadata": {"title": "Lien douteux"}, "files": [{"key": "a.pdf"}]},
]}}


def test_zenodo_garde_les_depots_lisibles_et_prefere_le_pdf(monkeypatch):
    brancher(monkeypatch, zenodo, Reponse(corps=JSON_ZENODO))
    documents = zenodo.rechercher_documents("algèbre", 5)
    assert len(documents) == 1
    d = documents[0]
    assert d["titre"] == "Cours d'algèbre" and d["annee"] == "2020" and d["langue"] == "fra"
    assert d["url"] == "https://zenodo.org/records/123"
    assert d["url_fichier"] == "https://zenodo.org/records/123/files/cours%20complet.pdf?download=1"


def test_zenodo_reponse_inattendue(monkeypatch):
    brancher(monkeypatch, zenodo, Reponse(corps={"autre": 1}))
    with pytest.raises(ErreurRechercheSource):
        zenodo.rechercher_documents("algèbre", 3)
    brancher(monkeypatch, zenodo, Reponse(corps=None))
    with pytest.raises(ErreurRechercheSource):
        zenodo.rechercher_documents("algèbre", 3)


JSON_OPENALEX = {"results": [
    {"id": "https://openalex.org/W123", "display_name": "Un article libre", "publication_year": 2019,
     "language": "en",
     "authorships": [{"author": {"display_name": "Alice Martin"}}, {"author": {"display_name": "Bob Durand"}}],
     "best_oa_location": {"pdf_url": "https://exemple.org/a.pdf", "landing_page_url": "https://exemple.org/a"}},
    {"id": "https://openalex.org/W124", "display_name": "Sans fichier direct", "publication_year": 2018,
     "authorships": [], "best_oa_location": {"pdf_url": None, "landing_page_url": "https://exemple.org/b"}},
    {"id": "https://openalex.org/W125", "display_name": "Sans version libre", "best_oa_location": None},
    {"id": "https://openalex.org/W126", "display_name": "Lien non https",
     "best_oa_location": {"pdf_url": "http://exemple.org/c.pdf", "landing_page_url": "http://exemple.org/c"}},
]}


def test_openalex_garde_les_versions_libres_en_https(monkeypatch):
    appels = brancher(monkeypatch, openalex, Reponse(corps=JSON_OPENALEX))
    documents = openalex.rechercher_documents("analyse", 5)
    assert [d["identifiant"] for d in documents] == ["W123", "W124"]
    assert documents[0]["url_fichier"] == "https://exemple.org/a.pdf"
    assert documents[0]["auteur"] == "Alice Martin, Bob Durand" and documents[0]["annee"] == "2019"
    assert "url_fichier" not in documents[1]
    assert appels[0][1]["filter"] == "open_access.is_oa:true" and "mailto" not in appels[0][1]


def test_openalex_adresse_de_contact_et_reponse_inattendue(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "contact@exemple.test")
    appels = brancher(monkeypatch, openalex, Reponse(corps=JSON_OPENALEX))
    openalex.rechercher_documents("analyse", 2)
    assert appels[0][1]["mailto"] == "contact@exemple.test"
    brancher(monkeypatch, openalex, Reponse(corps={"erreur": "x"}))
    with pytest.raises(ErreurRechercheSource):
        openalex.rechercher_documents("analyse", 2)


JSON_GUTENBERG = {"results": [
    {"id": 1342, "title": "Pride and Prejudice", "authors": [{"name": "Austen, Jane"}], "languages": ["en"],
     "formats": {"text/html": "https://www.gutenberg.org/ebooks/1342.html.images",
                 "text/plain; charset=utf-8": "https://www.gutenberg.org/ebooks/1342.txt.utf-8"}},
    {"id": 7, "title": "Sans texte brut", "authors": [], "languages": ["fr"],
     "formats": {"application/epub+zip": "https://www.gutenberg.org/ebooks/7.epub.images"}},
    {"id": 8, "title": "Texte hors Gutenberg", "authors": [], "languages": ["fr"],
     "formats": {"text/plain": "https://autre.example/8.txt"}},
]}


def test_gutenberg_lien_texte_brut_seulement_chez_gutenberg(monkeypatch):
    brancher(monkeypatch, gutenberg, Reponse(corps=JSON_GUTENBERG))
    documents = gutenberg.rechercher_documents("austen", 5)
    assert [d["identifiant"] for d in documents] == ["1342", "7", "8"]
    assert documents[0]["url"] == "https://www.gutenberg.org/ebooks/1342"
    assert documents[0]["url_fichier"] == "https://www.gutenberg.org/ebooks/1342.txt.utf-8"
    assert documents[0]["annee"] is None and documents[0]["auteur"] == "Austen, Jane"
    assert "url_fichier" not in documents[1] and "url_fichier" not in documents[2]


def test_gutenberg_reponse_inattendue(monkeypatch):
    brancher(monkeypatch, gutenberg, Reponse(corps=["pas", "un", "objet"]))
    with pytest.raises(ErreurRechercheSource):
        gutenberg.rechercher_documents("austen", 3)


def test_les_quatre_sources_sont_dans_le_registre_et_nommables():
    for cle, nom in (("arxiv", "arXiv"), ("zenodo", "Zenodo"), ("openalex", "OpenAlex"), ("gutenberg", "Project Gutenberg")):
        assert registre.SOURCES[cle]["nom"] == nom
        assert registre.identifiant_source(nom) == cle
    assert registre.identifiant_source("gutenberg.org") == "gutenberg"
    assert registre.identifiant_source("Open Alex") == "openalex"


def test_les_textes_des_nouvelles_sources_sans_tirets_doubles():
    import inspect
    for module in (arxiv, zenodo, openalex, gutenberg):
        assert "--" not in inspect.getsource(module)
