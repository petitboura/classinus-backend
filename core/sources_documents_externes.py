"""
Registre des sources de documents externes de Classinus (09/10/2026,
demande Bourama).

Deux façons de chercher, selon ce que l'étudiant a indiqué :
- l'étudiant NOMME une source (rare) : la recherche porte sur elle seule ;
- l'étudiant n'en nomme aucune : la recherche porte sur TOUTES les sources
  à la fois, les résultats sont mélangés (un de chaque source tour à tour)
  et chacun indique sa source. Décision de Bourama du 09/10/2026 (version
  "mélangée"). Une source qui ne répond pas ne bloque pas les autres : on
  affiche ce qui est trouvé ailleurs et on signale la source en panne.

Réglages par variables d'environnement (aucun changement de code) :
- RECHERCHE_DOCUMENTS_MODE : "melangee" (par défaut) ou "une_source" (sans
  indication de l'étudiant, seule la source par défaut est cherchée, comme
  avant l'ajout de Gallica et HAL)
- RECHERCHE_DOCUMENTS_SOURCES : liste de clés séparées par des virgules
  (ex. "internet_archive,hal") pour n'activer que certaines sources ; vide
  par défaut = toutes. Une source désactivée est traitée comme inconnue.

POUR AJOUTER UNE SOURCE (une bibliothèque en ligne de plus) :
1. Écrire un module de recherche comme core/recherche_gallica.py (une
   fonction rechercher_documents(requete, nombre=None) qui renvoie une liste
   de documents, et une exception quand le service est indisponible).
2. Ajouter une entrée dans _TOUTES_LES_SOURCES ci-dessous.
Ni core/outils_documents_externes.py (l'outil) ni core/registre_outils.py
n'ont besoin d'être touchés : le texte que le modèle lit sur l'outil est
fabriqué à partir de SOURCES.

Format d'un document renvoyé par une source : {"titre", "auteur", "annee",
"langue", "identifiant", "url", "acces"}. Ce module ajoute le champ "source"
(le nom lisible de la source) à chaque document.

Valeurs possibles de "acces" : "libre", "pret_numerique", "restreint"
(voir core/recherche_internet_archive.py). Seul Internet Archive utilise
"pret_numerique" et "restreint" ; Gallica et HAL ne renvoient que "libre".
"""

import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from core.recherche_documents_commun import ErreurRechercheSource, borner_nombre
from core.recherche_gallica import rechercher_documents as _rechercher_gallica
from core.recherche_hal import rechercher_documents as _rechercher_hal
from core.recherche_internet_archive import ErreurRechercheArchive, rechercher_documents as _rechercher_archive

# Clé = identifiant interne stable de la source. "alias" = façons dont un
# étudiant (ou le modèle) peut nommer la source ; comparées après
# normalisation (sans accents, sans majuscules, espaces et tirets ramenés
# à un tiret bas). L'ordre ici est l'ordre du mélange des résultats.
_TOUTES_LES_SOURCES = {
    "internet_archive": {
        "nom": "Internet Archive",
        "alias": ["archive", "archive.org", "internet archive", "internetarchive", "wayback"],
        "description": "livres, manuels et PDF numérisés",
        "rechercher": _rechercher_archive,
        "erreur": ErreurRechercheArchive,
    },
    "gallica": {
        "nom": "Gallica",
        "alias": ["bnf", "gallica.bnf.fr", "bibliotheque nationale de france", "bibliotheque nationale"],
        "description": "ouvrages anciens numérisés de la Bibliothèque nationale de France",
        "rechercher": _rechercher_gallica,
        "erreur": ErreurRechercheSource,
    },
    "hal": {
        "nom": "HAL",
        "alias": ["hal.science", "archives ouvertes", "archive ouverte", "hal archives ouvertes"],
        "description": "articles de recherche, thèses et rapports en texte complet",
        "rechercher": _rechercher_hal,
        "erreur": ErreurRechercheSource,
    },
}


def _cles_actives():
    demandees = [c.strip() for c in os.environ.get("RECHERCHE_DOCUMENTS_SOURCES", "").split(",") if c.strip()]
    if not demandees:
        return list(_TOUTES_LES_SOURCES)
    connues = [c for c in demandees if c in _TOUTES_LES_SOURCES]
    if len(connues) != len(demandees):
        logging.warning(f"RECHERCHE DOCUMENTS : sources inconnues ignorées dans RECHERCHE_DOCUMENTS_SOURCES ({demandees}).")
    return connues or list(_TOUTES_LES_SOURCES)


# Sources actives (réglage lu une fois au démarrage).
SOURCES = {cle: _TOUTES_LES_SOURCES[cle] for cle in _cles_actives()}

# Source utilisée quand l'étudiant n'en nomme aucune, SEULEMENT en mode
# "une_source" (voir mode_recherche).
SOURCE_PAR_DEFAUT = "internet_archive" if "internet_archive" in SOURCES else next(iter(SOURCES))


class SourceInconnue(Exception):
    """La source demandée n'existe pas dans SOURCES ; le message liste les sources disponibles."""


class ToutesSourcesIndisponibles(Exception):
    """Aucune des sources interrogées n'a pu répondre."""


def mode_recherche():
    """"melangee" (toutes les sources à la fois, par défaut) ou "une_source"."""
    return "une_source" if os.environ.get("RECHERCHE_DOCUMENTS_MODE", "").strip().lower() == "une_source" else "melangee"


def recherche_melangee_active():
    return mode_recherche() == "melangee" and len(SOURCES) > 1


def noms_sources():
    return [infos["nom"] for infos in SOURCES.values()]


def _normaliser(texte):
    texte = unicodedata.normalize("NFD", str(texte or "").strip().lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s\-]+", "_", texte).strip("_")


def identifiant_source(source):
    """
    Identifiant interne (clé de SOURCES) correspondant à ce que l'étudiant a
    indiqué. Source vide ou absente : la source par défaut. Source inconnue :
    SourceInconnue, jamais un repli silencieux sur une autre source (un
    étudiant qui demande une bibliothèque précise ne doit pas croire qu'elle
    a été fouillée alors qu'elle ne l'a pas été).
    """
    demande = _normaliser(source)
    if not demande:
        return SOURCE_PAR_DEFAUT
    for cle, infos in SOURCES.items():
        if demande == _normaliser(cle) or demande == _normaliser(infos["nom"]):
            return cle
        if demande in {_normaliser(a) for a in infos.get("alias", [])}:
            return cle
    raise SourceInconnue(
        f"Source inconnue : {str(source).strip()}. Sources disponibles : {', '.join(noms_sources())}."
    )


def erreur_de_la_source(cle):
    """Classe d'exception levée par cette source quand son service est indisponible."""
    return SOURCES[cle]["erreur"]


def _chercher_une_source(cle, requete, nombre):
    """
    (clé, documents, en_panne). Ne lève jamais : une source qui échoue, pour
    quelque raison que ce soit (service indisponible, format de réponse
    inattendu), ne doit pas faire perdre les résultats des autres.
    """
    infos = SOURCES[cle]
    try:
        documents = infos["rechercher"](requete, nombre)
    except infos["erreur"] as e:
        logging.error(f"RECHERCHE DOCUMENTS : {infos['nom']} indisponible ({e}).")
        return cle, [], True
    except Exception as e:
        logging.error(f"ERREUR RECHERCHE DOCUMENTS : {infos['nom']} a échoué de façon inattendue ({e}).")
        return cle, [], True
    for document in documents:
        document["source"] = infos["nom"]
    return cle, documents, False


def _melanger(listes, total):
    """Un document de chaque source à tour de rôle, sans doublon d'adresse, jusqu'à `total`."""
    melange, vues = [], set()
    for rang in range(max((len(liste) for liste in listes), default=0)):
        for liste in listes:
            if rang >= len(liste):
                continue
            document = liste[rang]
            if document["url"] in vues:
                continue
            vues.add(document["url"])
            melange.append(document)
            if len(melange) >= total:
                return melange
    return melange


def _rechercher_partout(requete, nombre):
    cles = list(SOURCES)
    with ThreadPoolExecutor(max_workers=len(cles)) as pool:
        resultats = list(pool.map(lambda cle: _chercher_une_source(cle, requete, nombre), cles))

    indisponibles = [SOURCES[cle]["nom"] for cle, _, en_panne in resultats if en_panne]
    if len(indisponibles) == len(cles):
        raise ToutesSourcesIndisponibles("Aucune source ne répond pour le moment.")

    interrogees = [SOURCES[cle]["nom"] for cle, _, en_panne in resultats if not en_panne]
    documents = _melanger([docs for _, docs, en_panne in resultats if not en_panne], nombre)
    return ", ".join(interrogees), documents, indisponibles


def rechercher(source, requete, nombre=None):
    """
    Cherche dans UNE source, ou dans toutes à la fois si l'étudiant n'en a
    nommé aucune (mode "melangee"). Renvoie (noms des sources interrogées,
    liste de documents chacun avec le champ "source", noms des sources en
    panne). Lève SourceInconnue si la source nommée n'existe pas,
    ToutesSourcesIndisponibles si aucune source ne répond en mode mélangé, ou
    l'exception propre à la source si son service est indisponible quand une
    seule source est cherchée.
    """
    nombre = borner_nombre(nombre)
    if not _normaliser(source) and recherche_melangee_active():
        return _rechercher_partout(requete, nombre)

    cle = identifiant_source(source)
    infos = SOURCES[cle]
    documents = infos["rechercher"](requete, nombre)
    for document in documents:
        document["source"] = infos["nom"]
    return infos["nom"], documents, []
