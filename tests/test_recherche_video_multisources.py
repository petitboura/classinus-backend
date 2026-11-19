"""Tests unitaires hors réseau de la recherche vidéo multi-sources."""

from core import recherche_video as rv


def test_normaliser_video_conserve_la_plateforme_et_la_source():
    resultat = rv._normaliser_video(
        {
            "title": "Documentaire",
            "link": "https://vimeo.com/123456",
            "thumbnail": "https://cdn.example/thumb.jpg",
            "source": "Vimeo",
            "channel": "Archives",
            "length": "12:30",
        },
        "documentaire",
        "SearchApi",
    )

    assert resultat["titre"] == "Documentaire"
    assert resultat["url"] == "https://vimeo.com/123456"
    assert resultat["source"] == "Vimeo"
    assert resultat["source_url"] == "https://vimeo.com"
    assert resultat["fournisseur_recherche"] == "SearchApi"
    assert resultat["duree"] == "12:30"


def test_normaliser_video_rejette_une_url_absente_ou_invalide():
    assert rv._normaliser_video({"title": "Sans lien"}, "test", "Serper") is None
    assert rv._normaliser_video(
        {"title": "Lien invalide", "link": "javascript:alert(1)"},
        "test",
        "Serper",
    ) is None


def test_recherche_video_complete_youtube_avec_serper(monkeypatch):
    rv._memoire.clear()
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-youtube")
    monkeypatch.setenv("SERPER_API_KEY", "test-serper")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SEARCHAPI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(rv, "_pause_youtube_jusqu_a", 0.0)

    youtube = [
        {"titre": f"YouTube {i}", "url": f"https://www.youtube.com/watch?v={i:011d}",
         "miniature": None, "chaine": "Chaîne", "duree": None, "id_video": str(i)}
        for i in range(20)
    ]
    serper = [
        {"titre": f"Vimeo {i}", "url": f"https://vimeo.com/{i}",
         "miniature": None, "chaine": None, "duree": None, "id_video": None}
        for i in range(10)
    ]
    monkeypatch.setattr(rv, "_chercher_via_youtube", lambda *args: youtube)
    monkeypatch.setattr(rv, "_chercher_via_serper_video", lambda *args: serper)

    resultats = rv.rechercher_videos("documentaire", nombre=30)

    assert len(resultats) == 30
    assert resultats[0]["source"] == "YouTube"
    assert any("vimeo.com" in video["url"] for video in resultats)


def test_recherche_video_borne_le_nombre_et_supporte_la_page(monkeypatch):
    rv._memoire.clear()
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SEARCHAPI_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    assert rv.rechercher_videos("test", nombre=500, page=2) == []
    assert rv._cle_memoire("test", 50, 2) != rv._cle_memoire("test", 50, 1)
