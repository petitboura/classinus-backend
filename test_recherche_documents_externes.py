"""
Tests de la recherche de documents externes multi sources (09/10/2026).
Aucun accès réseau : les réponses de Gallica et de HAL ci-dessous sont des
EXEMPLES FABRIQUÉS d'après la documentation de leurs API, pas de vraies
réponses (ces services refusent les lectures automatiques depuis
l'environnement de développement). Ils vérifient la logique de lecture, pas
l'accord avec les vrais services : à confirmer en production.
"""

import asyncio
import json
import sys

import pytest

sys.path.append("core")  # comme les autres tests : certains modules s'importent sans le préfixe core

import core.recherche_documents_commun as commun  # noqa: E402
import core.recherche_gallica as gallica  # noqa: E402
import core.recherche_hal as hal  # noqa: E402
import core.sources_documents_externes as registre  # noqa: E402
import core.outils_documents_externes as outil  # noqa: E402
from core.recherche_documents_commun import ErreurRechercheSource  # noqa: E402
from core.recherche_internet_archive import ErreurRechercheArchive  # noqa: E402


class Reponse:
    def __init__(self, code=200, corps=None, contenu=b""):
        self.status_code = code
        self._corps = corps
        self.content = contenu

    def json(self):
        if self._corps is None:
            raise ValueError("pas du json")
        return self._corps

    def raise_for_status(self):
        if self.status_code >= 400:
            raise commun.requests.HTTPError(str(self.status_code))


XML_GALLICA = b"""<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/"
    xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <srw:numberOfRecords>2</srw:numberOfRecords>
  <srw:records>
    <srw:record><srw:recordData><oai_dc:dc>
      <dc:title>Cours d'analyse</dc:title><dc:creator>Dupont, Jean</dc:creator>
      <dc:date>1895</dc:date><dc:language>fre</dc:language>
      <dc:identifier>http://gallica.bnf.fr/ark:/12148/bpt6k123456</dc:identifier>
    </oai_dc:dc></srw:recordData></srw:record>
    <srw:record><srw:recordData><oai_dc:dc>
      <dc:title>Sans lien reconnu</dc:title>
      <dc:identifier>http://autre-site.example/ark:/1/2</dc:identifier>
    </oai_dc:dc></srw:recordData></srw:record>
  </srw:records>
</srw:searchRetrieveResponse>"""


def doc(source, n):
    return {"titre": f"{source} {n}", "auteur": None, "annee": None, "langue": None,
            "identifiant": f"{source}{n}", "url": f"https://exemple.test/{source}/{n}", "acces": "libre"}


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch):
    monkeypatch.delenv("RECHERCHE_DOCUMENTS_MODE", raising=False)
    monkeypatch.setattr(commun.time, "sleep", lambda *_: None)


def sources_factices(monkeypatch, **par_source):
    """Remplace la fonction de recherche de chaque source ; une exception à lever, ou une liste."""
    for cle, comportement in par_source.items():
        def faux(requete, nombre, _c=comportement):
            if isinstance(_c, Exception):
                raise _c
            return [dict(d) for d in _c]
        monkeypatch.setitem(registre.SOURCES[cle], "rechercher", faux)


# --- Gallica ---

def test_gallica_lit_les_enregistrements_et_ignore_les_liens_inconnus(monkeypatch):
    monkeypatch.setattr(commun.requests, "get", lambda *a, **k: Reponse(contenu=XML_GALLICA))
    resultats = gallica.rechercher_documents("analyse")
    assert len(resultats) == 1
    d = resultats[0]
    assert d["url"] == "https://gallica.bnf.fr/ark:/12148/bpt6k123456"  # http remis en https
    assert d["titre"] == "Cours d'analyse" and d["auteur"] == "Dupont, Jean" and d["acces"] == "libre"


def test_gallica_xml_illisible_ou_service_en_panne(monkeypatch):
    monkeypatch.setattr(commun.requests, "get", lambda *a, **k: Reponse(contenu=b"pas du xml"))
    with pytest.raises(ErreurRechercheSource):
        gallica.rechercher_documents("analyse")
    monkeypatch.setattr(commun.requests, "get", lambda *a, **k: Reponse(code=503))
    with pytest.raises(ErreurRechercheSource):
        gallica.rechercher_documents("analyse")


def test_gallica_demande_vide_sans_appel_reseau(monkeypatch):
    def interdit(*a, **k):
        raise AssertionError("appel réseau inattendu")
    monkeypatch.setattr(commun.requests, "get", interdit)
    assert gallica.rechercher_documents(":::") == []


# --- HAL ---

def test_hal_garde_seulement_les_textes_complets_en_https(monkeypatch):
    corps = {"response": {"docs": [
        {"docid": "1", "title_s": ["Thèse A"], "authFullName_s": ["X", "Y"], "producedDateY_i": 2019,
         "language_s": ["fr"], "uri_s": "https://hal.science/hal-001", "fileMain_s": "https://hal.science/hal-001/document"},
        {"docid": "2", "title_s": ["Notice seule"], "uri_s": "https://hal.science/hal-002"},
        {"docid": "3", "title_s": ["Lien http"], "uri_s": "http://hal.science/hal-003", "fileMain_s": "x"},
        {"docid": "4", "title_s": ["Sans lien"], "fileMain_s": "x"},
    ]}}
    appels = {}

    def faux_get(url, params=None, **k):
        appels.update(params)
        return Reponse(corps=corps)
    monkeypatch.setattr(commun.requests, "get", faux_get)
    resultats = hal.rechercher_documents("these", 3)
    assert [d["identifiant"] for d in resultats] == ["1"]
    assert resultats[0]["annee"] == "2019" and resultats[0]["auteur"] == "X, Y"
    assert appels["rows"] == 6  # on demande le double pour écarter les notices


def test_hal_reponse_inattendue(monkeypatch):
    for corps in ({}, {"response": {}}, {"response": {"docs": "non"}}):
        monkeypatch.setattr(commun.requests, "get", lambda *a, _c=corps, **k: Reponse(corps=_c))
        with pytest.raises(ErreurRechercheSource):
            hal.rechercher_documents("x")


# --- Registre : mélange, pannes, source nommée ---

def test_melange_un_de_chaque_source_a_tour_de_role(monkeypatch):
    sources_factices(monkeypatch,
                     internet_archive=[doc("ia", i) for i in range(5)],
                     gallica=[doc("ga", i) for i in range(5)],
                     hal=[doc("hal", i) for i in range(5)])
    interrogees, documents, indisponibles = registre.rechercher("", "analyse", 6)
    assert [d["identifiant"] for d in documents] == ["ia0", "ga0", "hal0", "ia1", "ga1", "hal1"]
    assert [d["source"] for d in documents[:3]] == ["Internet Archive", "Gallica", "HAL"]
    assert indisponibles == [] and interrogees == "Internet Archive, Gallica, HAL"


def test_une_source_vide_laisse_la_place_aux_autres(monkeypatch):
    sources_factices(monkeypatch, internet_archive=[doc("ia", i) for i in range(5)], gallica=[], hal=[doc("hal", 0)])
    _, documents, _ = registre.rechercher("", "analyse", 4)
    assert [d["identifiant"] for d in documents] == ["ia0", "hal0", "ia1", "ia2"]


def test_une_source_en_panne_ne_bloque_pas_les_autres(monkeypatch):
    sources_factices(monkeypatch, internet_archive=ErreurRechercheArchive("panne"),
                     gallica=RuntimeError("format inattendu"), hal=[doc("hal", 0)])
    interrogees, documents, indisponibles = registre.rechercher("", "analyse", 6)
    assert [d["identifiant"] for d in documents] == ["hal0"]
    assert indisponibles == ["Internet Archive", "Gallica"] and interrogees == "HAL"


def test_toutes_les_sources_en_panne(monkeypatch):
    sources_factices(monkeypatch, internet_archive=ErreurRechercheArchive("a"),
                     gallica=ErreurRechercheSource("b"), hal=ErreurRechercheSource("c"))
    with pytest.raises(registre.ToutesSourcesIndisponibles):
        registre.rechercher("", "analyse", 6)


def test_doublons_d_adresse_ecartes(monkeypatch):
    commun_doc = doc("ia", 0)
    sources_factices(monkeypatch, internet_archive=[commun_doc], gallica=[commun_doc], hal=[])
    _, documents, _ = registre.rechercher("", "analyse", 6)
    assert len(documents) == 1


def test_source_nommee_cherche_cette_source_seule(monkeypatch):
    sources_factices(monkeypatch, internet_archive=[doc("ia", 0)], gallica=[doc("ga", 0)], hal=[doc("hal", 0)])
    for demande, attendu in [("gallica", "Gallica"), ("BnF", "Gallica"), ("Archive.org", "Internet Archive"),
                             ("archives ouvertes", "HAL"), ("  HAL ", "HAL")]:
        nom, documents, indisponibles = registre.rechercher(demande, "analyse", 6)
        assert nom == attendu and indisponibles == [] and {d["source"] for d in documents} == {attendu}, demande


def test_source_inconnue_jamais_de_repli_silencieux(monkeypatch):
    sources_factices(monkeypatch, internet_archive=[doc("ia", 0)], gallica=[], hal=[])
    with pytest.raises(registre.SourceInconnue) as e:
        registre.rechercher("persee", "analyse", 6)
    assert "Internet Archive" in str(e.value) and "Gallica" in str(e.value) and "HAL" in str(e.value)


def test_source_nommee_en_panne_leve_son_erreur(monkeypatch):
    sources_factices(monkeypatch, gallica=ErreurRechercheSource("panne"))
    with pytest.raises(ErreurRechercheSource):
        registre.rechercher("gallica", "analyse", 6)


def test_mode_une_source_utilise_seulement_la_source_par_defaut(monkeypatch):
    monkeypatch.setenv("RECHERCHE_DOCUMENTS_MODE", "une_source")
    sources_factices(monkeypatch, internet_archive=[doc("ia", 0)], gallica=[doc("ga", 0)], hal=[doc("hal", 0)])
    nom, documents, _ = registre.rechercher("", "analyse", 6)
    assert nom == "Internet Archive" and [d["identifiant"] for d in documents] == ["ia0"]


# --- Outil ---

def test_outil_resultat_json_et_sources_en_panne(monkeypatch):
    sources_factices(monkeypatch, internet_archive=[doc("ia", 0)], gallica=ErreurRechercheSource("x"), hal=[])
    sortie = json.loads(outil.rechercher_document_externe("analyse"))
    assert list(sortie) == ["documents", "sources_indisponibles"] and sortie["sources_indisponibles"] == ["Gallica"]


def test_outil_messages(monkeypatch):
    sources_factices(monkeypatch, internet_archive=[], gallica=[], hal=[])
    assert outil.rechercher_document_externe("analyse") == "Aucun document trouvé sur Internet Archive, Gallica, HAL pour cette recherche."
    sources_factices(monkeypatch, internet_archive=[], gallica=ErreurRechercheSource("x"), hal=ErreurRechercheSource("y"))
    assert outil.rechercher_document_externe("analyse").endswith("Attention, Gallica et HAL n'ont pas répondu.")
    sources_factices(monkeypatch, internet_archive=ErreurRechercheArchive("a"), gallica=ErreurRechercheSource("b"), hal=ErreurRechercheSource("c"))
    assert outil.rechercher_document_externe("analyse").startswith("Erreur : aucune bibliothèque ne répond")
    assert outil.rechercher_document_externe("analyse", source="persee").startswith("Erreur : Source inconnue")
    sources_factices(monkeypatch, hal=ErreurRechercheSource("z"))
    assert outil.rechercher_document_externe("analyse", source="hal") == "Erreur : HAL ne répond pas pour le moment, réessaie dans un instant."


def test_textes_affiches_sans_tirets_doubles(monkeypatch):
    sources_factices(monkeypatch, internet_archive=ErreurRechercheArchive("a"), gallica=ErreurRechercheSource("b"), hal=ErreurRechercheSource("c"))
    for texte in (outil.rechercher_document_externe("x"), outil.rechercher_document_externe("x", source="persee")):
        assert "--" not in texte and "—" not in texte


def test_les_deux_outils_sont_enregistres_et_le_texte_du_modele_est_a_jour():
    from core.outils_generation_commun import mcp_generation
    import core.serveur_mcp_generation  # noqa: F401
    noms = [t.name for t in asyncio.run(mcp_generation.list_tools())]
    assert "rechercher_document_externe" in noms and "lire_document_internet_archive" in noms
    assert len(noms) == len(set(noms))
    texte = outil.rechercher_document_externe.__doc__
    for mot in ("Internet Archive", "Gallica", "HAL", "TOUTES", "lire_document_internet_archive"):
        assert mot in texte, mot
