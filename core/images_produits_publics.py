"""Images des produits publics : envoi par le créateur et capture automatique du site.

Chaque image est lue puis réécrite en JPEG ou PNG propre (jamais le fichier d'origine tel quel),
réduite à une largeur raisonnable, et rangée dans produits/<id du compte>/ du bucket R2. Le
créateur reçoit un chemin ; la table des produits ne garde que ces chemins.

La capture lance un navigateur sans fenêtre sur l'adresse du produit. Chaque requête du navigateur
(page, redirection, image, script) passe par valider_url_externe : une adresse qui pointerait vers
le réseau interne du serveur est refusée, comme pour les liens collés dans le chat.
"""
import io
import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from PIL import Image, ImageOps

from core import config_produits_publics as cfg
from core import stockage_r2
from core.erreurs import erreur_api
from core.produits_publics import dossier_images, normaliser_url, url_image
from core.securite_url import UrlNonAutorisee, valider_url_externe

_ARGUMENTS_CHROMIUM = [
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--mute-audio",
]
_places_capture = threading.BoundedSemaphore(cfg.CAPTURES_SIMULTANEES_MAX)
_historique_captures: dict[str, deque] = defaultdict(deque)
_verrou_historique = threading.Lock()


def _ranger(auteur_id: str, octets: bytes, extension: str, type_mime: str) -> dict:
    chemin = f"{dossier_images(auteur_id)}{uuid.uuid4().hex}.{extension}"
    try:
        stockage_r2.from_(cfg.BUCKET_IMAGES).upload(chemin, octets, {"content-type": type_mime})
    except Exception:
        raise erreur_api(500, "PRODUIT_IMAGE_ENVOI_ECHEC")
    return {"chemin": chemin, "url": url_image(chemin)}


def _ouvrir(octets: bytes) -> Image.Image:
    if not octets or len(octets) > cfg.IMAGE_TAILLE_MAX_OCTETS:
        raise erreur_api(413, "PRODUIT_IMAGE_TROP_LOURDE", maximum_mo=cfg.IMAGE_TAILLE_MAX_OCTETS // (1024 * 1024))
    try:
        image = Image.open(io.BytesIO(octets))
        image.load()
    except Exception:
        raise erreur_api(400, "PRODUIT_IMAGE_ILLISIBLE")
    return ImageOps.exif_transpose(image)


def _encoder(image: Image.Image) -> tuple[bytes, str, str]:
    """PNG si l'image a de la transparence (logo), sinon JPEG plus léger."""
    sortie = io.BytesIO()
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        image.convert("RGBA").save(sortie, format="PNG", optimize=True)
        return sortie.getvalue(), "png", "image/png"
    image.convert("RGB").save(sortie, format="JPEG", quality=86, optimize=True, progressive=True)
    return sortie.getvalue(), "jpg", "image/jpeg"


def envoyer_image(auteur_id: str, octets: bytes, type_mime: str, logo: bool = False) -> dict:
    if type_mime not in cfg.TYPES_IMAGE_ACCEPTES:
        raise erreur_api(415, "PRODUIT_IMAGE_TYPE_INVALIDE")
    image = _ouvrir(octets)
    if logo:
        image = ImageOps.fit(image, (cfg.LOGO_COTE_MAX, cfg.LOGO_COTE_MAX), method=Image.LANCZOS)
    elif image.width > cfg.IMAGE_LARGEUR_MAX:
        hauteur = round(image.height * cfg.IMAGE_LARGEUR_MAX / image.width)
        image = image.resize((cfg.IMAGE_LARGEUR_MAX, hauteur), Image.LANCZOS)
    contenu, extension, mime = _encoder(image)
    return _ranger(auteur_id, contenu, extension, mime)


def _verifier_quota_capture(auteur_id: str) -> None:
    maintenant = time.monotonic()
    with _verrou_historique:
        file = _historique_captures[auteur_id]
        while file and maintenant - file[0] > 3600:
            file.popleft()
        if len(file) >= cfg.CAPTURES_PAR_HEURE_ET_COMPTE:
            raise erreur_api(429, "PRODUIT_CAPTURES_TROP_NOMBREUSES")
        file.append(maintenant)


def _filtrer_requete(route) -> None:
    """Chaque requête du navigateur doit viser une adresse publique, sinon elle est coupée."""
    try:
        valider_url_externe(route.request.url)
    except UrlNonAutorisee:
        route.abort()
        return
    route.continue_()


def _prendre_captures(url: str) -> list[bytes]:
    from playwright.sync_api import Error as ErreurPlaywright
    from playwright.sync_api import sync_playwright

    formats = (cfg.CAPTURE_BUREAU, cfg.CAPTURE_TELEPHONE)
    resultats: list[bytes] = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(args=_ARGUMENTS_CHROMIUM)
        try:
            for index, (largeur, hauteur) in enumerate(formats):
                contexte = navigateur.new_context(
                    viewport={"width": largeur, "height": hauteur},
                    device_scale_factor=1,
                    service_workers="block",
                    accept_downloads=False,
                    is_mobile=index == 1,
                    has_touch=index == 1,
                )
                try:
                    contexte.route("**/*", _filtrer_requete)
                    page = contexte.new_page()
                    page.route_web_socket("**/*", lambda ws: ws.close())
                    page.goto(url, wait_until="load", timeout=cfg.CAPTURE_DELAI_CHARGEMENT_S * 1000)
                    page.wait_for_timeout(cfg.CAPTURE_ATTENTE_APRES_CHARGEMENT_MS)
                    resultats.append(page.screenshot(type="png", full_page=False))
                except ErreurPlaywright as e:
                    logging.warning(f"PRODUIT : capture impossible ({largeur}x{hauteur}) pour {url} : {e}")
                finally:
                    contexte.close()
        finally:
            navigateur.close()
    return resultats


def capturer_site(auteur_id: str, adresse: str) -> list[dict]:
    """Prend une capture bureau et une capture téléphone du site, les range et renvoie leurs chemins."""
    url = normaliser_url(adresse)
    try:
        valider_url_externe(url)
    except UrlNonAutorisee:
        raise erreur_api(400, "PRODUIT_URL_INVALIDE")
    _verifier_quota_capture(auteur_id)
    if not _places_capture.acquire(timeout=5):
        raise erreur_api(503, "PRODUIT_CAPTURE_OCCUPEE")
    try:
        try:
            captures = _prendre_captures(url)
        except ImportError:
            raise erreur_api(503, "PRODUIT_CAPTURE_INDISPONIBLE")
        except Exception as e:
            logging.error(f"PRODUIT : navigateur indisponible pour la capture de {url} : {e}")
            raise erreur_api(503, "PRODUIT_CAPTURE_INDISPONIBLE")
    finally:
        _places_capture.release()
    if not captures:
        raise erreur_api(502, "PRODUIT_CAPTURE_ECHEC")
    rangees = []
    for octets in captures:
        image = _ouvrir(octets)
        contenu, extension, mime = _encoder(image)
        rangees.append(_ranger(auteur_id, contenu, extension, mime))
    return rangees


def supprimer_toutes_les_images(auteur_id: str) -> None:
    """Efface le dossier d'images d'un compte (suppression du compte, voir core/purge_compte.py)."""
    stockage = stockage_r2.from_(cfg.BUCKET_IMAGES)
    try:
        chemins = stockage.lister(dossier_images(auteur_id))
        for debut in range(0, len(chemins), 500):
            stockage.remove(chemins[debut:debut + 500])
    except Exception as e:
        logging.error(f"ERREUR PURGE (images produits du compte {auteur_id}) : {e}")
