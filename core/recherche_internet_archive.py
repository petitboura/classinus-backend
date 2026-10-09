"""
Recherche de livres et de PDF sur Internet Archive pour Classinus
(09/10/2026, demande Bourama, lot 1 du chantier "documents externes").

Ce module ne fait que TROUVER des documents et fabriquer leur lien exact.
La lecture du texte (lot 2) et l'ouverture des PDF dans le visionneur
(lot 3) viendront dans des lots séparés.

Service utilisé : l'API de recherche publique d'Internet Archive
(archive.org/advancedsearch.php), gratuite et sans clé. Seuls les
documents de type "texts" (livres, manuels, PDF scannés) sont cherchés.

Format de retour de rechercher_documents : liste de
{"titre", "auteur", "annee", "langue", "identifiant", "url", "acces"}.
Les champs que la source ne fournit pas valent None.

"acces" est une indication, la page du document fait foi :
- "libre"          : consultable directement, sans compte
- "pret_numerique" : livre encore sous droits, prêté seulement à un
                     utilisateur qui a un compte Internet Archive ; le
                     contenu ne peut pas être lu par Classinus
- "restreint"      : non consultable

Contrairement à la recherche de vidéos, ce module LÈVE une exception
(ErreurRechercheArchive) quand le service échoue, pour que l'outil puisse
distinguer "aucun résultat" de "service indisponible" et ne jamais dire à
l'étudiant qu'un livre n'existe pas alors que le service était en panne.

Réglages par variables d'environnement :
- RECHERCHE_ARCHIVE_DELAI_SECONDES : délai d'attente d'une requête (15 par défaut)
- RECHERCHE_ARCHIVE_ESSAIS : nombre d'essais en cas de panne passagère (2 par défaut)
- RECHERCHE_ARCHIVE_NOMBRE_DEFAUT : nombre de résultats par défaut (6)
- RECHERCHE_ARCHIVE_NOMBRE_MAX : plafond du nombre de résultats (15)

NON TESTÉ EN CONDITIONS RÉELLES au moment de l'écriture : le réseau de
l'environnement de développement bloque archive.org, seule la forme des
réponses a pu être vérifiée par un autre moyen. À vérifier en production
au premier vrai essai.
"""

import logging
import os
import re
import time

import requests

_URL_RECHERCHE = "https://archive.org/advancedsearch.php"
_URL_PAGE_DOCUMENT = "https://archive.org/details/{identifiant}"

# Les caractères qui ont un sens dans le langage de recherche d'Internet
# Archive : laissés tels quels dans la demande d'un étudiant, ils font
# échouer ou fausser la recherche (ex. un deux-points ou une parenthèse).
_REGEX_SYMBOLES_RECHERCHE = re.compile(r'[+\-!(){}\[\]^"~*?:\\/&|]')

_LONGUEUR_MAX_REQUETE = 200

_CHAMPS_DEMANDES = [
    "identifier", "title", "creator", "year", "language",
    "lending___status", "access-restricted-item",
]

# Identifiant Internet Archive : lettres, chiffres, point, tiret, tiret bas.
_REGEX_IDENTIFIANT = re.compile(r"^[\w.\-]+$")


class ErreurRechercheArchive(Exception):
    """Internet Archive n'a pas pu répondre (panne, délai dépassé, réponse illisible)."""


def _entier_env(nom, defaut):
    try:
        valeur = int(os.environ.get(nom, defaut))
        return valeur if valeur > 0 else defaut
    except (TypeError, ValueError):
        return defaut


def _en_liste(valeur):
    """Les champs d'Internet Archive sont tantôt un texte, tantôt une liste, tantôt absents."""
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return [str(v).strip() for v in valeur if v is not None and str(v).strip()]
    texte = str(valeur).strip()
    return [texte] if texte else []


def _texte_ou_none(valeur, maximum=None):
    elements = _en_liste(valeur)
    if not elements:
        return None
    if maximum:
        elements = elements[:maximum]
    return ", ".join(elements)


def _nettoyer_requete(requete):
    texte = _REGEX_SYMBOLES_RECHERCHE.sub(" ", requete or "")
    texte = " ".join(texte.split())
    return texte[:_LONGUEUR_MAX_REQUETE].strip()


def _acces(document):
    restreint = _en_liste(document.get("access-restricted-item"))
    if any(v.lower() == "true" for v in restreint):
        return "restreint"
    statuts = [s.lower() for s in _en_liste(document.get("lending___status"))]
    if any("lendable" in s or "borrow" in s for s in statuts):
        return "pret_numerique"
    return "libre"


def _construire_document(brut):
    identifiant = _texte_ou_none(brut.get("identifier"))
    if not identifiant or not _REGEX_IDENTIFIANT.match(identifiant):
        return None  # un identifiant douteux ne doit jamais devenir un lien
    return {
        "titre": _texte_ou_none(brut.get("title")) or identifiant,
        "auteur": _texte_ou_none(brut.get("creator"), maximum=3),
        "annee": _texte_ou_none(brut.get("year")),
        "langue": _texte_ou_none(brut.get("language")),
        "identifiant": identifiant,
        "url": _URL_PAGE_DOCUMENT.format(identifiant=identifiant),
        "acces": _acces(brut),
    }


def _interroger(requete_nettoyee, nombre):
    parametres = {
        "q": f"({requete_nettoyee}) AND mediatype:texts",
        "fl[]": _CHAMPS_DEMANDES,
        "rows": nombre,
        "output": "json",
    }
    en_tetes = {"User-Agent": "Classinus/1.0 (recherche de documents pour étudiants; https://classinus.com)"}
    delai = _entier_env("RECHERCHE_ARCHIVE_DELAI_SECONDES", 15)
    essais = _entier_env("RECHERCHE_ARCHIVE_ESSAIS", 2)

    derniere_erreur = None
    for essai in range(essais):
        try:
            reponse = requests.get(_URL_RECHERCHE, params=parametres, headers=en_tetes, timeout=delai)
            if reponse.status_code >= 500 or reponse.status_code == 429:
                raise ErreurRechercheArchive(f"réponse {reponse.status_code} d'Internet Archive")
            reponse.raise_for_status()
            return reponse.json()
        except (requests.RequestException, ValueError, ErreurRechercheArchive) as e:
            derniere_erreur = e
            if essai + 1 < essais:
                time.sleep(1)
    raise ErreurRechercheArchive(str(derniere_erreur))


def rechercher_documents(requete, nombre=None):
    """
    Cherche des livres et des PDF sur Internet Archive. Renvoie une liste
    (vide si rien n'est trouvé). Lève ErreurRechercheArchive si le service
    est indisponible ou renvoie une réponse inexploitable.
    """
    requete_nettoyee = _nettoyer_requete(requete)
    if not requete_nettoyee:
        return []

    nombre_defaut = _entier_env("RECHERCHE_ARCHIVE_NOMBRE_DEFAUT", 6)
    nombre_max = _entier_env("RECHERCHE_ARCHIVE_NOMBRE_MAX", 15)
    try:
        nombre = int(nombre) if nombre is not None else nombre_defaut
    except (TypeError, ValueError):
        nombre = nombre_defaut
    nombre = max(1, min(nombre, nombre_max))

    donnees = _interroger(requete_nettoyee, nombre)

    reponse = donnees.get("response") if isinstance(donnees, dict) else None
    documents_bruts = reponse.get("docs") if isinstance(reponse, dict) else None
    if not isinstance(documents_bruts, list):
        logging.error(f"RECHERCHE ARCHIVE : réponse inattendue pour la requête {requete_nettoyee!r}.")
        raise ErreurRechercheArchive("réponse inattendue d'Internet Archive")

    documents = []
    for brut in documents_bruts:
        if not isinstance(brut, dict):
            continue
        document = _construire_document(brut)
        if document:
            documents.append(document)
    return documents
