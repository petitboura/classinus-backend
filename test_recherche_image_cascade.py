"""
Tests de la cascade de recherche d'images (07/11/2026). Aucun accès réseau :
les réponses ci-dessous sont des EXEMPLES FABRIQUÉS d'après la documentation
des API (Wikimedia Commons, Openverse, Serper, SerpApi), pas de vraies
réponses. Ils vérifient la logique (ordre, secours, cache, filtres), pas
l'accord avec les vrais services : à confirmer en production.
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
]


@pytest.fixture(autouse=True)
def propre(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
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
    """routes : {fragment d'adresse: Reponse ou Exception}. Renvoie la liste des adresses appelées."""
    appels = []

    def faux(url, **kwargs):
        appels.append(url)
        for fragment, retour in routes.items():
            if fragment in url:
                if isinstance(retour, Exception):
                    raise retour
                return retour
        raise AssertionError(f"appel réseau inattendu : {url}")

    monkeypatch.setattr(ri.requests, "get", faux)
    monkeypatch.setattr(ri.requests, "post", faux)
    return appels


WIKI = Reponse(
    {
        "query": {
            "pages": {
                "11": {
                    "title": "File:Plan.svg",
                    "index": 1,
                    "imageinfo": [{"mime": "image/svg+xml", "url": "https://upload.wikimedia.org/plan.svg"}],
                },
                "12": {
                    "title": "File:Tour_Eiffel_nuit.jpg",
                    "index": 3,
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "url": "https://upload.wikimedia.org/a.jpg",
                            "thumburl": "https://upload.wikimedia.org/thumb/a.jpg",
                            "extmetadata": {"Artist": {"value": '<a href="x">Jean &amp; Paul</a>'}},
                        }
                    ],
                },
                "13": {
                    "title": "File:Tour Eiffel jour.png",
                    "index": 2,
                    "imageinfo": [{"mime": "image/png", "url": "https://upload.wikimedia.org/b.png"}],
                },
            }
        }
    }
)

OPENVERSE = Reponse(
    {
        "results": [
            {"title": "Chat", "url": "http://exemple.org/chat.jpg", "thumbnail": "https://api.openverse.org/t/1", "creator": "Léa"},
            {"title": "Sans adresse sûre", "url": "http://exemple.org/x.jpg", "thumbnail": "http://api.openverse.org/t/2"},
        ]
    }
)

SERPER = Reponse(
    {
        "images": [
            {"title": "Pont", "imageUrl": "https://site.fr/pont.jpg", "thumbnailUrl": "https://encrypted.gstatic.com/p", "source": "site.fr"},
            {"title": "Pont http", "imageUrl": "http://site.fr/pont2.jpg", "thumbnailUrl": "https://encrypted.gstatic.com/q", "domain": "site.fr"},
            {"title": "Rien de sûr", "imageUrl": "http://site.fr/3.jpg", "thumbnailUrl": "http://site.fr/3t.jpg"},
        ]
    }
)

SERPAPI = Reponse(
    {"images_results": [{"title": "Fleur", "original": "https://f.org/o.jpg", "thumbnail": "https://f.org/t.jpg", "source": "f.org"}]}
)

PIXABAY = Reponse({"hits": [{"tags": "arbre", "largeImageURL": "https://p/l.jpg", "webformatURL": "https://p/w.jpg", "user": "Ana"}]})


def test_ordre_par_defaut_wikimedia_premier_et_arret(monkeypatch):
    appels = brancher(monkeypatch, {"commons.wikimedia.org": WIKI})
    res = ri.rechercher_images("tour eiffel", 6)
    assert len(appels) == 1
    # trié par index, svg écarté, titre nettoyé, artiste sans balises ni entités
    assert [r["titre"] for r in res] == ["Tour Eiffel jour", "Tour Eiffel nuit"]
    assert res[1]["url"] == "https://upload.wikimedia.org/thumb/a.jpg"
    assert res[1]["credit"] == "Jean & Paul (Wikimedia Commons)"
    assert res[0]["credit"] == "Wikimedia Commons"


def test_secours_sur_openverse_si_wikimedia_echoue(monkeypatch):
    appels = brancher(monkeypatch, {"commons.wikimedia.org": RuntimeError("panne"), "openverse.org": OPENVERSE})
    res = ri.rechercher_images("chat")
    assert len(appels) == 2
    # le 2e résultat fabriqué n'a aucune adresse https : écarté
    assert len(res) == 1
    # original en http : repli sur la miniature https
    assert res[0]["url"] == "https://api.openverse.org/t/1"
    assert res[0]["credit"] == "Léa (Openverse)"


def test_openverse_ecarte_ce_qui_n_a_aucune_adresse_https(monkeypatch):
    brancher(monkeypatch, {"commons.wikimedia.org": Reponse({}), "openverse.org": OPENVERSE})
    res = ri.rechercher_images("chat")
    assert [r["titre"] for r in res] == ["Chat"]


def test_serper_saute_sans_cle_puis_utilise_la_cle(monkeypatch):
    appels = brancher(monkeypatch, {"commons.wikimedia.org": Reponse({}), "openverse.org": Reponse({}), "serper.dev": SERPER})
    assert ri.rechercher_images("pont") == []  # pas de clé : serper sauté, rien d'autre ne répond
    assert not any("serper.dev" in a for a in appels)
    monkeypatch.setenv("SERPER_API_KEY", "cle")
    ri.vider_cache_images()
    res = ri.rechercher_images("pont")
    assert [r["titre"] for r in res] == ["Pont", "Pont http"]
    assert res[0]["credit"] == "site.fr"
    assert res[1]["url"] == "https://encrypted.gstatic.com/q"  # original http : repli sur la miniature https
    assert res[1]["credit"] == "site.fr"


def test_serpapi_en_secours_de_serper(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "a")
    monkeypatch.setenv("SERPAPI_API_KEY", "b")
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "serper,serpapi")
    appels = brancher(monkeypatch, {"serper.dev": Reponse({}, 429), "serpapi.com": SERPAPI})
    res = ri.rechercher_images("fleur")
    assert len(appels) == 2
    assert res == [{"titre": "Fleur", "url": "https://f.org/o.jpg", "miniature": "https://f.org/t.jpg", "credit": "f.org"}]


def test_ordre_configurable_et_noms_inconnus_ignores(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", " Pixabay , inconnu, pixabay ")
    appels = brancher(monkeypatch, {"pixabay.com": PIXABAY})
    res = ri.rechercher_images("arbre")
    assert appels == ["https://pixabay.com/api/"]
    assert res[0]["credit"] == "Ana (Pixabay)"


def test_cache_evite_le_reseau_et_protege_les_resultats(monkeypatch):
    appels = brancher(monkeypatch, {"commons.wikimedia.org": WIKI})
    premier = ri.rechercher_images("Tour  Eiffel", 6)
    premier[0]["titre"] = "modifié par l'appelant"
    second = ri.rechercher_images("tour eiffel", 6)  # même requête normalisée
    assert len(appels) == 1
    assert second[0]["titre"] == "Tour Eiffel jour"
    ri.rechercher_images("tour eiffel", 3)  # autre nombre : autre entrée
    assert len(appels) == 2


def test_jamais_d_erreur_ni_de_vide_en_cache(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    appels = brancher(monkeypatch, {"commons.wikimedia.org": Reponse({})})
    assert ri.rechercher_images("rien") == []
    assert ri.rechercher_images("rien") == []
    assert len(appels) == 2
    brancher(monkeypatch, {"commons.wikimedia.org": RuntimeError("panne")})
    assert ri.rechercher_images("panne") == []


def test_cache_expire_et_desactivable(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    appels = brancher(monkeypatch, {"commons.wikimedia.org": WIKI})
    horloge = {"t": 1000.0}
    monkeypatch.setattr(ri.time, "monotonic", lambda: horloge["t"])
    monkeypatch.setenv("RECHERCHE_IMAGE_CACHE_SECONDES", "60")
    ri.rechercher_images("a")
    horloge["t"] += 59
    ri.rechercher_images("a")
    assert len(appels) == 1
    horloge["t"] += 2
    ri.rechercher_images("a")
    assert len(appels) == 2
    monkeypatch.setenv("RECHERCHE_IMAGE_CACHE_SECONDES", "0")
    ri.vider_cache_images()
    ri.rechercher_images("b")
    ri.rechercher_images("b")
    assert len(appels) == 4


def test_cache_borne_en_taille(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "wikimedia")
    monkeypatch.setenv("RECHERCHE_IMAGE_CACHE_MAX", "2")
    appels = brancher(monkeypatch, {"commons.wikimedia.org": WIKI})
    for q in ("a", "b", "c"):
        ri.rechercher_images(q)
    ri.rechercher_images("c")  # encore en cache
    assert len(appels) == 3
    ri.rechercher_images("a")  # la plus ancienne a été retirée
    assert len(appels) == 4


def test_aucun_fournisseur_disponible(monkeypatch):
    monkeypatch.setenv("RECHERCHE_IMAGE_ORDRE", "serper,pexels")
    brancher(monkeypatch, {})
    assert ri.rechercher_images("x") == []
