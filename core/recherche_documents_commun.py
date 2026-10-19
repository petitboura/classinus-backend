"""
Éléments communs aux sources Gallica et HAL de la recherche de documents
externes de Classinus (09/10/2026, demande Bourama, chantier documents
externes) : appel réseau avec nouvel essai, nettoyage de la demande de
l'étudiant, lecture tolérante des champs, borne du nombre de résultats.

core/recherche_internet_archive.py (écrit avant ce module, pour la seule
source d'Internet Archive) garde ses propres copies de ces éléments et ses
propres variables RECHERCHE_ARCHIVE_* ; il n'a pas été modifié.

Réglages par variables d'environnement :
- RECHERCHE_DOCUMENTS_DELAI_SECONDES : délai d'attente d'une requête (15 par défaut)
- RECHERCHE_DOCUMENTS_ESSAIS : nombre d'essais en cas de panne passagère (2 par défaut)
- RECHERCHE_DOCUMENTS_NOMBRE_DEFAUT : nombre de résultats par défaut (6)
- RECHERCHE_DOCUMENTS_NOMBRE_MAX : plafond du nombre de résultats (15)
"""

import logging
import os
import re
import time

import requests

# Les caractères qui ont un sens dans les langages de recherche des sources :
# laissés tels quels dans la demande d'un étudiant, ils font échouer ou
# fausser la recherche (ex. un deux-points ou une parenthèse).
_REGEX_SYMBOLES_RECHERCHE = re.compile(r'[+\-!(){}\[\]^"~*?:\\/&|<>=]')

LONGUEUR_MAX_REQUETE = 200

_EN_TETES = {"User-Agent": "Classinus/1.0 (recherche de documents pour étudiants; https://classinus.com)"}


class ErreurRechercheSource(Exception):
    """Une source n'a pas pu répondre (panne, délai dépassé, réponse illisible)."""


def entier_env(nom, defaut):
    try:
        valeur = int(os.environ.get(nom, defaut))
        return valeur if valeur > 0 else defaut
    except (TypeError, ValueError):
        return defaut


def borner_nombre(nombre):
    """Nombre de résultats demandé, ramené entre 1 et le plafond (défaut si absent ou illisible)."""
    nombre_defaut = entier_env("RECHERCHE_DOCUMENTS_NOMBRE_DEFAUT", 6)
    nombre_max = entier_env("RECHERCHE_DOCUMENTS_NOMBRE_MAX", 15)
    try:
        nombre = int(nombre) if nombre is not None else nombre_defaut
    except (TypeError, ValueError):
        nombre = nombre_defaut
    return max(1, min(nombre, nombre_max))


def en_liste(valeur):
    """Les champs des sources sont tantôt un texte, tantôt une liste, tantôt absents."""
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return [str(v).strip() for v in valeur if v is not None and str(v).strip()]
    texte = str(valeur).strip()
    return [texte] if texte else []


def texte_ou_none(valeur, maximum=None):
    elements = en_liste(valeur)
    if not elements:
        return None
    if maximum:
        elements = elements[:maximum]
    return ", ".join(elements)


def nettoyer_requete(requete):
    texte = _REGEX_SYMBOLES_RECHERCHE.sub(" ", requete or "")
    texte = " ".join(texte.split())
    return texte[:LONGUEUR_MAX_REQUETE].strip()


def _consigner_refus(nom_source, reponse):
    """
    Trace dans les logs ce que le service a répondu quand il refuse la
    demande (réponse 4xx hors 429) : l'en-tête Server, le type du contenu, les
    en-têtes de Cloudflare (cf-mitigated vaut "challenge" quand c'est un défi
    anti-robot, cf-ray identifie la demande), le titre de la page, un code
    d'erreur de type 1020 s'il y en a un, et le début du texte visible. Ajouté le 10/10/2026 : Gallica répond 403 depuis
    Railway et le code seul ne dit pas pourquoi (blocage d'adresse, en-tête
    refusé, quota...). Le texte est coupé et mis sur une seule ligne.
    """
    try:
        page = reponse.text or ""
        titre = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
        titre = " ".join(titre.group(1).split())[:150] if titre else None
        code = re.search(r"error\s*(?:code:?\s*)?(1\d{3})", page, re.IGNORECASE)
        # Le texte visible de la page (sans scripts ni balises) : le début du HTML
        # brut ne montre que des déclarations sans intérêt.
        visible = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
        visible = " ".join(re.sub(r"(?s)<[^>]+>", " ", visible).split())[:300]
        logging.error(
            f"RECHERCHE DOCUMENTS ({nom_source}) : refus {reponse.status_code}, "
            f"Server={reponse.headers.get('Server')!r}, "
            f"Content-Type={reponse.headers.get('Content-Type')!r}, "
            f"cf-mitigated={reponse.headers.get('cf-mitigated')!r}, "
            f"cf-ray={reponse.headers.get('cf-ray')!r}, "
            f"titre={titre!r}, code erreur={code.group(1) if code else None!r}, "
            f"texte de la page : {visible!r}"
        )
    except Exception:
        pass


def appeler_service(url, params, nom_source, en_tetes=None):
    """
    GET avec délai d'attente et nouvel essai en cas de panne passagère
    (délai dépassé, connexion coupée, réponse 429 ou 5xx). Renvoie la
    réponse HTTP, ou lève ErreurRechercheSource.

    `en_tetes` (facultatif) remplace les en-têtes par défaut pour une source
    qui en demande d'autres (Gallica, voir core/recherche_gallica.py). Les
    autres sources n'en passent pas et gardent _EN_TETES.
    """
    delai = entier_env("RECHERCHE_DOCUMENTS_DELAI_SECONDES", 15)
    essais = entier_env("RECHERCHE_DOCUMENTS_ESSAIS", 2)

    derniere_erreur = None
    derniere_reponse_refusee = None
    for essai in range(essais):
        try:
            reponse = requests.get(url, params=params, headers=en_tetes or _EN_TETES, timeout=delai)
            if reponse.status_code >= 500 or reponse.status_code == 429:
                raise ErreurRechercheSource(f"réponse {reponse.status_code} de {nom_source}")
            if 400 <= reponse.status_code < 500:
                derniere_reponse_refusee = reponse
            reponse.raise_for_status()
            return reponse
        except (requests.RequestException, ErreurRechercheSource) as e:
            derniere_erreur = e
            if essai + 1 < essais:
                time.sleep(1)
    logging.error(f"RECHERCHE DOCUMENTS ({nom_source}) : {derniere_erreur}")
    if derniere_reponse_refusee is not None:
        _consigner_refus(nom_source, derniere_reponse_refusee)
    raise ErreurRechercheSource(f"{nom_source} : {derniere_erreur}")
