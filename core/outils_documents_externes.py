"""
Outils MCP de la catégorie "documents_externes" : livres, PDF et articles
trouvés hors de Classinus (09/10/2026, demande Bourama, chantier Internet
Archive).

rechercher_document_externe : trouver un document et donner son lien exact.
Plusieurs sources (voir core/sources_documents_externes.py). Sans indication
de l'étudiant, la recherche porte sur toutes les sources à la fois et les
résultats sont mélangés avec leur source ; l'étudiant peut aussi nommer une
source. La logique de chaque source est dans son propre module
(core/recherche_internet_archive.py, core/recherche_gallica.py,
core/recherche_hal.py). Ce fichier ne fait que déclarer l'outil sur
`mcp_generation`, comme rechercher_video (core/outils_generation_media.py) ;
son chargement se fait par l'import dans core/serveur_mcp_generation.py.

Le texte que le modèle lit sur l'outil (docstring) est fabriqué à partir du
registre des sources : ajouter une source ne demande pas de le réécrire.

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
from core.sources_documents_externes import (
    SOURCES,
    SourceInconnue,
    ToutesSourcesIndisponibles,
    erreur_de_la_source,
    identifiant_source,
    recherche_melangee_active,
    rechercher,
)


def _phrase_sources_en_panne(indisponibles):
    if len(indisponibles) == 1:
        return f"{indisponibles[0]} n'a pas répondu"
    return f"{' et '.join(indisponibles)} n'ont pas répondu"


def rechercher_document_externe(requete: str, source: str = "", nombre: int = 6) -> str:
    try:
        noms_interroges, documents, indisponibles = rechercher(source, requete, nombre)
    except SourceInconnue as e:
        # Message prévu pour être relayé tel quel : il liste les sources
        # disponibles, le modèle peut alors proposer l'une d'elles.
        return f"Erreur : {e}"
    except ToutesSourcesIndisponibles:
        logging.error(f"ERREUR outil recherche document externe : aucune source ne répond (requête {requete!r}).")
        return "Erreur : aucune bibliothèque ne répond pour le moment, réessaie dans un instant."
    except Exception as e:
        try:
            nom_source = SOURCES[identifiant_source(source)]["nom"]
            service_indisponible = isinstance(e, erreur_de_la_source(identifiant_source(source)))
        except SourceInconnue:
            nom_source, service_indisponible = "la source demandée", False
        logging.error(f"ERREUR outil recherche document externe (source {source!r}, requête {requete!r}) : {e}")
        if service_indisponible:
            return f"Erreur : {nom_source} ne répond pas pour le moment, réessaie dans un instant."
        return "Erreur : la recherche de documents a échoué, réessaie."

    if not documents:
        message = f"Aucun document trouvé sur {noms_interroges} pour cette recherche."
        if indisponibles:
            message += f" Attention, {_phrase_sources_en_panne(indisponibles)}."
        return message

    resultat = {"documents": documents}
    if indisponibles:
        resultat["sources_indisponibles"] = indisponibles
    return json.dumps(resultat, ensure_ascii=False)


# Texte lu par le modèle, fabriqué à partir du registre des sources (voir
# core/sources_documents_externes.py) pour qu'ajouter une source ne demande
# pas de le réécrire.
_LISTE_SOURCES = ", ".join(
    f"{infos['nom']} ({infos['description']})" for infos in SOURCES.values()
)

if recherche_melangee_active():
    _CONSIGNE_SOURCES = f"""Sources disponibles : {_LISTE_SOURCES}. Par défaut, la recherche porte sur TOUTES ces
    sources à la fois et mélange les résultats, chacun indiquant sa source dans
    le champ source : laisse alors le paramètre source vide. Renseigne source
    seulement quand l'étudiant demande une bibliothèque précise (passe son nom) :
    la recherche ne porte alors que sur elle. Si l'étudiant demande une source
    qui n'est pas dans la liste, dis lui qu'elle n'est pas disponible pour
    l'instant et propose une source disponible, sans jamais chercher ailleurs
    sans le lui dire. Si une source n'a pas répondu (champ sources_indisponibles),
    dis le à l'étudiant : les résultats viennent seulement des autres."""
else:
    _CONSIGNE_SOURCES = f"""Sources disponibles : {_LISTE_SOURCES}. La recherche porte sur UNE seule source à la
    fois, jamais sur plusieurs en même temps. Si l'étudiant indique une source,
    passe son nom dans le paramètre source. S'il n'en indique aucune, laisse
    source vide : la source par défaut est utilisée. Si l'étudiant demande une
    source qui n'est pas dans la liste, dis lui qu'elle n'est pas disponible
    pour l'instant et propose une source disponible, sans jamais chercher
    ailleurs sans le lui dire."""

rechercher_document_externe.__doc__ = f"""
    Cherche un livre, un manuel, un PDF ou un article dans des bibliothèques
    en ligne à partir d'un titre, d'un auteur ou d'un sujet, et donne le lien
    exact du document. À utiliser quand l'étudiant veut trouver un ouvrage qui
    n'est ni dans sa bibliothèque ni dans le catalogue public de Classinus
    (pour ceux là, utilise les outils de bibliothèque). Renvoie un JSON listant
    les documents trouvés (titre, auteur, année, langue, source, url, acces).

    {_CONSIGNE_SOURCES}

    Écris le lien de chaque document en markdown [titre](url) avec l'url
    exacte du résultat, sans jamais l'inventer ni la modifier. Indique la
    source du document quand c'est utile. Le champ acces est une indication,
    la page du document fait foi : "libre" veut dire consultable directement ;
    "pret_numerique" veut dire un livre encore sous droits, que l'étudiant ne
    peut lire qu'en l'empruntant avec un compte gratuit sur la source, et dont
    Classinus ne peut pas lire le contenu (dis le clairement) ; "restreint"
    veut dire non consultable.

    Pour les documents d'Internet Archive, deux liens sont possibles. url est
    la page sur le site d'Internet Archive. url_pdf, quand il est présent,
    ouvre le PDF directement dans le visionneur de Classinus : l'étudiant reste
    dans l'appli, c'est le lien à mettre en avant. Donne les deux, chacun en
    markdown [titre](adresse) avec l'adresse exacte, sans la modifier. Quand il
    n'y a pas url_pdf, le champ note_pdf dit pourquoi : transmets cette mention
    à l'étudiant avec des mots simples, sans inventer de lien.

    Cet outil trouve et donne le lien, il ne lit pas le contenu du document.
    Pour lire le texte d'un document Internet Archive, utilise ensuite
    lire_document_internet_archive. Les documents des autres sources ne
    peuvent pas être lus pour l'instant : donne seulement leur lien, et ne
    prétends jamais avoir lu un livre que tu as seulement trouvé. Si rien
    n'est trouvé, dis le et propose de reformuler (autre titre, nom de
    l'auteur, autre langue). Paramètres : requete (mots clés de la recherche),
    source (nom de la source indiquée par l'étudiant, vide par défaut),
    nombre (6 par défaut, 15 au maximum).
    """

mcp_generation.tool()(rechercher_document_externe)
