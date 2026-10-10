"""
Source Zenodo (dépôt du CERN : travaux de recherche, mais aussi cours, thèses
et supports pédagogiques) de la recherche de documents externes (10/10/2026,
demande Bourama). Enregistrée dans core/sources_documents_externes.py.

Service utilisé : l'API publique de Zenodo (zenodo.org/api/records),
gratuite et sans clé pour la recherche. Seuls les dépôts en accès libre qui
contiennent un fichier lisible (PDF, Word, Excel, PowerPoint, texte) sont
gardés : un jeu de données ou une archive de code n'est d'aucune utilité ici.

Chaque résultat : {"titre", "auteur", "annee", "langue", "identifiant",
"url", "url_fichier", "acces"}. url est la page du dépôt sur Zenodo,
url_fichier le lien direct du fichier choisi (le PDF de préférence).

NON VÉRIFIÉ CONTRE UNE VRAIE RÉPONSE au moment de l'écriture : le serveur de
développement n'a pas accès à ce service, le format lu ici suit la
documentation de l'API. À vérifier en production au premier vrai essai : si
le format diffère, cette source ne renverra rien (et le journal le dira),
sans gêner les autres sources.
"""

import logging
from urllib.parse import quote, urlparse

from core.recherche_documents_commun import (
    ErreurRechercheSource,
    appeler_service,
    borner_nombre,
    nettoyer_requete,
    texte_ou_none,
)

NOM_SOURCE = "Zenodo"

ErreurRechercheZenodo = ErreurRechercheSource

_URL_RECHERCHE = "https://zenodo.org/api/records"
_TAILLE_MAX = 30
# Extensions que le lecteur de documents externes sait lire, par ordre de préférence.
_EXTENSIONS_LISIBLES = (".pdf", ".docx", ".pptx", ".xlsx", ".txt")


def _fichier_lisible(fichiers):
    """Nom du meilleur fichier lisible parmi ceux du dépôt, ou None."""
    noms = [f.get("key") for f in fichiers if isinstance(f, dict) and isinstance(f.get("key"), str)]
    for extension in _EXTENSIONS_LISIBLES:
        for nom in noms:
            if nom.lower().endswith(extension):
                return nom
    return None


def _construire_document(brut):
    metadonnees = brut.get("metadata") if isinstance(brut.get("metadata"), dict) else {}
    liens = brut.get("links") if isinstance(brut.get("links"), dict) else {}
    identifiant = texte_ou_none(brut.get("id"))
    if not identifiant:
        return None
    url = texte_ou_none(liens.get("self_html")) or f"https://zenodo.org/records/{identifiant}"
    analyse = urlparse(url)
    if analyse.scheme != "https" or analyse.hostname != "zenodo.org":
        return None  # jamais de lien inventé ou douteux
    fichier = _fichier_lisible(brut.get("files") if isinstance(brut.get("files"), list) else [])
    if not fichier:
        return None  # rien de lisible dans ce dépôt
    createurs = metadonnees.get("creators") if isinstance(metadonnees.get("creators"), list) else []
    date = texte_ou_none(metadonnees.get("publication_date")) or ""
    return {
        "titre": texte_ou_none(metadonnees.get("title")) or url,
        "auteur": texte_ou_none([c.get("name") for c in createurs if isinstance(c, dict)], maximum=3),
        "annee": date[:4] if date[:4].isdigit() else None,
        "langue": texte_ou_none(metadonnees.get("language")),
        "identifiant": identifiant,
        "url": url,
        "url_fichier": f"https://zenodo.org/records/{identifiant}/files/{quote(fichier)}?download=1",
        "acces": "libre",
    }


def rechercher_documents(requete, nombre=None):
    """
    Cherche des documents sur Zenodo. Renvoie une liste (vide si rien n'est
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
            "access_status": "open",
            "sort": "bestmatch",
            # Plus de lignes que nécessaire : les dépôts sans fichier lisible
            # sont écartés ensuite.
            "size": min(nombre * 3, _TAILLE_MAX),
        },
        NOM_SOURCE,
    )
    try:
        donnees = reponse.json()
    except ValueError:
        raise ErreurRechercheSource(f"{NOM_SOURCE} : réponse illisible")

    contenu = donnees.get("hits") if isinstance(donnees, dict) else None
    resultats = contenu.get("hits") if isinstance(contenu, dict) else None
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
