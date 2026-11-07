"""
Recherche d'image : cascade de fournisseurs, avec cache en mémoire.

L'ordre par défaut est celui validé avec Bourama (07/11/2026) :

1. Wikimedia Commons (gratuit, sans clé) : vraies photos de lieux, personnes,
   monuments, espèces, événements.
2. Openverse (gratuit, sans clé) : photos et illustrations sous licence libre
   venues de nombreuses sources.
3. Serper (clé SERPER_API_KEY) : Google Images, le vrai web. Crédits gratuits
   à l'inscription puis payant au volume.
4. SerpApi (clé SERPAPI_API_KEY) : Google Images, 250 recherches gratuites par
   mois. Secours de Serper.
5. Pixabay (clé PIXABAY_API_KEY) : banque de photos de stock, illustrations,
   vecteurs. Ancien premier choix, qui ne trouvait pas de vraies images.
6. Pexels (clé PEXELS_API_KEY) : banque de photos de stock, dernier recours.

Un fournisseur est essayé seulement si le précédent échoue ou ne renvoie rien
(erreur, quota dépassé, panne, clé absente). Un fournisseur à clé sans clé
configurée est simplement sauté. La recherche ne fait jamais échouer l'outil.

L'ordre se change sans toucher au code, avec la variable d'environnement
RECHERCHE_IMAGE_ORDRE (noms séparés par des virgules, parmi : wikimedia,
openverse, serper, serpapi, pixabay, pexels). Un fournisseur absent de la
liste n'est jamais utilisé.

Cache : un résultat non vide est gardé en mémoire (même requête, même nombre
d'images) pour économiser les crédits gratuits. Jamais d'erreur ni de résultat
vide en cache. Réglages : RECHERCHE_IMAGE_CACHE_SECONDES (défaut 3 jours, 0 pour
désactiver) et RECHERCHE_IMAGE_CACHE_MAX (défaut 500 requêtes).

Format de retour inchangé : liste de {"titre", "url", "miniature", "credit"}.
Seules les adresses https sont gardées pour Wikimedia, Openverse, Serper et
SerpApi (une image http est bloquée dans une page https).

NON TESTÉ EN CONDITIONS RÉELLES : ces services ne sont pas joignables depuis
l'environnement de développement. Les tests (test_recherche_image_cascade.py)
utilisent des réponses fabriquées d'après la documentation des API. À vérifier
au premier vrai test en production.
"""

import html
import logging
import os
import re
import threading
import time

import requests

_URL_PIXABAY = "https://pixabay.com/api/"
_URL_PEXELS = "https://api.pexels.com/v1/search"
_URL_WIKIMEDIA = "https://commons.wikimedia.org/w/api.php"
_URL_OPENVERSE = "https://api.openverse.org/v1/images/"
_URL_SERPER = "https://google.serper.dev/images"
_URL_SERPAPI = "https://serpapi.com/search.json"

_AGENT_UTILISATEUR = "Classinus/1.0 (https://classinus.com)"
_DELAI_NOUVEAUX_FOURNISSEURS = 10
_DELAI_BANQUES = 15

_ORDRE_PAR_DEFAUT = "wikimedia,openverse,serper,serpapi,pixabay,pexels"
_CACHE_SECONDES_PAR_DEFAUT = 259200  # 3 jours
_CACHE_MAX_PAR_DEFAUT = 500

# Formats que le visionneur sait afficher (on écarte svg, tiff, pdf, audio, vidéo).
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
        logging.warning(f"{cle} invalide ({brut!r}), valeur par défaut {defaut} utilisée.")
        return defaut


def _https(adresse):
    """Renvoie l'adresse si elle est en https, sinon None."""
    if isinstance(adresse, str) and adresse.startswith("https://"):
        return adresse
    return None


def _texte_sans_html(texte) -> str:
    if not texte:
        return ""
    sans_balises = re.sub(r"<[^>]+>", " ", str(texte))
    return " ".join(html.unescape(sans_balises).split())


def _chercher_via_pixabay(requete: str, nombre: int, cle: str) -> list[dict]:
    reponse = requests.get(
        _URL_PIXABAY,
        params={
            "key": cle,
            "q": requete,
            "per_page": max(3, min(nombre, 20)),  # minimum imposé par l'API Pixabay
            "safesearch": "true",
        },
        timeout=_DELAI_BANQUES,
    )
    reponse.raise_for_status()
    hits = reponse.json().get("hits", [])
    # "url" = image DIRECTE (pas pageURL, qui pointe vers la page Pixabay
    # marketing) : nécessaire pour que le visionneur en app
    # (VisionneurPositionGlobal.tsx, typeMime "image/*") puisse l'afficher
    # directement, comme n'importe quelle autre image de la bibliothèque.
    return [
        {
            "titre": h.get("tags") or requete,
            "url": h.get("largeImageURL") or h.get("webformatURL"),
            "miniature": h.get("webformatURL") or h.get("previewURL"),
            "credit": f"{h['user']} (Pixabay)" if h.get("user") else "Pixabay",
        }
        for h in hits[:nombre]
        if (h.get("largeImageURL") or h.get("webformatURL")) and (h.get("webformatURL") or h.get("previewURL"))
    ]


def _chercher_via_pexels(requete: str, nombre: int, cle: str) -> list[dict]:
    reponse = requests.get(
        _URL_PEXELS,
        headers={"Authorization": cle},
        params={"query": requete, "per_page": max(1, min(nombre, 15))},
        timeout=_DELAI_BANQUES,
    )
    reponse.raise_for_status()
    photos = reponse.json().get("photos", [])
    return [
        {
            "titre": p.get("alt") or requete,
            "url": (p.get("src") or {}).get("large") or (p.get("src") or {}).get("original"),
            "miniature": (p.get("src") or {}).get("medium") or (p.get("src") or {}).get("small"),
            "credit": f"{p['photographer']} (Pexels)" if p.get("photographer") else "Pexels",
        }
        for p in photos[:nombre]
        if ((p.get("src") or {}).get("large") or (p.get("src") or {}).get("original")) and (p.get("src") or {}).get("medium")
    ]


def _chercher_via_wikimedia(requete: str, nombre: int, _cle=None) -> list[dict]:
    reponse = requests.get(
        _URL_WIKIMEDIA,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,  # espace "Fichier"
            "gsrsearch": requete,
            "gsrlimit": max(10, min(nombre * 3, 30)),  # marge : tous les fichiers ne sont pas des images affichables
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 1000,  # évite de renvoyer l'original, parfois énorme
            "iiextmetadatafilter": "Artist",
        },
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    pages = (reponse.json().get("query") or {}).get("pages") or {}
    sortie = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        infos = (page.get("imageinfo") or [{}])[0]
        if infos.get("mime") not in _MIMES_AFFICHABLES:
            continue
        adresse = _https(infos.get("thumburl")) or _https(infos.get("url"))
        if not adresse:
            continue
        titre = re.sub(r"^[^:]+:", "", page.get("title") or "", count=1)
        titre = titre.rsplit(".", 1)[0].replace("_", " ").strip() or requete
        artiste = _texte_sans_html(((infos.get("extmetadata") or {}).get("Artist") or {}).get("value"))[:80]
        sortie.append(
            {
                "titre": titre,
                "url": adresse,
                "miniature": adresse,
                "credit": f"{artiste} (Wikimedia Commons)" if artiste else "Wikimedia Commons",
            }
        )
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_openverse(requete: str, nombre: int, _cle=None) -> list[dict]:
    reponse = requests.get(
        _URL_OPENVERSE,
        headers={"User-Agent": _AGENT_UTILISATEUR},
        params={"q": requete, "page_size": max(1, min(nombre, 20))},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for r in reponse.json().get("results", []):
        miniature = _https(r.get("thumbnail"))
        adresse = _https(r.get("url")) or miniature
        if not adresse:
            continue
        createur = (r.get("creator") or "").strip()
        sortie.append(
            {
                "titre": r.get("title") or requete,
                "url": adresse,
                "miniature": miniature or adresse,
                "credit": f"{createur} (Openverse)" if createur else "Openverse",
            }
        )
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_serper(requete: str, nombre: int, cle: str) -> list[dict]:
    # Pas de paramètre "num" : le nombre par défaut de l'API est gardé, puis
    # coupé à `nombre` ci-dessous (voir NON TESTÉ plus haut).
    reponse = requests.post(
        _URL_SERPER,
        headers={"X-API-KEY": cle, "Content-Type": "application/json"},
        json={"q": requete},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for h in reponse.json().get("images", []):
        miniature = _https(h.get("thumbnailUrl"))
        # Si l'original n'est pas en https, on prend la miniature (hébergée par Google).
        adresse = _https(h.get("imageUrl")) or miniature
        if not adresse:
            continue
        sortie.append(
            {
                "titre": h.get("title") or requete,
                "url": adresse,
                "miniature": miniature or adresse,
                "credit": h.get("source") or h.get("domain") or "Google Images",
            }
        )
        if len(sortie) >= nombre:
            break
    return sortie


def _chercher_via_serpapi(requete: str, nombre: int, cle: str) -> list[dict]:
    reponse = requests.get(
        _URL_SERPAPI,
        params={"engine": "google_images", "q": requete, "api_key": cle, "safe": "active"},
        timeout=_DELAI_NOUVEAUX_FOURNISSEURS,
    )
    reponse.raise_for_status()
    sortie = []
    for h in reponse.json().get("images_results", []):
        miniature = _https(h.get("thumbnail"))
        adresse = _https(h.get("original")) or miniature
        if not adresse:
            continue
        sortie.append(
            {
                "titre": h.get("title") or requete,
                "url": adresse,
                "miniature": miniature or adresse,
                "credit": h.get("source") or "Google Images",
            }
        )
        if len(sortie) >= nombre:
            break
    return sortie


# nom -> (fonction, variable d'environnement de la clé, ou None si sans clé)
_FOURNISSEURS = {
    "wikimedia": (_chercher_via_wikimedia, None),
    "openverse": (_chercher_via_openverse, None),
    "serper": (_chercher_via_serper, "SERPER_API_KEY"),
    "serpapi": (_chercher_via_serpapi, "SERPAPI_API_KEY"),
    "pixabay": (_chercher_via_pixabay, "PIXABAY_API_KEY"),
    "pexels": (_chercher_via_pexels, "PEXELS_API_KEY"),
}


def _ordre_fournisseurs() -> list[str]:
    brut = _get_secret("RECHERCHE_IMAGE_ORDRE") or _ORDRE_PAR_DEFAUT
    ordre = []
    for nom in (n.strip().lower() for n in brut.split(",")):
        if not nom or nom in ordre:
            continue
        if nom not in _FOURNISSEURS:
            logging.warning(f"RECHERCHE_IMAGE_ORDRE : fournisseur inconnu {nom!r}, ignoré.")
            continue
        ordre.append(nom)
    return ordre


# Cache en mémoire : {(requête normalisée, nombre): (expire, résultats)}.
# Un seul processus uvicorn (voir Procfile), donc un cache par processus suffit.
_cache: dict = {}
_verrou_cache = threading.Lock()


def vider_cache_images() -> None:
    with _verrou_cache:
        _cache.clear()


def _cle_cache(requete: str, nombre: int) -> tuple:
    return (" ".join(requete.lower().split()), nombre)


def _lire_cache(cle: tuple):
    with _verrou_cache:
        trouve = _cache.get(cle)
        if trouve is None:
            return None
        expire, resultats = trouve
        if time.monotonic() >= expire:
            del _cache[cle]
            return None
        return [dict(r) for r in resultats]


def _ecrire_cache(cle: tuple, resultats: list[dict]) -> None:
    duree = _lire_entier("RECHERCHE_IMAGE_CACHE_SECONDES", _CACHE_SECONDES_PAR_DEFAUT)
    if duree <= 0 or not resultats:
        return
    maximum = max(1, _lire_entier("RECHERCHE_IMAGE_CACHE_MAX", _CACHE_MAX_PAR_DEFAUT))
    with _verrou_cache:
        _cache.pop(cle, None)
        while len(_cache) >= maximum:
            _cache.pop(next(iter(_cache)))  # la plus ancienne entrée
        _cache[cle] = (time.monotonic() + duree, [dict(r) for r in resultats])


def rechercher_images(requete: str, nombre: int = 6) -> list[dict]:
    """
    Cherche des images sur le web. Essaie les fournisseurs dans l'ordre
    configuré (voir le début du fichier) et s'arrête au premier qui renvoie
    des images. Renvoie une liste (peut être vide) de {"titre", "url",
    "miniature", "credit"}.
    """
    cle_cache = _cle_cache(requete, nombre)
    en_cache = _lire_cache(cle_cache)
    if en_cache is not None:
        return en_cache

    essayes = []
    for nom in _ordre_fournisseurs():
        fonction, variable_cle = _FOURNISSEURS[nom]
        cle = None
        if variable_cle:
            cle = _get_secret(variable_cle)
            if not cle:
                logging.debug(f"Recherche d'image : {variable_cle} absente, {nom} sauté.")
                continue
        essayes.append(nom)
        try:
            resultats = fonction(requete, nombre, cle)
        except Exception as e:
            logging.error(f"ERREUR RECHERCHE IMAGE ({nom}, requête {requete!r}) : {e}")
            continue
        if resultats:
            _ecrire_cache(cle_cache, resultats)
            return resultats

    if essayes:
        logging.warning(f"Recherche d'image : aucun résultat pour {requete!r} (essayés : {', '.join(essayes)}).")
    else:
        logging.error("Recherche d'image : aucun fournisseur disponible (ordre vide ou clés absentes).")
    return []
