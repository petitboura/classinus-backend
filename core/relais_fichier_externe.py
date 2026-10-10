"""
Relais des fichiers hebergés sur des sites externes (10/10/2026, demande de Bourama).

Pourquoi : le navigateur ne peut pas charger un PDF d'un autre site (CORS), donc
l'apercu et le telechargement echouent. Le backend va chercher le fichier a la
place du navigateur et le renvoie en flux, avec les requetes partielles (Range)
pour que le lecteur ne prenne que les pages regardees.

Securite (le fichier vient d'un site que nous ne controlons pas, et il est servi
depuis api.classinus.com, l'origine de confiance du site) :
- Le lien du relais est signe (HMAC) et expire. Il n'est delivre qu'a un
  utilisateur connecte (voir api/fichiers_externes.py). Le relais n'est donc pas
  un proxy ouvert : on ne peut pas lui faire relayer une adresse choisie librement.
- Le type est verifie sur les premiers octets du fichier (signature), jamais
  d'apres l'en-tete du site distant. Seuls PDF, Office, images raster et texte brut
  passent. Jamais HTML, SVG, XML ni script.
- Le Content-Type renvoye est impose par nous, avec nosniff et
  Content-Security-Policy sandbox : meme une erreur de tri ne peut pas executer un script.
- Anti-SSRF refait a chaque redirection (valider_url_externe), redirections
  suivies a la main, cinq au maximum, aucun cookie ni en-tete d'identification
  envoye au site distant.
- Plafond de taille, delai maximum, limite de debit (api/fichiers_externes.py).

Limite connue : l'adresse est validee juste avant la requete, mais la requete
resout le nom de domaine une seconde fois. Un domaine qui change d'adresse entre
les deux (DNS rebinding) n'est pas totalement exclu. Le jeton signe, le plafond de
taille et le refus de tout contenu non liste limitent ce que cela permettrait.

Reglages par variables d'environnement :
- RELAIS_EXTERNE_SECRET : cle de signature des liens (sinon derivee de SUPABASE_SECRET)
- RELAIS_EXTERNE_TAILLE_MAX : plafond en octets (100 Mo par defaut)
- RELAIS_EXTERNE_DELAI : delai d'attente du site distant en secondes (30)
- RELAIS_EXTERNE_DUREE_LIEN : duree de validite d'un lien en secondes (3600)
- RELAIS_EXTERNE_LIMITE : limite de debit par personne (voir api/fichiers_externes.py)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from core.securite_url import UrlNonAutorisee, valider_url_externe

_TAILLE_BLOC = 256 * 1024
_SAUTS_MAX = 5
_REGEX_PLAGE = re.compile(r"^bytes=\d*-\d*$")
_REGEX_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)")
_REGEX_CONTENT_RANGE_VIDE = re.compile(r"bytes\s+\*/(\d+)")
_AGENT = "Mozilla/5.0 (compatible; ClassinusFichierRelais/1.0)"
EN_TETES_EXPOSES = "Content-Range, Content-Length, Accept-Ranges"

# Type impose par nous, jamais celui du site distant. Cle : type reconnu sur les octets.
TYPES_AUTORISES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "zip": "application/zip",
    "ole": "application/octet-stream",
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "texte": "text/plain; charset=utf-8",
}
_EXTENSIONS_TEXTE = {"txt", "csv", "md", "json", "tex"}
_EXTENSIONS_OFFICE_OLE = {"doc": "ole", "xls": "ole", "ppt": "ole"}
_EXTENSIONS_ZIP = {"docx", "xlsx", "pptx", "zip"}


class ErreurRelais(Exception):
    def __init__(self, statut, code):
        super().__init__(code)
        self.statut = statut
        self.code = code


class RelaisExterne:
    def __init__(self, statut, entetes, flux, amont):
        self.statut = statut
        self.entetes = entetes
        self.flux = flux
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
    return _entier_env("RELAIS_EXTERNE_TAILLE_MAX", 100 * 1024 * 1024)


def duree_lien():
    return _entier_env("RELAIS_EXTERNE_DUREE_LIEN", 3600)


# Jetons signes

def _cle_signature():
    brute = os.environ.get("RELAIS_EXTERNE_SECRET") or os.environ.get("SUPABASE_SECRET")
    if not brute:
        raise ErreurRelais(503, "RELAIS_EXTERNE_INDISPONIBLE")
    return hashlib.sha256(b"relais-fichier-externe|" + brute.encode("utf-8")).digest()


def _b64(octets):
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


def _b64_inverse(texte):
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def creer_jeton(url, type_reconnu, maintenant=None):
    charge = {"u": url, "t": type_reconnu, "e": int((maintenant or time.time()) + duree_lien())}
    corps = _b64(json.dumps(charge, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_cle_signature(), corps.encode("ascii"), hashlib.sha256).digest())
    return f"{corps}.{signature}"


def lire_jeton(jeton, maintenant=None):
    """Renvoie (url, type reconnu) si le jeton est authentique et valide, sinon ErreurRelais(403)."""
    try:
        corps, signature = jeton.split(".", 1)
        attendue = _b64(hmac.new(_cle_signature(), corps.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, attendue):
            raise ValueError("signature")
        charge = json.loads(_b64_inverse(corps))
        if int(charge["e"]) < (maintenant or time.time()):
            raise ValueError("expire")
        url, type_reconnu = charge["u"], charge["t"]
        if type_reconnu not in TYPES_AUTORISES or not isinstance(url, str):
            raise ValueError("contenu")
        return url, type_reconnu
    except ErreurRelais:
        raise
    except Exception:
        raise ErreurRelais(403, "LIEN_RELAIS_INVALIDE")


# Reconnaissance du type sur les octets

def type_depuis_octets(debut, nom_ou_url=""):
    """
    Type reconnu d'apres les premiers octets, ou None si le contenu n'est pas
    dans la liste autorisee. Le nom ne sert qu'a departager les formats qui
    partagent une meme signature (Office et zip, ancien Office, texte).
    """
    extension = (urlparse(nom_ou_url).path.rsplit(".", 1)[-1] if "." in urlparse(nom_ou_url).path else "").lower()

    if debut.startswith(b"%PDF-"):
        return "pdf"
    if debut.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if debut.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if debut.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if debut[:4] == b"RIFF" and debut[8:12] == b"WEBP":
        return "webp"
    if debut.startswith(b"PK\x03\x04"):
        return extension if extension in _EXTENSIONS_ZIP else "zip"
    if debut.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole" if extension in _EXTENSIONS_OFFICE_OLE else None
    if extension in _EXTENSIONS_TEXTE:
        return "texte" if _ressemble_a_du_texte_brut(debut) else None
    return None


def _ressemble_a_du_texte_brut(debut):
    if not debut or b"\x00" in debut:
        return False
    try:
        texte = debut.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            texte = debut[:-3].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return False
    tete = texte.lstrip("﻿ \t\r\n").lower()
    # Une page web ou un SVG deguise en texte brut est refuse.
    return not tete.startswith(("<", "<!"))


# Requete vers le site distant

def _requete_amont(url, methode, plage):
    """
    Suit les redirections a la main, anti-SSRF a chaque saut. Renvoie la reponse
    finale (en flux, a fermer) et l'adresse finale. Lève ErreurRelais.
    """
    delai = _entier_env("RELAIS_EXTERNE_DELAI", 30)
    courante = url
    for _ in range(_SAUTS_MAX + 1):
        try:
            valider_url_externe(courante)
        except UrlNonAutorisee as e:
            logging.warning(f"RELAIS EXTERNE BLOQUE (SSRF) : {courante} : {e}")
            raise ErreurRelais(400, "LIEN_EXTERNE_NON_AUTORISE")

        entetes = {"User-Agent": _AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        if plage:
            entetes["Range"] = plage
        try:
            reponse = requests.request(
                "HEAD" if methode == "HEAD" else "GET",
                courante,
                headers=entetes,
                timeout=(10, delai),
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            logging.warning(f"RELAIS EXTERNE ECHEC ({courante}) : {type(e).__name__} {str(e)[:200]}")
            raise ErreurRelais(502, "SITE_EXTERNE_INDISPONIBLE")

        if reponse.status_code in (301, 302, 303, 307, 308):
            suivant = reponse.headers.get("Location")
            reponse.close()
            if not suivant:
                raise ErreurRelais(502, "SITE_EXTERNE_INDISPONIBLE")
            courante = urljoin(courante, suivant)
            continue
        return reponse, courante
    raise ErreurRelais(502, "SITE_EXTERNE_INDISPONIBLE")


def _verifier_statut(reponse):
    if reponse.status_code in (401, 403):
        reponse.close()
        raise ErreurRelais(403, "FICHIER_EXTERNE_RESTREINT")
    if reponse.status_code in (404, 410):
        reponse.close()
        raise ErreurRelais(404, "FICHIER_EXTERNE_INTROUVABLE")
    if reponse.status_code not in (200, 206, 416):
        reponse.close()
        raise ErreurRelais(502, "SITE_EXTERNE_INDISPONIBLE")


def _taille_totale(reponse):
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


def _debut_de_plage(reponse):
    """Position du premier octet de cette reponse dans le fichier (0 pour un 200)."""
    if reponse.status_code != 206:
        return 0
    trouve = _REGEX_CONTENT_RANGE.search(reponse.headers.get("Content-Range") or "")
    return int(trouve.group(1)) if trouve else -1


def inspecter(url):
    """
    Verifie un lien externe avant de delivrer un lien de relais : anti-SSRF, plafond
    de taille, et type reconnu sur les premiers octets. Renvoie un dict
    {type, nom, taille}. Lève ErreurRelais.
    """
    reponse, finale = _requete_amont(url, "GET", "bytes=0-4095")
    try:
        _verifier_statut(reponse)
        if reponse.status_code == 416:
            raise ErreurRelais(415, "TYPE_FICHIER_NON_AUTORISE")
        total = _taille_totale(reponse)
        if total > plafond_octets():
            raise ErreurRelais(413, "FICHIER_EXTERNE_TROP_GROS")
        debut = b""
        for bloc in reponse.iter_content(4096):
            debut += bloc
            if len(debut) >= 4096:
                break
    finally:
        reponse.close()

    type_reconnu = type_depuis_octets(debut[:4096], finale) or type_depuis_octets(debut[:4096], url)
    if not type_reconnu:
        raise ErreurRelais(415, "TYPE_FICHIER_NON_AUTORISE")

    nom = os.path.basename(urlparse(finale).path) or "fichier"
    return {"type": type_reconnu, "nom": nom, "taille": total or None}


def _flux_verifie(reponse, type_attendu, plafond, debut_position):
    """
    Relaye les octets avec le plafond. Si la reponse commence au debut du fichier,
    les premiers octets sont revérifiés : le site distant a pu changer de contenu
    depuis la delivrance du lien. Un contenu qui ne correspond plus est coupe.
    """
    envoye = 0
    premier = debut_position == 0
    try:
        for bloc in reponse.iter_content(_TAILLE_BLOC):
            if not bloc:
                continue
            if premier:
                premier = False
                if type_depuis_octets(bloc[:4096], reponse.url) != type_attendu and not (
                    type_attendu in _EXTENSIONS_ZIP and bloc.startswith(b"PK\x03\x04")
                ):
                    logging.warning("RELAIS EXTERNE : le contenu ne correspond plus au type verifie, coupure")
                    return
            envoye += len(bloc)
            if envoye > plafond:
                logging.warning("RELAIS EXTERNE : plafond atteint en cours de flux, coupure")
                return
            yield bloc
    finally:
        reponse.close()


def _nom_sur(nom):
    propre = re.sub(r"[^A-Za-z0-9._-]", "_", nom or "fichier")[:120]
    return propre or "fichier"


def ouvrir_fichier_externe(jeton, nom_affiche, methode="GET", plage=None, telechargement=False):
    """Ouvre le fichier du jeton pour le relayer. Renvoie un RelaisExterne ou lève ErreurRelais."""
    url, type_reconnu = lire_jeton(jeton)
    if plage and not _REGEX_PLAGE.match(plage.strip()):
        plage = None  # une plage multiple ou mal formee est ignoree, jamais transmise

    reponse, _ = _requete_amont(url, methode, plage.strip() if plage else None)
    _verifier_statut(reponse)

    plafond = plafond_octets()
    total = _taille_totale(reponse)
    if total > plafond:
        reponse.close()
        raise ErreurRelais(413, "FICHIER_EXTERNE_TROP_GROS")

    disposition = "attachment" if telechargement else "inline"
    entetes = {
        "Content-Type": TYPES_AUTORISES[type_reconnu],
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'{disposition}; filename="{_nom_sur(nom_affiche)}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "private, max-age=600",
        # "identity" empeche la compression globale de l'API : un lecteur PDF qui voit
        # un contenu compresse abandonne les requetes partielles.
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
        debut = _debut_de_plage(reponse)
        flux = _flux_verifie(reponse, type_reconnu, plafond, debut)
    return RelaisExterne(reponse.status_code, entetes, flux, reponse)
