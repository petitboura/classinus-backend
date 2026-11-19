"""
Tests hors réseau de la recherche multi-sources, paginée et dédupliquée.
Les réponses sont des jeux de données fictifs : aucun quota API n'est consommé.
"""
import pytest

import core.recherche_image as ri


VARIABLES = [
    "RECHERCHE_IMAGE_ORDRE",
    "RECHERCHE_IMAGE_CACHE_SECONDES",
    "RECHERCHE_IMAGE_CACHE_MAX",
    "SERPER_API_KEY",
    "SERPAPI_API_KEY",
    "PIXABAY_API_KEY",
    "PEXELS_API_KEY",
    "FLICKR_API_KEY",
    "SMITHSONIAN_API_KEY",
    "EUROPEANA_API_KEY",
]


@pytest.fixture(autouse=True)
def propre(monkeypatch):
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    ri.vider_cache_images()
    yield
    ri.vider_cache_images()


class Reponse:
    def __init__(self, corps, statut=200):
        self._corps = corps
        self.status_code = statut

    def json(self):
        return self._corps

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def brancher(monkeypatch, routes):
    """routes : fragments d'URL vers réponse ou exception. Renvoie les appels."""
    appels = []

    def faux(url, **kwargs):
        appels.append((url, kwargs))
        for fragment, retour in routes.items():
            if fragment in url:
                if isinstance(retour, Exception):
                    raise retour
                return retour
        raise AssertionError(f"appel réseau inattendu : {url}")

    monkeypatch.setattr(ri.requests, "get", faux)
    monkeypatch.setattr(ri.requests, "post", faux)
    return appels


def test_interroge_les_sources_en_parallele_et_fusionne(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia,openverse,loc")
    wiki = Reponse({
        "query": {"pages": {"1": {
            "title": "File:Grand Mosque.jpg",
            "index": 1,
            "canonicalurl": "https://commons.wikimedia.org/wiki/File:Grand_Mosque.jpg",
            "imageinfo": [{
                "mime": "image/jpeg",
                "url": "https://upload.wikimedia.org/large.jpg",
                "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                "extmetadata": {"Artist": {"value": "Photographe"}},
            }],
        }}}
    })
    openverse = Reponse({"results": [{
        "title": "Place du marché",
        "url": "https://images.example/market.jpg",
        "thumbnail": "https://images.example/market-small.jpg",
        "creator": "Awa",
        "foreign_landing_url": "https://photo.example/market",
    }]})
    loc = Reponse({"results": [{
        "title": "Photographie d'archive",
        "image_url": ["https://tile.loc.gov/archive.jpg"],
        "thumbnail_url": "https://tile.loc.gov/archive-small.jpg",
        "url": "https://www.loc.gov/item/123/",
    }]})
    appels = brancher(monkeypatch, {
        "commons.wikimedia.org": wiki,
        "api.openverse.org": openverse,
        "www.loc.gov": loc,
    })

    resultats = ri.rechercher_images("marché africain", nombre=9)

    assert len(appels) == 3
    assert {url.split("/")[2] for url, _ in appels} == {
        "commons.wikimedia.org", "api.openverse.org", "www.loc.gov"
    }
    assert len(resultats) == 3
    assert resultats[0]["source_url"] == "https://commons.wikimedia.org/wiki/File:Grand_Mosque.jpg"
    assert resultats[1]["source_url"] == "https://photo.example/market"
    assert resultats[2]["source_url"] == "https://www.loc.gov/item/123/"
    assert resultats[0]["source_name"] == "commons.wikimedia.org"


def test_dedoublonne_les_meme_images_entre_sources(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia,openverse")
    meme_url = "https://cdn.example/image.jpg"
    wiki = Reponse({"query": {"pages": {"1": {
        "title": "File:Image.jpg",
        "index": 1,
        "imageinfo": [{"mime": "image/jpeg", "url": meme_url, "thumburl": meme_url}],
    }}}})
    openverse = Reponse({"results": [{
        "title": "Même image",
        "url": meme_url,
        "thumbnail": meme_url,
        "foreign_landing_url": "https://source.example/image",
    }]})
    brancher(monkeypatch, {"commons.wikimedia.org": wiki, "api.openverse.org": openverse})

    resultats = ri.rechercher_images("image", nombre=20)

    assert len(resultats) == 1
    assert resultats[0]["url"] == meme_url


def test_flickr_utilise_la_page_demandee_et_donne_le_lien_de_l_image(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "flickr")
    monkeypatch.setenv("FLICKR_API_KEY", "cle-test")
    appels = brancher(monkeypatch, {
        "www.flickr.com": Reponse({"photos": {"photo": [{
            "id": "123456",
            "owner": "compte",
            "owner_name": "Photographe",
            "title": "Dakar",
            "url_o": "https://live.staticflickr.com/original.jpg",
            "url_m": "https://live.staticflickr.com/medium.jpg",
        }]}})
    })

    resultats = ri.rechercher_images("Dakar", nombre=20, page=2)

    assert len(appels) == 1
    assert appels[0][1]["params"]["page"] == 2
    assert resultats[0]["source_url"] == "https://www.flickr.com/photos/compte/123456"
    assert resultats[0]["source_name"] == "flickr.com"


def test_une_source_en_erreur_ne_bloque_pas_les_autres(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia,openverse")
    openverse = Reponse({"results": [{
        "title": "Image disponible",
        "url": "https://images.example/ok.jpg",
        "thumbnail": "https://images.example/thumb.jpg",
        "foreign_landing_url": "https://site.example/page",
    }]})
    brancher(monkeypatch, {
        "commons.wikimedia.org": RuntimeError("panne temporaire"),
        "api.openverse.org": openverse,
    })

    resultats = ri.rechercher_images("test", nombre=10)

    assert len(resultats) == 1
    assert resultats[0]["source_url"] == "https://site.example/page"


def test_cache_distinct_pour_chaque_page(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    appels = []

    def faux(url, **kwargs):
        params = kwargs["params"]
        appels.append(params["gsroffset"])
        decalage = params["gsroffset"]
        return Reponse({"query": {"pages": {str(decalage): {
            "title": f"File:Image-{decalage}.jpg",
            "index": 1,
            "imageinfo": [{
                "mime": "image/jpeg",
                "url": f"https://upload.wikimedia.org/{decalage}.jpg",
                "thumburl": f"https://upload.wikimedia.org/{decalage}-small.jpg",
            }],
        }}}})

    monkeypatch.setattr(ri.requests, "get", faux)
    premiere = ri.rechercher_images("mali", nombre=10, page=1)
    deuxieme = ri.rechercher_images("mali", nombre=10, page=2)
    encore_premiere = ri.rechercher_images("mali", nombre=10, page=1)

    assert len(appels) == 2
    assert premiere[0]["url"] != deuxieme[0]["url"]
    assert encore_premiere == premiere


def test_une_source_avec_cle_absente_est_ignoree(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "flickr,openverse")
    appels = brancher(monkeypatch, {
        "api.openverse.org": Reponse({"results": []}),
    })

    assert ri.rechercher_images("sans clé") == []
    assert len(appels) == 1
    assert "api.openverse.org" in appels[0][0]


def test_limites_nombre_et_page(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    appels = brancher(monkeypatch, {"commons.wikimedia.org": Reponse({})})

    ri.rechercher_images("requête", nombre=500, page=0)

    assert appels[0][1]["params"]["gsrlimit"] == 50
    assert appels[0][1]["params"]["gsroffset"] == 0


def test_cache_epargne_les_requetes_et_peut_etre_desactive(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    appels = brancher(monkeypatch, {"commons.wikimedia.org": Reponse({"query": {"pages": {"1": {
        "title": "File:Photo.jpg",
        "index": 1,
        "imageinfo": [{"mime": "image/jpeg", "url": "https://upload.wikimedia.org/photo.jpg"}],
    }}}})})

    ri.rechercher_images("photo")
    ri.rechercher_images("photo")
    assert len(appels) == 1

    monkeypatch.setenv("RECHERCHE_IMAGE_CACHE_SECONDES", "0")
    ri.vider_cache_images()
    ri.rechercher_images("autre")
    ri.rechercher_images("autre")
    assert len(appels) == 3
