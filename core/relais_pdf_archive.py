"""
Relais des PDF Internet Archive vers le visionneur du chat (lot 3 du
chantier Internet Archive, 09/10/2026, demande Bourama).

Pourquoi un relais : le visionneur du chat n'ouvre en aperçu que les fichiers
servis par le backend (voir lib/originesFiables.ts du frontend). Un PDF
d'archive.org passe donc par ici, et son lien se termine par .pdf, ce qui
suffit au chat pour l'afficher dans le visionneur sans aucun changement
côté interface.

Fonctionnement :
- le lien est /fichiers/archive/{identifiant}.pdf (voir api/fichiers_archive.py) ;
  le PDF réel est choisi comme pour la lecture du texte (core/lecture_document_archive.py),
  le PDF avec couche de texte d'abord ;
- le fichier est relayé en flux, jamais chargé en entier en mémoire ;
- les requêtes partielles (Range) sont transmises telles quelles à Internet
  Archive : le visionneur ne télécharge que les pages qu'on regarde, donc un
  gros scan de livre s'ouvre sans être téléchargé en entier ;
- plafond haut (500 Mo par défaut) uniquement contre les abus : un fichier
  plus gros est refusé, et jamais plus que le plafond n'est relayé en une
  réponse ;
- un livre en prêt numérique (accès réservé) n'est jamais relayé.

Le retour d'ouvrir_pdf_archive est un objet RelaisPdf : statut, en-têtes et un
générateur d'octets à fermer après usage. Les erreurs sont des ErreurRelais
(statut HTTP + code d'erreur de core/erreurs.py), jamais un message brut.

Réglages par variables d'environnement :
- ARCHIVE_RELAIS_TAILLE_MAX : plafond en octets (500 Mo par défaut)
- ARCHIVE_RELAIS_DELAI : délai d'attente d'Internet Archive en secondes (30)
- ARCHIVE_RELAIS_MEMOIRE_SECONDES : durée de mémorisation du PDF choisi (3600)
- ARCHIVE_RELAIS_MEMOIRE_TAILLE : nombre de documents gardés (500)
- ARCHIVE_RELAIS_LIMITE : limite de débit par personne (voir api/fichiers_archive.py)

NON TESTÉ EN CONDITIONS RÉELLES au moment de l'écriture (09/10/2026) : le
serveur de développement n'a pas accès à archive.org. Le test réel avec un
gros scan est le lot 4.
"""

import logging
import os
import re
import threading
import time
from urllib.parse import quote, urlparse

import requests

from core.lecture_document_archive import (
    _DocumentIllisible,
    _choisir_fichier_pdf,
    _est_vrai,
    _recuperer_metadonnees,
    _taille_fichier,
    extraire_identifiant,
)

_URL_FICHIER = "https://archive.org/download/{id}/{fichier}"
_TAILLE_BLOC = 256 * 1024
_REGEX_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)")
_REGEX_CONTENT_RANGE_VIDE = re.compile(r"bytes\s+\*/(\d+)")
EN_TETES_EXPOSES = "Content-Range, Content-Length, Accept-Ranges"

_verrou = threading.Lock()
_memoire = {}  # identifiant -> (instant, nom du fichier PDF)


class ErreurRelais(Exception):
    def __init__(self, statut, code):
        super().__init__(code)
        self.statut = statut
        self.code = code


class RelaisPdf:
    def __init__(self, statut, entetes, flux, amont):
        self.statut = statut
        self.entetes = entetes
        self.flux = flux  # générateur d'octets, vide pour une requête HEAD
        self._amont = amont

    def fermer(self):
        try:
            self._amont.close()
        except Exception:
            pass


def _entier_env(nom, defaut):
    try:
        valeur = int(os.environ.get(nom, defaut))
        return valeur if valeur > 0 else defaut
    except (TypeError, ValueError):
        return defaut


def plafond_octets():
    return _entier_env("ARCHIVE_RELAIS_TAILLE_MAX", 500 * 1024 * 1024)


def url_visionneur(identifiant, base_publique):
    """Lien du PDF à donner au chat : se termine par .pdf pour s'ouvrir dans le visionneur."""
    base = (base_publique or "").rstrip("/")
    return f"{base}/fichiers/archive/{quote(identifiant, safe='')}.pdf"


def lien_pdf_visionneur(identifiant):
    """Lien du PDF dans le visionneur avec l'adresse publique du backend, ou None si elle est inconnue."""
    try:
        from core.stockage_r2 import R2_PUBLIC_BASE_URL

        return url_visionneur(identifiant, R2_PUBLIC_BASE_URL) if R2_PUBLIC_BASE_URL else None
    except Exception:
        return None


def identifiant_depuis_nom(nom_fichier):
    """'livre_2020.pdf' -> 'livre_2020'. None si le nom n'est pas un lien de ce relais."""
    if not nom_fichier or not nom_fichier.lower().endswith(".pdf"):
        return None
    return extraire_identifiant(nom_fichier[:-4])


def _lire_memoire(identifiant):
    duree = _entier_env("ARCHIVE_RELAIS_MEMOIRE_SECONDES", 3600)
    with _verrou:
        entree = _memoire.get(identifiant)
        if entree and time.time() - entree[0] < duree:
            return entree[1]
        _memoire.pop(identifiant, None)
    return None


def _ecrire_memoire(identifiant, nom_fichier):
    taille_max = max(1, _entier_env("ARCHIVE_RELAIS_MEMOIRE_TAILLE", 500))
    with _verrou:
        _memoire[identifiant] = (time.time(), nom_fichier)
        while len(_memoire) > taille_max:
            plus_ancien = min(_memoire, key=lambda cle: _memoire[cle][0])
            _memoire.pop(plus_ancien, None)


def _trouver_pdf(identifiant):
    """Nom du PDF à relayer. Lève ErreurRelais si le document n'est pas relayable."""
    connu = _lire_memoire(identifiant)
    if connu:
        return connu
    try:
        metadonnees = _recuperer_metadonnees(identifiant)
    except _DocumentIllisible:
        raise ErreurRelais(404, "DOCUMENT_ARCHIVE_INTROUVABLE")
    except requests.RequestException as e:
        logging.error(f"ERREUR RELAIS PDF ARCHIVE ({identifiant}) metadonnees : {type(e).__name__} {str(e)[:200]}")
        raise ErreurRelais(502, "ARCHIVE_INDISPONIBLE")

    if _est_vrai((metadonnees.get("metadata") or {}).get("access-restricted-item")):
        raise ErreurRelais(403, "DOCUMENT_ARCHIVE_RESTREINT")

    fichier = _choisir_fichier_pdf(metadonnees.get("files") or [])
    if not fichier:
        raise ErreurRelais(404, "DOCUMENT_ARCHIVE_SANS_PDF")
    taille = _taille_fichier(fichier)
    if taille and taille > plafond_octets():
        raise ErreurRelais(413, "DOCUMENT_ARCHIVE_TROP_GROS")

    _ecrire_memoire(identifiant, fichier["name"])
    return fichier["name"]


def _hote_archive(url):
    hote = (urlparse(url).hostname or "").lower()
    return hote == "archive.org" or hote.endswith(".archive.org")


def _taille_totale(reponse):
    """Taille complète du fichier, d'après Content-Range (206/416) ou Content-Length (200)."""
    contenu_plage = reponse.headers.get("Content-Range") or ""
    trouve = _REGEX_CONTENT_RANGE.search(contenu_plage)
    if trouve and trouve.group(3) != "*":
        return int(trouve.group(3))
    trouve = _REGEX_CONTENT_RANGE_VIDE.search(contenu_plage)
    if trouve:
        return int(trouve.group(1))
    try:
        return int(reponse.headers.get("Content-Length") or 0)
    except ValueError:
        return 0


def _flux_plafonne(reponse, plafond):
    envoye = 0
    try:
        for bloc in reponse.iter_content(_TAILLE_BLOC):
            if not bloc:
                continue
            envoye += len(bloc)
            if envoye > plafond:
                logging.warning("RELAIS PDF ARCHIVE : plafond atteint en cours de flux, coupure")
                return
            yield bloc
    finally:
        reponse.close()


def ouvrir_pdf_archive(identifiant, methode="GET", plage=None):
    """
    Ouvre le PDF d'un document Internet Archive pour le relayer.
    `plage` est l'en-tête Range du visiteur (ou None). Renvoie un RelaisPdf,
    ou lève ErreurRelais. Le visiteur doit appeler .fermer() après usage.
    """
    nom_fichier = _trouver_pdf(identifiant)
    url = _URL_FICHIER.format(id=quote(identifiant, safe=""), fichier=quote(nom_fichier, safe="/"))
    delai = _entier_env("ARCHIVE_RELAIS_DELAI", 30)
    plafond = plafond_octets()

    try:
        reponse = requests.request(
            "HEAD" if methode == "HEAD" else "GET",
            url,
            headers={"Range": plage} if plage else {},
            timeout=(10, delai),
            stream=True,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logging.error(f"ERREUR RELAIS PDF ARCHIVE ({identifiant}) : {type(e).__name__} {str(e)[:200]}")
        raise ErreurRelais(502, "ARCHIVE_INDISPONIBLE")

    # Les redirections d'Internet Archive restent sur archive.org et ses serveurs.
    sauts = [r.url for r in reponse.history] + [reponse.url]
    if not all(_hote_archive(u) for u in sauts):
        reponse.close()
        logging.error(f"RELAIS PDF ARCHIVE ({identifiant}) : redirection hors archive.org refusée")
        raise ErreurRelais(502, "ARCHIVE_INDISPONIBLE")

    if reponse.status_code in (401, 403):
        reponse.close()
        raise ErreurRelais(403, "DOCUMENT_ARCHIVE_RESTREINT")
    if reponse.status_code == 404:
        reponse.close()
        raise ErreurRelais(404, "DOCUMENT_ARCHIVE_INTROUVABLE")
    if reponse.status_code not in (200, 206, 416):
        reponse.close()
        logging.error(f"ERREUR RELAIS PDF ARCHIVE ({identifiant}) : statut amont {reponse.status_code}")
        raise ErreurRelais(502, "ARCHIVE_INDISPONIBLE")

    total = _taille_totale(reponse)
    if total > plafond:
        reponse.close()
        raise ErreurRelais(413, "DOCUMENT_ARCHIVE_TROP_GROS")

    entetes = {
        "Content-Type": "application/pdf",
        "Accept-Ranges": "bytes",
        "Content-Disposition": "inline",
        # Un PDF d'archive ne change pas : le navigateur peut le garder.
        "Cache-Control": "public, max-age=3600",
        # "identity" empeche la compression globale de l'API (api/main.py) :
        # un lecteur PDF qui voit un contenu compresse abandonne les requetes
        # partielles et telecharge tout le fichier.
        "Content-Encoding": "identity",
        "Access-Control-Expose-Headers": EN_TETES_EXPOSES,
    }
    for cle in ("Content-Length", "Content-Range"):
        if reponse.headers.get(cle):
            entetes[cle] = reponse.headers[cle]

    if methode == "HEAD" or reponse.status_code == 416:
        reponse.close()
        flux = iter(())
    else:
        flux = _flux_plafonne(reponse, plafond)
    return RelaisPdf(reponse.status_code, entetes, flux, reponse)
