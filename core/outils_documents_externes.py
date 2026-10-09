"""
Outils MCP de la catégorie "documents_externes" : livres et PDF trouvés
hors de Classinus (09/10/2026, demande Bourama, lot 1 du chantier
Internet Archive).

Lot 1 : rechercher_document_externe (trouver un document et donner son
lien exact). La logique est dans core/recherche_internet_archive.py. Ce
fichier ne fait que déclarer l'outil sur `mcp_generation`, comme
rechercher_video (core/outils_generation_media.py) ; son chargement se fait
par l'import dans core/serveur_mcp_generation.py.

Exposé côté chat seulement pour l'instant. Pas ajouté au serveur MCP
public (core/serveur_mcp_espace.py) : la question de l'exposition publique
est à poser à Bourama avant, jamais supposée.

Outil de RECHERCHE : le résultat revient au modèle, qui en a besoin pour
répondre (il n'est donc pas dans OUTILS_AUTONOMES). Le JSON renvoyé utilise
la clé "documents", distincte de "results", "images" et "videos" : les
détecteurs de cartes de core/execution_outils.py tournent sur chaque
résultat d'outil, un outil ne doit jamais s'afficher deux fois.
"""

import json
import logging

from core.outils_generation_commun import mcp_generation
from core.recherche_internet_archive import ErreurRechercheArchive, rechercher_documents


@mcp_generation.tool()
def rechercher_document_externe(requete: str, nombre: int = 6) -> str:
    """
    Cherche un livre, un manuel ou un PDF sur Internet Archive à partir d'un
    titre, d'un auteur ou d'un sujet, et donne le lien exact du document. À
    utiliser quand l'étudiant veut trouver un ouvrage qui n'est ni dans sa
    bibliothèque ni dans le catalogue public de Classinus (pour ceux là,
    utilise les outils de bibliothèque). Renvoie un JSON listant les documents
    trouvés (titre, auteur, année, langue, url, acces).

    Écris le lien de chaque document en markdown [titre](url) avec l'url
    exacte du résultat, sans jamais l'inventer ni la modifier. Le champ acces
    est une indication, la page du document fait foi : "libre" veut dire
    consultable directement ; "pret_numerique" veut dire un livre encore sous
    droits, que l'étudiant ne peut lire qu'en l'empruntant avec un compte
    gratuit Internet Archive, et dont Classinus ne peut pas lire le contenu
    (dis le clairement) ; "restreint" veut dire non consultable.

    Deux liens possibles par document. url est la page sur le site d'Internet
    Archive. url_pdf, quand il est présent, ouvre le PDF directement dans le
    visionneur de Classinus : l'étudiant reste dans l'appli, c'est le lien à
    mettre en avant. Donne les deux, chacun en markdown [titre](adresse) avec
    l'adresse exacte, sans la modifier. Quand il n'y a pas url_pdf, le champ
    note_pdf dit pourquoi : transmets cette mention à l'étudiant avec des mots
    simples, sans inventer de lien.

    Cet outil trouve et donne le lien, il ne lit pas le contenu du document :
    ne prétends jamais avoir lu un livre que tu as seulement trouvé. Si rien
    n'est trouvé, dis le et propose de reformuler (autre titre, nom de
    l'auteur, autre langue). Paramètres : requete (mots clés de la recherche),
    nombre (6 par défaut, 15 au maximum).
    """
    try:
        documents = rechercher_documents(requete, nombre)
    except ErreurRechercheArchive as e:
        logging.error(f"ERREUR outil recherche document externe (requête {requete!r}) : {e}")
        return "Erreur : Internet Archive ne répond pas pour le moment, réessaie dans un instant."
    except Exception as e:
        logging.error(f"ERREUR outil recherche document externe (requête {requete!r}) : {e}")
        return "Erreur : la recherche de documents a échoué, réessaie."

    if not documents:
        return "Aucun document trouvé sur Internet Archive pour cette recherche."
    return json.dumps({"documents": documents}, ensure_ascii=False)
