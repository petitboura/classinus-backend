"""
Recherche d'images multi-sources, parallèle et paginée.

Chaque source renvoie l'adresse de la page qui héberge réellement l'image
(source_url/source_name), séparée du crédit de l'auteur. Les sources
indépendantes sont interrogées en parallèle, puis les résultats sont fusionnés,
dédupliqués et répartis entre les sources pour éviter qu'une seule domine.

Les erreurs et quotas d'une source n'empêchent jamais les autres de répondre.
Le cache conserve chaque page séparément afin de limiter les appels API.
"""

import html
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit, urlunsplit

import requests

_URL_PIXABAY = "https://pixabay.com/api/"
_URL_PEXELS = "https://api.pexels.com/v1/search"
_URL_WIKIMEDIA = "https://commons.wikimedia.org/w/api.php"
_URL_OPENVERSE = "https://api.openverse.org/v1/images/"
_URL_SERPER = "https://google.serper.dev/images"
_URL_SERPAPI = "https://serpapi.com/search.json"
_URL_SEARCHAPI = "https://www.searchapi.io/api/v1/search"
_URL_FLICKR = "https://www.flickr.com/services/rest/"
_URL_SMITHSONIAN = "https://api.si.edu/openaccess/api/v1.0/search"
_URL_EUROPEANA = "https://api.europeana.eu/record/v2/search.json"
_URL_NASA = "https://images-api.nasa.gov/search"
_URL_LOC = "https://www.loc.gov/photos/"

_AGENT_UTILISATEUR = "Classinus/1.0 (https://classinus.com)"
_DELAI_NOUVEAUX_FOURNISSEURS = 12
_DELAI_BANQUES = 15
_NOMBRE_DEFAUT = 40
_NOMBRE_MAX_PAGE = 100
_MAX_WORKERS = 8

_ORDRE_PAR_DEFAUT = (
    "wikimedia,openverse,loc,flickr,smithsonian,europeana,nasa,"
    "serper,serpapi,searchapi,pixabay,pexels"
)
_CACHE_SECONDES_PAR_DEFAUT = 259200
_CACHE_MAX_PAR_DEFAUT = 500
_MIMES_AFFICHABLES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _get_secret(cle):
    return os.environ.get(cle)


def _lire_entier(cle: str, defaut: int) -> int:
    brut = _get_secret(cle)
    if brut is None or not str(brut).strip():
        return defaut
    try:
        return max(0, int(str(brut).strip()))
    except ValueError:
        logging.warning("%s invalide (%r), valeur par défaut %s utilisée.", cle, brut, defaut)
        return defaut


def _https(adresse):
    """Accepte uniquement une URL d'image HTTPS."""
    if isinstance(adresse, str) and adresse.strip().lower().startswith("https://"):
        return adresse.strip()
    return None


def _url_source(adresse, domaine=None):
    """Normalise une page source HTTP(S), sans fabriquer de domaine inconnu."""
    if isinstance(adresse, str) and adresse.strip():
        valeur = adresse.strip()
        if valeur.startswith("//"):
            valeur = "https:" + valeur
        elif valeur.startswith("http://"):
            valeur = "https://" + valeur[7:]
        try:
            parsed = urlsplit(valeur)
            if parsed.scheme == "https" and parsed.hostname:
                return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))
        except ValueError:
            pass
    if isinstance(domaine, str):
        hote = domaine.strip().lower().removeprefix("www.")
        if re.fullmatch(r"[a-z0-9.-]+", hote) and "." in hote and ".." not in hote:
            return "https://" + hote
    return None


def _texte_sans_html(texte) -> str:
    if not texte:
        return ""
    sans_balises = re.sub(r"<[^>]+>", " ", str(texte))
    return " ".join(html.unescape(sans_balises).split())


def _premiere_valeur(valeur):
    if isinstance(valeur, list):
        return valeur[0] if valeur else None
    return valeur


def _valeur_texte(valeur):
    if isinstance(valeur, dict):
        return valeur.get("content") or valeur.get("value") or valeur.get("label") or ""
    if isinstance(valeur, list):
        return _valeur_texte(valeur[0]) if valeur else ""
    return str(valeur or "")


def _resultat(titre, url, miniature=None, credit=None, source_url=None, source_domain=None):
    image = _https(url) or _https(miniature)
    vignette = _https(miniature) or image
    if not image or not vignette:
        return None
    page_source = _url_source(source_url, source_domain)
    domaine = None
    if page_source:
        try:
            domaine = (urlsplit(page_source).hostname or "").lower().removeprefix("www.")
        except ValueError:
            page_source = None
    resultat = {
        "titre": _texte_sans_html(titre)[:240] or "Image",
        "url": image,
        "miniature": vignette,
        "credit": _texte_sans_html(credit)[:160] if credit else "",
    }
    if page_source:
        resultat["source_url"] = page_source
        resultat["source_name"] = domaine or ""
        resultat["source_domain"] = domaine or ""
    return resultat


def _chercher_via_wikimedia(requete: str, nombre: int, _cle=None, page: int = 1) -> list[dict]:
    par_page = max(10, min(nombre * 2, 50))
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": requete,
        "gsrlimit": par_page,
        "gsroffset": (page - 1) * par_page,
        "prop": "imageinfo|info",
        "inprop": "url",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 960,
        "iiextmetadatafilter": "Artist",
    }
    reponse = requests.get(
        _URL_WIKIMEDIA,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params=params,
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    pages = (reponse.json().get("query") or {}).get("pages") or {}
    sortie = []
    for page_data in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        infos = (page_data.get("imageinfo") or [{}])[0]
        if infos.get("mime") not in _MIMES_AFFICHABLES:
            continue
        adresse = _https(infos.get("thumburl")) or _https(infos.get("url"))
        if not adresse:
            continue
        nom_fichier = page_data.get("title") or ""
        titre = re.sub(r"^[^:]+:", "", nom_fichier, count=1)
        titre = titre.rsplit(".", 1)[0].replace("_", " ").strip() or requete
        artiste = _texte_sans_html(((infos.get("extmetadata") or {}).get("Artist") or {}).get("value"))
        source_url = page_data.get("canonicalurl") or (
            "https://commons.wikimedia.org/wiki/" + quote(nom_fichier.replace(" ", "_"), safe=":")
        )
        resultat = _resultat(titre, adresse, adresse, artiste, source_url)
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_openverse(requete: str, nombre: int, _cle=None, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_OPENVERSE,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={"q": requete, "page_size": max(1, min(nombre, 20)), "page": page},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("results", []):
        resultat = _resultat(
            item.get("title") or requete,
            item.get("url"),
            item.get("thumbnail"),
            item.get("creator"),
            item.get("foreign_landing_url") or item.get("detail_url"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_loc(requete: str, nombre: int, _cle=None, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_LOC,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={"fo": "json", "q": requete, "c": min(nombre, 100), "sp": page},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("results", []):
        images = item.get("image_url") or []
        if isinstance(images, str):
            images = [images]
        image = next((_https(u) for u in reversed(images) if _https(u)), None)
        image = image or _https(item.get("image"))
        miniature = _https(item.get("thumbnail_url")) or image
        resultat = _resultat(
            item.get("title") or requete,
            image,
            miniature,
            item.get("contributor") or item.get("creator"),
            item.get("url") or item.get("id"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_flickr(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_FLICKR,
        params={
            "method": "flickr.photos.search",
            "api_key": cle,
            "text": requete,
            "format": "json",
            "nojsoncallback": 1,
            "per_page": min(nombre, 500),
            "page": page,
            "media": "photos",
            "content_type": 1,
            "safe_search": 1,
            "extras": "url_m,url_l,url_c,url_o,owner_name,description",
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    photos = (reponse.json().get("photos") or {}).get("photo") or []
    sortie = []
    for photo in photos:
        identifiant = photo.get("id")
        proprietaire = photo.get("owner")
        source_url = (
            f"https://www.flickr.com/photos/{quote(str(proprietaire), safe='')}/{quote(str(identifiant), safe='')}"
            if identifiant and proprietaire else None
        )
        resultat = _resultat(
            photo.get("title") or requete,
            photo.get("url_o") or photo.get("url_l") or photo.get("url_c") or photo.get("url_m"),
            photo.get("url_m") or photo.get("url_c") or photo.get("url_l"),
            photo.get("owner_name"),
            source_url,
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_smithsonian(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_SMITHSONIAN,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={
            "q": requete,
            "api_key": cle,
            "rows": min(nombre, 100),
            "start": (page - 1) * min(nombre, 100),
            "sort": "relevancy",
            "type": "edanmdm",
            "row_group": "objects",
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    rows = (reponse.json().get("response") or {}).get("rows") or []
    sortie = []
    for row in rows:
        contenu = row.get("content") or {}
        descriptif = contenu.get("descriptiveNonRepeating") or {}
        medias = (descriptif.get("online_media") or {}).get("media") or []
        if isinstance(medias, dict):
            medias = [medias]
        titre = _valeur_texte(descriptif.get("title")) or row.get("title") or requete
        source_url = descriptif.get("guid") or row.get("url")
        if not source_url and row.get("id"):
            source_url = "https://www.si.edu/object/" + quote(str(row["id"]), safe="")
        for media in medias:
            if not isinstance(media, dict):
                continue
            url_image = media.get("content")
            miniature = media.get("thumbnail") or url_image
            resultat = _resultat(
                titre,
                url_image,
                miniature,
                media.get("credit") or media.get("source"),
                source_url,
            )
            if resultat:
                sortie.append(resultat)
                break
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_europeana(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    taille = min(nombre, 100)
    reponse = requests.get(
        _URL_EUROPEANA,
        headers={"User-Agent": _AGENT_UTILISATEUR, "X-Api-Key": cle},
        params={
            "query": requete,
            "rows": taille,
            "start": (page - 1) * taille + 1,
            "media": "true",
            "thumbnail": "true",
            "profile": "rich",
            "qf": "TYPE:IMAGE",
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("items", []):
        preview = _premiere_valeur(item.get("edmPreview"))
        original = _premiere_valeur(item.get("edmIsShownBy")) or preview
        source_url = _premiere_valeur(item.get("edmIsShownAt")) or item.get("guid")
        titre = _valeur_texte(item.get("title")) or requete
        resultat = _resultat(titre, original, preview, None, source_url)
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_nasa(requete: str, nombre: int, _cle=None, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_NASA,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={"q": requete, "media_type": "image", "page": page},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    elements = ((reponse.json().get("collection") or {}).get("items")) or []
    sortie = []
    for item in elements:
        donnees = item.get("data") or [{}]
        meta = donnees[0] if donnees else {}
        liens = item.get("links") or []
        preview = next((_https(l.get("href")) for l in liens if l.get("render") == "image" and _https(l.get("href"))), None)
        if not preview:
            preview = next((_https(l.get("href")) for l in liens if _https(l.get("href"))), None)
        nasa_id = meta.get("nasa_id")
        source_url = "https://images.nasa.gov/details/" + quote(str(nasa_id), safe="") if nasa_id else None
        resultat = _resultat(meta.get("title") or requete, preview, preview, None, source_url)
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_pixabay(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_PIXABAY,
        params={
            "key": cle,
            "q": requete,
            "per_page": min(nombre, 200),
            "page": page,
            "safesearch": "true",
        },
        timeout=_DELAI_BANQUES,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("hits", []):
        resultat = _resultat(
            item.get("tags") or requete,
            item.get("largeImageURL") or item.get("webformatURL"),
            item.get("webformatURL") or item.get("previewURL"),
            item.get("user"),
            item.get("pageURL"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_pexels(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_PEXELS,
        headers={"Authorization": cle},
        params={"query": requete, "per_page": min(nombre, 80), "page": page},
        timeout=_DELAI_BANQUES,
    )
    reponse.raise_for_status()
    sortie = []
    for photo in reponse.json().get("photos", []):
        src = photo.get("src") or {}
        resultat = _resultat(
            photo.get("alt") or requete,
            src.get("large") or src.get("original") or src.get("medium"),
            src.get("medium") or src.get("small") or src.get("large"),
            photo.get("photographer"),
            photo.get("url"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_serper(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.post(
        _URL_SERPER,
        headers={"X-API-KEY": cle, "Content-Type": "application/json"},
        json={"q": requete, "page": page},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("images", []):
        resultat = _resultat(
            item.get("title") or requete,
            item.get("imageUrl"),
            item.get("thumbnailUrl"),
            None,
            item.get("link"),
            item.get("domain") or item.get("source"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_serpapi(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    reponse = requests.get(
        _URL_SERPAPI,
        params={
            "engine": "google_images",
            "q": requete,
            "api_key": cle,
            "safe": "active",
            "ijn": page - 1,
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("images_results", []):
        resultat = _resultat(
            item.get("title") or requete,
            item.get("original"),
            item.get("thumbnail"),
            None,
            item.get("link"),
            item.get("source"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_searchapi(requete: str, nombre: int, cle: str, page: int = 1) -> list[dict]:
    """Google Images via SearchApi.io : source.link = page réellement publiée."""
    reponse = requests.get(
        _URL_SEARCHAPI,
        headers={
            "Authorization": f"Bearer {cle}",
            "User-Agent": _AGENT_UTILISATEUR,
        },
        params={
            "engine": "google_images",
            "q": requete,
            "page": page,
            "safe": "active",
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for item in reponse.json().get("images", []):
        source = item.get("source") or {}
        original = item.get("original") or {}
        resultat = _resultat(
            item.get("title") or requete,
            original.get("link"),
            item.get("thumbnail"),
            source.get("name"),
            source.get("link"),
        )
        if resultat:
            sortie.append(resultat)
        if len(sortie) >= nombre:
            break
    return sortie


# nom -> (fonction, variable d'environnement de la clé, ou None si sans clé)
_FOURNISSEURS = {
    "wikimedia": (_chercher_via_wikimedia, None),
    "openverse": (_chercher_via_openverse, None),
    "loc": (_chercher_via_loc, None),
    "flickr": (_chercher_via_flickr, "FLICKR_API_KEY"),
    "smithsonian": (_chercher_via_smithsonian, "SMITHSONIAN_API_KEY"),
    "europeana": (_chercher_via_europeana, "EUROPEANA_API_KEY"),
    "nasa": (_chercher_via_nasa, None),
    "serper": (_chercher_via_serper, "SERPER_API_KEY"),
    "serpapi": (_chercher_via_serpapi, "SERPAPI_API_KEY"),
    "searchapi": (_chercher_via_searchapi, "SEARCHAPI_API_KEY"),
    "pixabay": (_chercher_via_pixabay, "PIXABAY_API_KEY"),
    "pexels": (_chercher_via_pexels, "PEXELS_API_KEY"),
}


def _ordre_fournisseurs() -> list[str]:
    brut = _get_secret("RECHERCHE_IMAGE_ORDRE") or _ORDRE_PAR_DEFAUT
    ordre = []
    for nom in (element.strip().lower() for element in brut.split(",")):
        if not nom or nom in ordre:
            continue
        if nom not in _FOURNISSEURS:
            logging.warning("RECHERCHE_IMAGE_ORDRE : source inconnue %r, ignorée.", nom)
            continue
        ordre.append(nom)
    return ordre


_cache: dict = {}
_verrou_cache = threading.Lock()


def vider_cache_images() -> None:
    with _verrou_cache:
        _cache.clear()


def _cle_cache(requete: str, nombre: int, page: int, ordre: tuple) -> tuple:
    return (" ".join(requete.lower().split()), nombre, page, ordre)


def _lire_cache(cle: tuple):
    with _verrou_cache:
        trouve = _cache.get(cle)
        if trouve is None:
            return None
        expire, resultats = trouve
        if time.monotonic() >= expire:
            del _cache[cle]
            return None
        return [dict(resultat) for resultat in resultats]


def _ecrire_cache(cle: tuple, resultats: list[dict]) -> None:
    duree = _lire_entier("RECHERCHE_IMAGE_CACHE_SECONDES", _CACHE_SECONDES_PAR_DEFAUT)
    if duree <= 0 or not resultats:
        return
    maximum = max(1, _lire_entier("RECHERCHE_IMAGE_CACHE_MAX", _CACHE_MAX_PAR_DEFAUT))
    with _verrou_cache:
        _cache.pop(cle, None)
        while len(_cache) >= maximum:
            _cache.pop(next(iter(_cache)))
        _cache[cle] = (time.monotonic() + duree, [dict(resultat) for resultat in resultats])


def _cle_deduplication(adresse: str) -> str:
    try:
        parsed = urlsplit(adresse)
        return (parsed.hostname or "").lower() + parsed.path.rstrip("/")
    except ValueError:
        return adresse.strip().lower()


def rechercher_images(requete: str, nombre: int = _NOMBRE_DEFAUT, page: int = 1) -> list[dict]:
    """
    Recherche sur plusieurs sources en parallèle. nombre est limité à 100
    résultats par page ; page commence à 1. Les pages sont mises en cache
    séparément. La fonction renvoie les champs titre/url/miniature/credit et,
    lorsque disponible, source_url/source_name/source_domain.
    """
    if not isinstance(requete, str) or not requete.strip():
        return []
    try:
        nombre = max(1, min(int(nombre), _NOMBRE_MAX_PAGE))
        page = max(1, int(page))
    except (TypeError, ValueError):
        nombre, page = _NOMBRE_DEFAUT, 1

    ordre = tuple(_ordre_fournisseurs())
    cle_cache = _cle_cache(requete, nombre, page, ordre)
    en_cache = _lire_cache(cle_cache)
    if en_cache is not None:
        return en_cache

    disponibles = []
    for nom in ordre:
        fonction, variable_cle = _FOURNISSEURS[nom]
        cle = _get_secret(variable_cle) if variable_cle else None
        if variable_cle and not cle:
            logging.debug("Recherche d'image : %s absente, source %s sautée.", variable_cle, nom)
            continue
        disponibles.append((nom, fonction, cle))

    if not disponibles:
        logging.warning("Recherche d'image : aucune source disponible.")
        return []

    resultats_par_source = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(disponibles))) as pool:
        taches = {
            nom: pool.submit(fonction, requete, nombre, cle, page)
            for nom, fonction, cle in disponibles
        }
        # Lecture dans l'ordre configuré, même si les réponses arrivent dans un autre ordre.
        for nom, _fonction, _cle in disponibles:
            try:
                resultats_par_source[nom] = taches[nom].result()
            except Exception as erreur:
                logging.warning("Recherche d'image : source %s indisponible pour %r : %s", nom, requete, erreur)
                resultats_par_source[nom] = []

    # Fusion équilibrée : on prend un résultat par source à chaque tour, pour
    # ne pas laisser une source volumineuse monopoliser les 40 premiers items.
    fusion = []
    vus = set()
    for index in range(nombre):
        for nom, _fonction, _cle in disponibles:
            source = resultats_par_source.get(nom) or []
            if index >= len(source):
                continue
            resultat = source[index]
            adresse = resultat.get("url")
            cle = _cle_deduplication(adresse) if adresse else ""
            if not cle or cle in vus:
                continue
            vus.add(cle)
            fusion.append(dict(resultat))
            if len(fusion) >= nombre:
                break
        if len(fusion) >= nombre:
            break

    if fusion:
        _ecrire_cache(cle_cache, fusion)
    logging.info(
        "Recherche d'image %r : %s résultat(s), %s source(s) interrogée(s), page %s.",
        requete, len(fusion), len(disponibles), page
    )
    return fusion
