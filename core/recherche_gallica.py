"""
Source Gallica (Bibliothèque nationale de France) de la recherche de
documents externes (09/10/2026, demande Bourama). Enregistrée dans
core/sources_documents_externes.py.

Service utilisé : l'API de recherche publique de Gallica (SRU,
gallica.bnf.fr/SRU), gratuite et sans clé, qui répond en XML. Seules les
monographies (livres) sont cherchées. Surtout des ouvrages anciens
numérisés, consultables en ligne.

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "acces"}. "acces" vaut toujours "libre" (un document de Gallica
listé ici est consultable en ligne). Cette source ne sait que TROUVER :
l'outil de lecture du texte (lot 2) ne lit que Internet Archive.

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le service
refuse les lectures automatiques depuis l'environnement de développement,
le format lu ici suit la documentation de l'API. Les noms d'éléments sont
lus sans tenir compte des préfixes XML, et un document dont le lien n'est
pas trouvé est ignoré, jamais inventé. À vérifier en production au premier
vrai essai : si le format diffère, cette source ne renverra rien (et le
journal le dira), sans gêner les autres sources.
"""

import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from core.recherche_documents_commun import (
    ErreurRechercheSource,
    appeler_service,
    borner_nombre,
    nettoyer_requete,
    texte_ou_none,
)

NOM_SOURCE = "Gallica"

# Même exception que les autres sources de ce module commun : le registre
# (core/sources_documents_externes.py) s'en sert pour savoir qu'un service est
# indisponible.
ErreurRechercheGallica = ErreurRechercheSource

_URL_RECHERCHE = "https://gallica.bnf.fr/SRU"
_CHAMPS_LUS = ("title", "creator", "date", "language", "identifier")


def _nom_local(balise):
    """Nom d'un élément XML sans son préfixe d'espace de noms."""
    return balise.rsplit("}", 1)[-1] if isinstance(balise, str) else ""


def _lien_gallica(identifiants):
    for valeur in identifiants:
        analyse = urlparse(valeur)
        if analyse.hostname == "gallica.bnf.fr" and analyse.path.startswith("/ark:/"):
            return f"https://gallica.bnf.fr{analyse.path}"
    return None


def _construire_document(champs):
    url = _lien_gallica(champs.get("identifier", []))
    if not url:
        return None  # sans lien Gallica reconnu, jamais de document
    return {
        "titre": texte_ou_none(champs.get("title"), maximum=1) or url,
        "auteur": texte_ou_none(champs.get("creator"), maximum=3),
        "annee": texte_ou_none(champs.get("date"), maximum=1),
        "langue": texte_ou_none(champs.get("language"), maximum=2),
        "identifiant": url.rsplit("/", 1)[-1],
        "url": url,
        "acces": "libre",
    }


def rechercher_documents(requete, nombre=None):
    """
    Cherche des livres sur Gallica. Renvoie une liste (vide si rien n'est
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
            "operation": "searchRetrieve",
            "version": "1.2",
            "query": f'(gallica all "{requete_nettoyee}") and dc.type all "monographie"',
            "maximumRecords": nombre,
        },
        NOM_SOURCE,
    )
    try:
        racine = ET.fromstring(reponse.content)
    except ET.ParseError:
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse illisible")

    enregistrements = [e for e in racine.iter() if _nom_local(e.tag) == "record"]
    documents = []
    for enregistrement in enregistrements:
        donnees = next((e for e in enregistrement.iter() if _nom_local(e.tag) == "recordData"), None)
        if donnees is None:
            continue
        champs = {}
        for element in donnees.iter():
            nom = _nom_local(element.tag)
            if nom in _CHAMPS_LUS and element.text and element.text.strip():
                champs.setdefault(nom, []).append(element.text.strip())
        document = _construire_document(champs)
        if document:
            documents.append(document)

    if enregistrements and not documents:
        logging.warning(f"RECHERCHE DOCUMENTS ({NOM_SOURCE}) : des résultats sont arrivés mais aucun lien reconnu, format à revérifier.")
    return documents[:nombre]
