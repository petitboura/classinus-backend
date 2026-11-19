"""
Recherche de vidéos multi-sources pour Classinus.

Trois niveaux, essayés dans cet ordre, sans jamais faire échouer la
recherche pour l'étudiant :

1. Mémoire des recherches déjà faites : une même demande, déjà posée
   récemment, est servie sans rien consommer du quota de YouTube.
2. Service officiel de YouTube (YouTube Data API v3). Clé YOUTUBE_API_KEY,
   ou à défaut GOOGLE_API_KEY (déjà présente sur Railway) : elle fonctionne
   seulement si le service YouTube est activé dans le projet Google auquel
   elle appartient et qu'elle n'est pas limitée à un autre service. Si
   Google la refuse, on passe par Tavily sans insister (voir plus bas).
   Gratuit, mais plafonné à 10 000 points par jour pour tout le projet
   Google, soit environ 100 recherches (une recherche coûte 100 points,
   la lecture des durées 1 point). Google ne vend pas de quota
   supplémentaire, il faut en faire la demande.
3. Google Videos via Serper, SerpApi et SearchApi : complète les résultats
   YouTube, avec des vidéos provenant de plusieurs plateformes.
4. Tavily en dernier recours, limité à YouTube.
Les fournisseurs payants ne sont appelés que si les précédents ne remplissent
le nombre demandé.

Quand YouTube répond que la limite du jour est atteinte, on arrête de le
solliciter pendant un moment (réglable) et on passe directement par
Tavily, pour ne pas perdre de temps à chaque recherche.

Format de retour : liste de {"titre", "url", "miniature", "chaine", "duree", "id_video", "source", "source_url", "fournisseur_recherche"}. Les métadonnées absentes restent à None.

Réglages par variables d'environnement :
- YOUTUBE_API_KEY : clé du service officiel de YouTube (sinon GOOGLE_API_KEY)
- SERPER_API_KEY : recherche Google Videos via Serper
- SERPAPI_API_KEY : recherche Google Videos via SerpApi
- SEARCHAPI_API_KEY : recherche Google Videos via SearchApi
- TAVILY_API_KEY : secours web déjà utilisé ailleurs dans Classinus
- RECHERCHE_VIDEO_MEMOIRE_SECONDES : durée de mémorisation (86400 par défaut)
- RECHERCHE_VIDEO_MEMOIRE_TAILLE : nombre de recherches gardées (500 par défaut)
- RECHERCHE_VIDEO_PAUSE_QUOTA_SECONDES : pause après limite atteinte (3600 par défaut)
- RECHERCHE_VIDEO_PAUSE_CLE_SECONDES : pause après une clé refusée par Google (600 par défaut)

NON TESTÉ EN CONDITIONS RÉELLES au moment de l'écriture (06/10/2026) : à
vérifier en production au premier vrai essai.
"""

import html
import logging
import os
import re
import threading
import time

import requests

_URL_YOUTUBE_RECHERCHE = "https://www.googleapis.com/youtube/v3/search"
_URL_YOUTUBE_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
_URL_TAVILY = "https://api.tavily.com/search"
_URL_SERPER_VIDEO = "https://google.serper.dev/videos"
_URL_SERPAPI = "https://serpapi.com/search.json"
_URL_SEARCHAPI = "https://www.searchapi.io/api/v1/search"

_REGEX_ID_VIDEO = re.compile(r"(?:youtu\.be/|youtube\.com/watch\?(?:[^#]*&)?v=|youtube\.com/shorts/)([\w-]{11})")
_REGEX_DUREE_ISO = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
_REGEX_CLE_DANS_URL = re.compile(r"([?&]key=)[^&\s'\")]+")


def _masquer_cle(texte):
    """
    Cache la clé d'API dans un message d'erreur : la bibliothèque requests
    recopie l'adresse complète (clé comprise) dans ses erreurs, et ces
    messages finissent dans les journaux. À utiliser pour tout message
    d'erreur écrit dans les journaux.
    """
    return _REGEX_CLE_DANS_URL.sub(r"\1***", str(texte))

_verrou = threading.Lock()
_memoire = {}  # (requete normalisée, nombre) -> (instant, résultats)
_pause_youtube_jusqu_a = 0.0


def _entier_env(nom, defaut):
    try:
        return int(os.environ.get(nom, defaut))
    except (TypeError, ValueError):
        return defaut


def _cle_memoire(requete, nombre, page=1):
    return (" ".join(requete.lower().split()), nombre, page)


def _lire_memoire(cle):
    duree = _entier_env("RECHERCHE_VIDEO_MEMOIRE_SECONDES", 86400)
    with _verrou:
        entree = _memoire.get(cle)
        if not entree:
            return None
        instant, resultats = entree
        if time.time() - instant > duree:
            _memoire.pop(cle, None)
            return None
        return [dict(r) for r in resultats]


def _ecrire_memoire(cle, resultats):
    taille_max = _entier_env("RECHERCHE_VIDEO_MEMOIRE_TAILLE", 500)
    with _verrou:
        if len(_memoire) >= taille_max and cle not in _memoire:
            plus_ancienne = min(_memoire, key=lambda k: _memoire[k][0])
            _memoire.pop(plus_ancienne, None)
        _memoire[cle] = (time.time(), [dict(r) for r in resultats])


def _formater_duree(iso):
    """Convertit une durée ISO 8601 (PT1H2M3S) en texte lisible (1:02:03)."""
    correspondance = _REGEX_DUREE_ISO.match(iso or "")
    if not correspondance:
        return None
    heures, minutes, secondes = (int(v) if v else 0 for v in correspondance.groups())
    if heures:
        return f"{heures}:{minutes:02d}:{secondes:02d}"
    return f"{minutes}:{secondes:02d}"


def _miniature(id_video):
    return f"https://i.ytimg.com/vi/{id_video}/hqdefault.jpg"


class _LimiteYoutubeAtteinte(Exception):
    pass


class _CleYoutubeRefusee(Exception):
    pass


def _chercher_via_youtube(requete, nombre, cle):
    reponse = requests.get(
        _URL_YOUTUBE_RECHERCHE,
        params={
            "key": cle,
            "part": "snippet",
            "type": "video",
            "q": requete,
            "maxResults": max(1, min(nombre, 20)),
            "safeSearch": "moderate",
        },
        timeout=15,
    )
    if reponse.status_code in (400, 401, 403):
        try:
            erreur = reponse.json().get("error", {})
        except ValueError:
            erreur = {}
        raisons = [e.get("reason") for e in (erreur.get("errors") or [])]
        if "quotaExceeded" in raisons or "dailyLimitExceeded" in raisons:
            raise _LimiteYoutubeAtteinte()
        if reponse.status_code in (401, 403) or "keyInvalid" in raisons:
            raise _CleYoutubeRefusee(f"{reponse.status_code} {raisons} {erreur.get('message')}")
    reponse.raise_for_status()

    elements = reponse.json().get("items", [])
    ids = [e.get("id", {}).get("videoId") for e in elements]
    ids = [i for i in ids if i]
    if not ids:
        return []

    # Les durées demandent un deuxième appel (1 point seulement). Si cet
    # appel échoue, on garde les vidéos sans durée plutôt que de tout perdre.
    durees = {}
    try:
        detail = requests.get(
            _URL_YOUTUBE_VIDEOS,
            params={"key": cle, "part": "contentDetails", "id": ",".join(ids)},
            timeout=15,
        )
        detail.raise_for_status()
        for v in detail.json().get("items", []):
            durees[v.get("id")] = _formater_duree((v.get("contentDetails") or {}).get("duration"))
    except Exception as e:
        logging.warning(f"RECHERCHE VIDEO : durées indisponibles ({_masquer_cle(e)}), résultats gardés sans durée.")

    resultats = []
    for e in elements:
        id_video = e.get("id", {}).get("videoId")
        if not id_video:
            continue
        extrait = e.get("snippet") or {}
        miniatures = extrait.get("thumbnails") or {}
        miniature = (
            (miniatures.get("high") or {}).get("url")
            or (miniatures.get("medium") or {}).get("url")
            or _miniature(id_video)
        )
        resultats.append({
            "titre": html.unescape(extrait.get("title") or requete),
            "url": f"https://www.youtube.com/watch?v={id_video}",
            "miniature": miniature,
            "chaine": html.unescape(extrait.get("channelTitle") or "") or None,
            "duree": durees.get(id_video),
            "id_video": id_video,
        })
    return resultats[:nombre]



def _normaliser_video(item, requete, source_api):
    """Normalise un résultat de moteur vidéo sans inventer son URL."""
    url = item.get("link") or item.get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return None
    titre = html.unescape(str(item.get("title") or item.get("name") or requete)).strip()
    miniature = item.get("imageUrl") or item.get("thumbnail") or item.get("thumbnail_url")
    if not isinstance(miniature, str) or not miniature.startswith("https://"):
        miniature = None
    source = item.get("source") or item.get("platform") or item.get("domain")
    chaine = item.get("channel") or item.get("channel_name") or item.get("author")
    duree = item.get("duration") or item.get("length")
    try:
        domaine = re.sub(r"^www\.", "", __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url).hostname or "")
    except Exception:
        domaine = ""
    return {
        "titre": titre or requete,
        "url": url,
        "miniature": miniature,
        "chaine": html.unescape(str(chaine)).strip() if chaine else None,
        "duree": str(duree).strip() if duree else None,
        "id_video": None,
        "source": html.unescape(str(source)).strip() if source else domaine or source_api,
        "source_url": f"https://{domaine}" if domaine else None,
        "fournisseur_recherche": source_api,
    }


def _chercher_via_serper_video(requete, nombre, cle, page=1):
    reponse = requests.post(
        _URL_SERPER_VIDEO,
        headers={"X-API-KEY": cle, "Content-Type": "application/json"},
        json={"q": requete, "num": min(nombre, 100), "page": max(1, page), "gl": "fr", "hl": "fr"},
        timeout=20,
    )
    reponse.raise_for_status()
    return [
        video for video in (
            _normaliser_video(item, requete, "Serper")
            for item in reponse.json().get("videos", [])
        ) if video
    ]


def _chercher_via_serpapi_video(requete, nombre, cle, page=1):
    reponse = requests.get(
        _URL_SERPAPI,
        params={"engine": "google_videos", "q": requete, "api_key": cle,
                "num": min(nombre, 100), "start": max(0, (page - 1) * nombre),
                "hl": "fr", "gl": "fr"},
        timeout=25,
    )
    reponse.raise_for_status()
    donnees = reponse.json()
    elements = donnees.get("video_results") or donnees.get("videos_results") or []
    return [
        video for video in (
            _normaliser_video(item, requete, "SerpApi")
            for item in elements
        ) if video
    ]


def _chercher_via_searchapi_video(requete, nombre, cle, page=1):
    reponse = requests.get(
        _URL_SEARCHAPI,
        headers={"Authorization": f"Bearer {cle}"},
        params={"engine": "google_videos", "q": requete, "page": max(1, page),
                "hl": "fr", "gl": "fr", "link": "resolved", "safe": "active"},
        timeout=25,
    )
    reponse.raise_for_status()
    donnees = reponse.json()
    elements = donnees.get("videos") or donnees.get("videos_carousel") or []
    return [
        video for video in (
            _normaliser_video(item, requete, "SearchApi")
            for item in elements
        ) if video
    ]


def _chercher_via_tavily(requete, nombre, cle, page=1):
    reponse = requests.post(
        _URL_TAVILY,
        headers={"Authorization": f"Bearer {cle}"},
        json={
            "query": f"{requete} youtube",
            "include_domains": ["youtube.com", "youtu.be"],
            "max_results": min(20, nombre),
        },
        timeout=20,
    )
    reponse.raise_for_status()

    resultats = []
    deja_vus = set()
    for r in reponse.json().get("results", []):
        correspondance = _REGEX_ID_VIDEO.search(r.get("url") or "")
        if not correspondance:
            continue  # chaîne, playlist ou page qui n'est pas une vidéo
        id_video = correspondance.group(1)
        if id_video in deja_vus:
            continue
        deja_vus.add(id_video)
        titre = re.sub(r"\s*[-|]\s*YouTube\s*$", "", html.unescape(r.get("title") or "")).strip()
        resultats.append({
            "titre": titre or requete,
            "url": f"https://www.youtube.com/watch?v={id_video}",
            "miniature": _miniature(id_video),
            "chaine": None,
            "duree": None,
            "id_video": id_video,
        })
    return resultats[:nombre]


def rechercher_videos(requete, nombre=30, page=1):
    """
    Recherche des vidéos sur YouTube et sur le web (Google Videos).
    30 résultats par défaut, jusqu'à 50 par page. Les fournisseurs payants
    ne sont appelés que si les sources précédentes n'ont pas rempli la page.
    """
    global _pause_youtube_jusqu_a
    requete = (requete or "").strip()
    if not requete:
        return []
    try:
        nombre = max(1, min(int(nombre), 50))
        page = max(1, int(page))
    except (TypeError, ValueError):
        nombre, page = 30, 1

    cle_m = _cle_memoire(requete, nombre, page)
    en_memoire = _lire_memoire(cle_m)
    if en_memoire is not None:
        return en_memoire

    resultats = []
    deja_vus = set()

    def ajouter(elements):
        for video in elements or []:
            url = video.get("url")
            if not url or url in deja_vus:
                continue
            deja_vus.add(url)
            resultats.append(video)
            if len(resultats) >= nombre:
                break

    # YouTube officiel en premier : les liens sont directement lisibles dans Classinus.
    cle_youtube = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if page == 1 and cle_youtube and time.time() >= _pause_youtube_jusqu_a:
        try:
            ajouter(_chercher_via_youtube(requete, min(nombre, 20), cle_youtube))
            for video in resultats:
                video.setdefault("source", "YouTube")
                video.setdefault("source_url", "https://www.youtube.com")
                video.setdefault("fournisseur_recherche", "YouTube Data API")
        except _LimiteYoutubeAtteinte:
            pause = _entier_env("RECHERCHE_VIDEO_PAUSE_QUOTA_SECONDES", 3600)
            _pause_youtube_jusqu_a = time.time() + pause
            logging.warning("RECHERCHE VIDEO : quota YouTube atteint, bascule vers les moteurs web.")
        except _CleYoutubeRefusee as e:
            pause = _entier_env("RECHERCHE_VIDEO_PAUSE_CLE_SECONDES", 600)
            _pause_youtube_jusqu_a = time.time() + pause
            logging.warning(f"RECHERCHE VIDEO : clé YouTube refusée, bascule vers les moteurs web ({_masquer_cle(e)}).")
        except Exception as e:
            logging.warning(f"RECHERCHE VIDEO : YouTube indisponible ({_masquer_cle(e)}).")

    # Moteurs de vidéos Google : même clé que les recherches d'images déjà configurées.
    fournisseurs = [
        ("Serper", "SERPER_API_KEY", _chercher_via_serper_video),
        ("SerpApi", "SERPAPI_API_KEY", _chercher_via_serpapi_video),
        ("SearchApi", "SEARCHAPI_API_KEY", _chercher_via_searchapi_video),
    ]
    for nom, variable, fonction in fournisseurs:
        if len(resultats) >= nombre:
            break
        cle = os.environ.get(variable)
        if not cle:
            continue
        try:
            ajouter(fonction(requete, nombre - len(resultats), cle, page))
        except Exception as e:
            logging.warning(f"RECHERCHE VIDEO : {nom} indisponible ({_masquer_cle(e)}).")

    # Tavily reste le dernier recours et peut trouver des vidéos hors YouTube.
    if len(resultats) < nombre:
        cle_tavily = os.environ.get("TAVILY_API_KEY")
        if cle_tavily:
            try:
                ajouter(_chercher_via_tavily(requete, nombre - len(resultats), cle_tavily, page))
            except Exception as e:
                logging.warning(f"RECHERCHE VIDEO : Tavily indisponible ({_masquer_cle(e)}).")

    resultats = resultats[:nombre]
    if resultats:
        _ecrire_memoire(cle_m, resultats)
    return resultats
