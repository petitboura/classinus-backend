"""
Source HAL (archive ouverte française de la recherche : articles, thèses,
rapports, cours) de la recherche de documents externes (09/10/2026, demande
Bourama). Enregistrée dans core/sources_documents_externes.py.

Service utilisé : l'API de recherche publique de HAL
(api.archives-ouvertes.fr/search), gratuite et sans clé. Seuls les
documents dont le texte complet est déposé sont gardés (une simple notice
sans fichier n'est d'aucune utilité pour un étudiant).

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "acces"}. L'url est la page du document sur HAL, qui donne accès au
fichier. "acces" vaut "libre" (texte complet déposé). Cette source ne sait
que TROUVER : l'outil de lecture du texte (lot 2) ne lit que Internet Archive.

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le service
interdit la lecture automatique depuis l'environnement de développement, le
format lu ici suit la documentation de l'API. Un document sans lien https
est ignoré, jamais inventé. À vérifier en production au premier vrai essai :
si le format diffère, cette source ne renverra rien (et le journal le dira),
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

NOM_SOURCE = "HAL"

# Même exception que les autres sources de ce module commun : le registre
# (core/sources_documents_externes.py) s'en sert pour savoir qu'un service est
# indisponible.
ErreurRechercheHal = ErreurRechercheSource

_URL_RECHERCHE = "https://api.archives-ouvertes.fr/search/"
_CHAMPS_DEMANDES = "docid,title_s,authFullName_s,producedDateY_i,language_s,uri_s,fileMain_s"
_LIGNES_MAX = 30


def _construire_document(brut):
    if not texte_ou_none(brut.get("fileMain_s")):
        return None  # notice sans texte complet déposé
    url = texte_ou_none(brut.get("uri_s"))
    analyse = urlparse(url or "")
    if analyse.scheme != "https" or not analyse.hostname:
        return None  # jamais de lien inventé ou douteux
    identifiant = texte_ou_none(brut.get("docid")) or analyse.path.strip("/")
    return {
        "titre": texte_ou_none(brut.get("title_s"), maximum=1) or url,
        "auteur": texte_ou_none(brut.get("authFullName_s"), maximum=3),
        "annee": texte_ou_none(brut.get("producedDateY_i")),
        "langue": texte_ou_none(brut.get("language_s"), maximum=2),
        "identifiant": identifiant,
        "url": url,
        "acces": "libre",
    }


def rechercher_documents(requete, nombre=None):
    """
    Cherche des documents sur HAL. Renvoie une liste (vide si rien n'est
    trouvé). Lève ErreurRechercheSource si le service est indisponible ou
    renvoie une réponse inexploitable.
    """
    requete_nettoyee = nettoyer_requete(requete)
    if not requete_nettoyee:
        return []
    nombre = borner_nombre(nombre)

    reponse = appeler_service(
        _URL_RECHERCHE,
        {
            "q": requete_nettoyee,
            "wt": "json",
            # On demande plus de lignes que nécessaire : les notices sans
            # fichier sont écartées ensuite.
            "rows": min(nombre * 2, _LIGNES_MAX),
            "fl": _CHAMPS_DEMANDES,
        },
        NOM_SOURCE,
    )
    try:
        donnees = reponse.json()
    except ValueError:
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse illisible")

    contenu = donnees.get("response") if isinstance(donnees, dict) else None
    documents_bruts = contenu.get("docs") if isinstance(contenu, dict) else None
    if not isinstance(documents_bruts, list):
        logging.error(f"RECHERCHE DOCUMENTS ({NOM_SOURCE}) : réponse inattendue pour {requete_nettoyee!r}.")
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse inattendue")

    documents = []
    for brut in documents_bruts:
        if isinstance(brut, dict):
            document = _construire_document(brut)
            if document:
                documents.append(document)
    return documents[:nombre]
