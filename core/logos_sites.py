"""
Logo d'un site, vérifié côté serveur (29/10/2026, demande de Bourama).

Problème réglé : quand un site n'a pas d'icône, le service public d'icônes de Google
répond "introuvable" (404) mais envoie quand même une petite image de globe. Le
navigateur affiche cette image comme si c'était un vrai logo, et l'écran n'a aucun moyen
de la distinguer : le globe prenait la place de la lettre de secours.

Ici, c'est le serveur qui pose la question à Google. Il voit le vrai statut et ne renvoie
l'image que si Google a réellement une icône. Sinon il répond 404 sans image, et l'écran
affiche la lettre. La réponse est gardée en mémoire un moment, pour que ce soit rapide et
identique sur le web, le PC et le mobile.

Rien n'est lié à un compte : c'est uniquement un nom de site et son icône publique, donc
rien à purger à la suppression d'un compte.
"""

import re
import threading
import time

import httpx

URL_SERVICE_ICONES = "https://www.google.com/s2/favicons"
# Google redirige vers son propre serveur d'icônes : on n'accepte que ses adresses.
HOTES_AUTORISES = ("google.com", "gstatic.com")

TAILLE_DEMANDEE = 64
DELAI_REPONSE = 4.0
MAX_REDIRECTIONS = 3
TAILLE_MAX_IMAGE = 200_000

# Durées de mémorisation, en secondes. Un site sans icône peut en publier une plus tard :
# on réessaie donc plus souvent que pour un logo déjà trouvé.
DUREE_TROUVE = 24 * 3600
DUREE_ABSENT = 6 * 3600
DUREE_INDISPONIBLE = 60
MAX_ENTREES_MEMOIRE = 2000

TROUVE = "trouve"
ABSENT = "absent"
INDISPONIBLE = "indisponible"

_NOM_DE_SITE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$"
)

_memoire = {}
_verrou = threading.Lock()


def normaliser_site(domaine):
    """Nom de site en minuscules, sans "www.", ou None s'il n'a pas la forme d'un nom de site."""
    if not isinstance(domaine, str):
        return None
    nom = domaine.strip().lower()
    if nom.startswith("www."):
        nom = nom[4:]
    return nom if _NOM_DE_SITE.fullmatch(nom) else None


def _hote_autorise(hote):
    hote = (hote or "").lower()
    return any(hote == h or hote.endswith("." + h) for h in HOTES_AUTORISES)


def _interroger_service(nom):
    """Pose la question à Google. Renvoie (statut, octets, type de contenu)."""
    try:
        with httpx.Client(follow_redirects=True, max_redirects=MAX_REDIRECTIONS, timeout=DELAI_REPONSE) as client:
            reponse = client.get(URL_SERVICE_ICONES, params={"domain": nom, "sz": TAILLE_DEMANDEE})
    except httpx.HTTPError:
        return INDISPONIBLE, None, None

    if not _hote_autorise(reponse.url.host):
        return INDISPONIBLE, None, None
    if reponse.status_code == 404:
        return ABSENT, None, None
    if reponse.status_code != 200:
        return INDISPONIBLE, None, None

    type_contenu = (reponse.headers.get("content-type") or "").split(";")[0].strip().lower()
    octets = reponse.content
    if not type_contenu.startswith("image/") or not octets or len(octets) > TAILLE_MAX_IMAGE:
        return INDISPONIBLE, None, None
    return TROUVE, octets, type_contenu


def _duree(statut):
    return {TROUVE: DUREE_TROUVE, ABSENT: DUREE_ABSENT}.get(statut, DUREE_INDISPONIBLE)


def _faire_de_la_place(maintenant):
    """Retire les réponses périmées, puis les plus anciennes si la mémoire est pleine."""
    for cle in [c for c, (expire, *_reste) in _memoire.items() if expire <= maintenant]:
        del _memoire[cle]
    while len(_memoire) >= MAX_ENTREES_MEMOIRE:
        del _memoire[next(iter(_memoire))]


def logo_du_site(domaine):
    """
    Renvoie (statut, octets, type de contenu, nom normalisé) :
    - TROUVE : Google a une vraie icône, les octets de l'image suivent ;
    - ABSENT : Google n'a pas d'icône pour ce site (l'écran affiche la lettre) ;
    - INDISPONIBLE : Google n'a pas répondu, ou le nom n'est pas un nom de site.
    """
    nom = normaliser_site(domaine)
    if nom is None:
        return INDISPONIBLE, None, None, None

    maintenant = time.time()
    with _verrou:
        trouve = _memoire.get(nom)
        if trouve and trouve[0] > maintenant:
            return trouve[1], trouve[2], trouve[3], nom

    statut, octets, type_contenu = _interroger_service(nom)

    with _verrou:
        _faire_de_la_place(time.time())
        _memoire[nom] = (time.time() + _duree(statut), statut, octets, type_contenu)
    return statut, octets, type_contenu, nom


def duree_cache_navigateur(statut):
    """Durée, en secondes, pendant laquelle le navigateur peut garder la réponse sans redemander."""
    return _duree(statut)


def vider_memoire():
    """Pour les tests."""
    with _verrou:
        _memoire.clear()
