"""
Source OpenAlex (catalogue mondial d'articles scientifiques ; ne garde ici
que ceux dont une version est en accès libre) de la recherche de documents
externes (10/10/2026, demande Bourama). Enregistrée dans
core/sources_documents_externes.py.

Service utilisé : l'API publique d'OpenAlex (api.openalex.org/works),
gratuite. Une adresse de contact peut être donnée dans la variable
d'environnement OPENALEX_EMAIL (OpenAlex la recommande pour un service plus
fiable, elle n'est pas obligatoire).

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "acces"} et, quand OpenAlex connaît le lien direct du PDF libre,
"url_fichier" (lu ensuite par lire_document_externe). Sans ce lien, le
document ne peut pas être lu : seule sa page est donnée.

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le serveur de
développement n'a pas accès à ce service, le format lu ici suit la
documentation de l'API. À vérifier en production au premier vrai essai : si
le format diffère, cette source ne renverra rien (et le journal le dira),
sans gêner les autres sources.
"""

import logging
import os
from urllib.parse import urlparse

from core.recherche_documents_commun import (
    ErreurRechercheSource,
    appeler_service,
    borner_nombre,
    nettoyer_requete,
    texte_ou_none,
)

NOM_SOURCE = "OpenAlex"

ErreurRechercheOpenAlex = ErreurRechercheSource

_URL_RECHERCHE = "https://api.openalex.org/works"
_CHAMPS_DEMANDES = "id,display_name,authorships,publication_year,language,best_oa_location"
_LIGNES_MAX = 30


def _lien_https(valeur):
    texte = texte_ou_none(valeur)
    analyse = urlparse(texte or "")
    return texte if analyse.scheme == "https" and analyse.hostname else None


def _construire_document(brut):
    emplacement = brut.get("best_oa_location") if isinstance(brut.get("best_oa_location"), dict) else {}
    lien_pdf = _lien_https(emplacement.get("pdf_url"))
    url = _lien_https(emplacement.get("landing_page_url")) or lien_pdf
    if not url:
        return None  # sans lien https vers une version libre, jamais de document
    auteurs = brut.get("authorships") if isinstance(brut.get("authorships"), list) else []
    noms = [
        a.get("author", {}).get("display_name")
        for a in auteurs
        if isinstance(a, dict) and isinstance(a.get("author"), dict)
    ]
    identifiant = (texte_ou_none(brut.get("id")) or url).rstrip("/").rsplit("/", 1)[-1]
    document = {
        "titre": texte_ou_none(brut.get("display_name")) or url,
        "auteur": texte_ou_none(noms, maximum=3),
        "annee": texte_ou_none(brut.get("publication_year")),
        "langue": texte_ou_none(brut.get("language")),
        "identifiant": identifiant,
        "url": url,
        "acces": "libre",
    }
    if lien_pdf:
        document["url_fichier"] = lien_pdf
    return document


def rechercher_documents(requete, nombre=None):
    """
    Cherche des articles en accès libre via OpenAlex. Renvoie une liste (vide
    si rien n'est trouvé). Lève ErreurRechercheSource si le service est
    indisponible ou renvoie une réponse inexploitable.
    """
    requete_nettoyee = nettoyer_requete(requete)
    if not requete_nettoyee:
        return []
    nombre = borner_nombre(nombre)

    parametres = {
        "search": requete_nettoyee,
        "filter": "open_access.is_oa:true",
        "per-page": min(nombre * 2, _LIGNES_MAX),
        "select": _CHAMPS_DEMANDES,
    }
    contact = os.environ.get("OPENALEX_EMAIL", "").strip()
    if contact:
        parametres["mailto"] = contact

    reponse = appeler_service(_URL_RECHERCHE, parametres, NOM_SOURCE)
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
    if resultats and not documents:
        logging.warning(f"RECHERCHE DOCUMENTS ({NOM_SOURCE}) : des résultats sont arrivés mais aucun lien reconnu, format à revérifier.")
    return documents[:nombre]
