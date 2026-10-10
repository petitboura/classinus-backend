"""
Source Project Gutenberg (livres du domaine public, surtout littéraires) de
la recherche de documents externes (10/10/2026, demande Bourama).
Enregistrée dans core/sources_documents_externes.py.

Service utilisé : Gutendex (gutendex.com), une API publique gratuite et sans
clé qui interroge le catalogue de Project Gutenberg. ATTENTION : Gutendex
n'est pas géré par Project Gutenberg, c'est un service tiers. S'il
disparaît, cette source tombe en panne (signalée à l'étudiant) sans gêner
les autres, et il faudra la brancher sur un autre service.

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "url_fichier", "acces"}. url est la page du livre sur
gutenberg.org, url_fichier le lien direct de la version texte brut (lue
ensuite par lire_document_externe). "annee" est toujours absent : le
catalogue ne donne pas l'année de publication du livre. Sans version texte
brut en https, pas de url_fichier.

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le serveur de
développement n'a pas accès à ce service, le format lu ici suit la
documentation de l'API. À vérifier en production au premier vrai essai : si
le format diffère, cette source ne renverra rien (et le journal le dira),
sans gêner les autres sources.
"""

import logging
from urllib.parse import urlparse

from core.recherche_documents_commun import (
    ErreurRechercheSource,
    appeler_service,
    borner_nombre,
    nettoyer_requete,
    texte_ou_none,
)

NOM_SOURCE = "Project Gutenberg"

ErreurRechercheGutenberg = ErreurRechercheSource

_URL_RECHERCHE = "https://gutendex.com/books/"


def _lien_texte(formats):
    """Lien https de la version texte brut, ou None."""
    if not isinstance(formats, dict):
        return None
    for type_mime, adresse in formats.items():
        if isinstance(type_mime, str) and type_mime.startswith("text/plain") and isinstance(adresse, str):
            analyse = urlparse(adresse)
            if analyse.scheme == "https" and analyse.hostname and analyse.hostname.endswith("gutenberg.org"):
                return adresse
    return None


def _construire_document(brut):
    identifiant = texte_ou_none(brut.get("id"))
    if not identifiant:
        return None
    auteurs = brut.get("authors") if isinstance(brut.get("authors"), list) else []
    document = {
        "titre": texte_ou_none(brut.get("title")) or f"Livre {identifiant}",
        "auteur": texte_ou_none([a.get("name") for a in auteurs if isinstance(a, dict)], maximum=3),
        "annee": None,
        "langue": texte_ou_none(brut.get("languages"), maximum=2),
        "identifiant": identifiant,
        "url": f"https://www.gutenberg.org/ebooks/{identifiant}",
        "acces": "libre",
    }
    lien = _lien_texte(brut.get("formats"))
    if lien:
        document["url_fichier"] = lien
    return document


def rechercher_documents(requete, nombre=None):
    """
    Cherche des livres du domaine public. Renvoie une liste (vide si rien
    n'est trouvé). Lève ErreurRechercheSource si le service est indisponible
    ou renvoie une réponse inexploitable.
    """
    requete_nettoyee = nettoyer_requete(requete)
    if not requete_nettoyee:
        return []
    nombre = borner_nombre(nombre)

    reponse = appeler_service(_URL_RECHERCHE, {"search": requete_nettoyee}, NOM_SOURCE)
    try:
        donnees = reponse.json()
    except ValueError:
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse illisible")

    resultats = donnees.get("results") if isinstance(donnees, dict) else None
    if not isinstance(resultats, list):
        logging.error(f"RECHERCHE DOCUMENTS ({NOM_SOURCE}) : réponse inattendue pour {requete_nettoyee!r}.")
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse inattendue")

    documents = []
    for brut in resultats:
        if isinstance(brut, dict):
            document = _construire_document(brut)
            if document:
                documents.append(document)
    return documents[:nombre]
