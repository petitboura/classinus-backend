"""
Outil MCP lire_document_internet_archive : lecture du texte d'un livre ou
d'un PDF d'Internet Archive (09/10/2026, demande Bourama, lot 2 du chantier
Internet Archive).

La logique est dans core/lecture_document_archive.py. Ce fichier ne fait que
déclarer l'outil sur `mcp_generation`, comme lire_video
(core/outils_lecture_video.py), et son chargement se fait par l'import dans
core/serveur_mcp_generation.py.

Outil de LECTURE : le texte est renvoyé au modèle, qui en a besoin pour
répondre (contrairement aux outils de génération, qui ne renvoient qu'une
confirmation).

Pas exposé sur le serveur MCP public (core/serveur_mcp_espace.py) : décision
à demander explicitement à Bourama, voir la règle en tête de
core/serveur_mcp_generation.py.
"""

import logging

from core.lecture_document_archive import lire_document_archive as _lire_document_archive
from core.outils_generation_commun import mcp_generation


@mcp_generation.tool()
def lire_document_internet_archive(url: str, a_partir_du_caractere: int = 0, rechercher: str = "") -> str:
    """
    Lit le TEXTE d'un livre ou d'un PDF d'Internet Archive, pour répondre à
    une question sur le document, le résumer, l'expliquer ou en citer un
    passage. À utiliser dès que tu as besoin du contenu d'un document
    Internet Archive (un document trouvé par la recherche Internet Archive ou
    dont on te donne le lien archive.org) : appelle-le avant de répondre,
    sans jamais deviner ce que le document contient. Un document long est lu
    par tranches : si la réponse indique de rappeler l'outil, fais-le avec
    a_partir_du_caractere pour lire la suite avant de conclure. Pour trouver
    un passage précis dans un livre long sans tout lire, passe le mot ou
    l'expression cherchée dans rechercher : la réponse donne les passages
    trouvés avec leur position. Le texte vient d'une numérisation et peut
    contenir des erreurs de lecture. Donne toujours le lien de la page du
    document dans ta réponse. Si le document est en prêt numérique ou
    illisible, la réponse te le dit : dis-le clairement à l'étudiant avec le
    lien, sans rien inventer. Paramètres : url (adresse archive.org du
    document ou son identifiant), a_partir_du_caractere (0 pour commencer au
    début), rechercher (mot ou expression à trouver, vide pour lire le texte).
    """
    try:
        return _lire_document_archive(url, a_partir_du_caractere, rechercher)
    except Exception as e:
        logging.error(f"ERREUR outil lecture document Internet Archive : {e}")
        return "Erreur : la lecture du document a échoué, réessaie."
