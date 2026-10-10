"""
Source arXiv (articles de mathématiques, physique, informatique et autres
sciences, en général en anglais) de la recherche de documents externes
(10/10/2026, demande Bourama). Enregistrée dans core/sources_documents_externes.py.

Service utilisé : l'API publique d'arXiv (export.arxiv.org/api/query),
gratuite et sans clé, qui répond en XML (format Atom).

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "url_fichier", "acces"}. url est la page de l'article sur arXiv,
url_fichier le lien direct du PDF (lu ensuite par lire_document_externe).
"acces" vaut toujours "libre".

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le serveur de
développement n'a pas accès à ce service, le format lu ici suit la
documentation de l'API. Un article sans lien https vers arxiv.org est
ignoré, jamais inventé. À vérifier en production au premier vrai essai : si
le format diffère, cette source ne renverra rien (et le journal le dira),
sans gêner les autres sources.
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

NOM_SOURCE = "arXiv"

# Même exception que les autres sources de ce module commun : le registre
# s'en sert pour savoir qu'un service est indisponible.
ErreurRechercheArxiv = ErreurRechercheSource

_URL_RECHERCHE = "https://export.arxiv.org/api/query"
_HOTES_ARXIV = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}


def _nom_local(balise):
    return balise.rsplit("}", 1)[-1] if isinstance(balise, str) else ""


def _texte(entree, nom):
    element = next((e for e in entree if _nom_local(e.tag) == nom), None)
    return " ".join(element.text.split()) if element is not None and element.text and element.text.strip() else None


def _lien_arxiv(adresse):
    """Adresse arXiv en https, ou None si ce n'est pas un lien arXiv."""
    analyse = urlparse(adresse or "")
    if analyse.hostname not in _HOTES_ARXIV or not analyse.path.strip("/"):
        return None
    return f"https://arxiv.org{analyse.path}"


def _construire_document(entree):
    url = _lien_arxiv(_texte(entree, "id"))
    if not url:
        return None  # jamais de lien inventé ou douteux
    identifiant = url.split("/abs/", 1)[-1].strip("/")
    auteurs = [
        " ".join(e.text.split())
        for a in entree if _nom_local(a.tag) == "author"
        for e in a if _nom_local(e.tag) == "name" and e.text and e.text.strip()
    ]
    publie = _texte(entree, "published") or ""
    document = {
        "titre": _texte(entree, "title") or url,
        "auteur": texte_ou_none(auteurs, maximum=3),
        "annee": publie[:4] if publie[:4].isdigit() else None,
        "langue": None,
        "identifiant": identifiant,
        "url": url,
        "acces": "libre",
    }
    # Lien direct du PDF : celui annoncé par arXiv, sinon construit depuis
    # l'identifiant (arXiv publie ses PDF à /pdf/<identifiant>).
    lien_pdf = next(
        (_lien_arxiv(e.get("href")) for e in entree
         if _nom_local(e.tag) == "link" and (e.get("title") == "pdf" or e.get("type") == "application/pdf")),
        None,
    )
    document["url_fichier"] = lien_pdf or f"https://arxiv.org/pdf/{identifiant}"
    return document


def rechercher_documents(requete, nombre=None):
    """
    Cherche des articles sur arXiv. Renvoie une liste (vide si rien n'est
    trouvé). Lève ErreurRechercheSource si le service est indisponible ou
    renvoie une réponse inexploitable.
    """
    requete_nettoyee = nettoyer_requete(requete)
    if not requete_nettoyee:
        return []
    nombre = borner_nombre(nombre)

    mots = requete_nettoyee.split()
    reponse = appeler_service(
        _URL_RECHERCHE,
        {
            "search_query": " AND ".join(f"all:{mot}" for mot in mots),
            "start": 0,
            "max_results": nombre,
        },
        NOM_SOURCE,
    )
    try:
        racine = ET.fromstring(reponse.content)
    except ET.ParseError:
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse illisible")

    entrees = [e for e in racine if _nom_local(e.tag) == "entry"]
    documents = []
    for entree in entrees:
        document = _construire_document(entree)
        if document:
            documents.append(document)

    if entrees and not documents:
        logging.warning(f"RECHERCHE DOCUMENTS ({NOM_SOURCE}) : des résultats sont arrivés mais aucun lien reconnu, format à revérifier.")
    return documents[:nombre]
