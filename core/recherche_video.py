"""
Recherche de vidéos YouTube pour Classinus.

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
3. Tavily en secours, restreint à youtube.com, quand la clé YouTube est
   absente, que la limite du jour est atteinte ou que le service échoue.
   Résultats moins riches : pas de chaîne ni de durée.

Quand YouTube répond que la limite du jour est atteinte, on arrête de le
solliciter pendant un moment (réglable) et on passe directement par
Tavily, pour ne pas perdre de temps à chaque recherche.

Format de retour : liste de {"titre", "url", "miniature", "chaine",
"duree", "id_video"}. "chaine" et "duree" valent None quand la source
(Tavily) ne les fournit pas.

Réglages par variables d'environnement :
- YOUTUBE_API_KEY : clé du service officiel de YouTube (sinon GOOGLE_API_KEY)
- TAVILY_API_KEY : déjà utilisée ailleurs dans Classinus
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

_REGEX_ID_VIDEO = re.compile(r"(?:youtu\.be/|youtube\.com/watch\?(?:[^#]*&)?v=|youtube\.com/shorts/)([\w-]{11})")
_REGEX_DUREE_ISO = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

_verrou = threading.Lock()
_memoire = {}  # (requete normalisée, nombre) -> (instant, résultats)
_pause_youtube_jusqu_a = 0.0


def _entier_env(nom, defaut):
    try:
        return int(os.environ.get(nom, defaut))
    except (TypeError, ValueError):
        return defaut


def _cle_memoire(requete, nombre):
    return (" ".join(requete.lower().split()), nombre)


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
    if reponse.status_code in (400, 403):
        try:
            erreur = reponse.json().get("error", {})
        except ValueError:
            erreur = {}
        raisons = [e.get("reason") for e in (erreur.get("errors") or [])]
        if "quotaExceeded" in raisons or "dailyLimitExceeded" in raisons:
            raise _LimiteYoutubeAtteinte()
        if reponse.status_code == 403 or "keyInvalid" in raisons:
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
        logging.warning(f"RECHERCHE VIDEO : durées indisponibles ({e}), résultats gardés sans durée.")

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


def _chercher_via_tavily(requete, nombre, cle):
    reponse = requests.post(
        _URL_TAVILY,
        headers={"Authorization": f"Bearer {cle}"},
        json={
            "query": f"{requete} youtube",
            "include_domains": ["youtube.com", "youtu.be"],
            "max_results": 10,
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


def rechercher_videos(requete, nombre=6):
    """
    Cherche des vidéos YouTube. Renvoie une liste (peut être vide).
    Ne lève jamais d'exception : une recherche de vidéos est un bonus pour
    la réponse, jamais un prérequis.
    """
    global _pause_youtube_jusqu_a

    requete = (requete or "").strip()
    if not requete:
        return []

    cle_m = _cle_memoire(requete, nombre)
    en_memoire = _lire_memoire(cle_m)
    if en_memoire is not None:
        return en_memoire

    cle_youtube = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if cle_youtube and time.time() >= _pause_youtube_jusqu_a:
        try:
            resultats = _chercher_via_youtube(requete, nombre, cle_youtube)
            if resultats:
                _ecrire_memoire(cle_m, resultats)
                return resultats
        except _LimiteYoutubeAtteinte:
            pause = _entier_env("RECHERCHE_VIDEO_PAUSE_QUOTA_SECONDES", 3600)
            _pause_youtube_jusqu_a = time.time() + pause
            logging.error(
                f"RECHERCHE VIDEO : limite du jour de YouTube atteinte, passage par Tavily pendant {pause} secondes."
            )
        except _CleYoutubeRefusee as e:
            pause = _entier_env("RECHERCHE_VIDEO_PAUSE_CLE_SECONDES", 600)
            _pause_youtube_jusqu_a = time.time() + pause
            logging.error(
                f"RECHERCHE VIDEO : clé refusée par YouTube ({e}). Service YouTube non activé ou clé limitée "
                f"à un autre service. Passage par Tavily pendant {pause} secondes."
            )
        except Exception as e:
            logging.error(f"ERREUR RECHERCHE VIDEO (YouTube, requête {requete!r}) : {e}")
    elif not cle_youtube:
        logging.warning("Aucune clé YouTube (YOUTUBE_API_KEY ou GOOGLE_API_KEY) : recherche de vidéos tentée via Tavily.")

    cle_tavily = os.environ.get("TAVILY_API_KEY")
    if not cle_tavily:
        logging.error("TAVILY_API_KEY manquante : aucun fournisseur de recherche de vidéos disponible.")
        return []

    try:
        resultats = _chercher_via_tavily(requete, nombre, cle_tavily)
    except Exception as e:
        logging.error(f"ERREUR RECHERCHE VIDEO (Tavily, requête {requete!r}) : {e}")
        return []

    if resultats:
        _ecrire_memoire(cle_m, resultats)
    return resultats
