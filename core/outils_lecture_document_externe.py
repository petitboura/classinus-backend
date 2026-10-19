"""
Outil MCP lire_document_externe : lecture du texte d'un fichier (PDF, Word,
Excel, PowerPoint, texte) à partir de son lien direct, quelle que soit sa
source (10/10/2026, demande Bourama, lecteur unique).

La logique est dans core/lecture_document_externe.py. Ce fichier ne fait que
déclarer l'outil sur `mcp_generation`, comme lire_document_internet_archive
(core/outils_lecture_document_archive.py), et son chargement se fait par
l'import dans core/serveur_mcp_generation.py.

Outil de LECTURE : le texte est renvoyé au modèle, qui en a besoin pour
répondre.

Pas exposé sur le serveur MCP public (core/serveur_mcp_espace.py) : décision
à demander explicitement à Bourama, voir la règle en tête de
core/serveur_mcp_generation.py.
"""

import logging

from core.lecture_document_externe import lire_document_externe as _lire_document_externe
from core.outils_generation_commun import mcp_generation


@mcp_generation.tool()
def lire_document_externe(url: str, a_partir_du_caractere: int = 0, rechercher: str = "") -> str:
    """
    Lit le TEXTE d'un fichier (PDF, Word, Excel, PowerPoint ou texte) à partir
    de son lien direct, pour répondre à une question sur le document, le
    résumer, l'expliquer ou en citer un passage. À utiliser quand tu as
    besoin du contenu d'un document qui n'est pas sur Internet Archive : un
    document trouvé par rechercher_document_externe avec un champ url_fichier
    (utilise cette adresse exacte), ou un lien direct vers un fichier donné
    par l'étudiant. Appelle-le avant de répondre, sans jamais deviner ce que
    le document contient. Pour un document Internet Archive, utilise plutôt
    lire_document_internet_archive. Cet outil ne lit pas une page web : si
    l'adresse mène à une page, la réponse te le dit. Un document long est lu
    par tranches : si la réponse indique de rappeler l'outil, fais-le avec
    a_partir_du_caractere pour lire la suite avant de conclure. Pour trouver
    un passage précis dans un livre long sans tout lire, passe le mot ou
    l'expression cherchée dans rechercher : la réponse donne les passages
    trouvés avec leur position. Le texte d'un scan peut contenir des erreurs
    de lecture, et un PDF scanné très long n'est lu qu'en partie : la réponse
    le précise. Donne toujours le lien du fichier dans ta réponse. Si le
    fichier est en accès réservé, trop gros ou illisible, la réponse te le
    dit : dis-le clairement à l'étudiant avec le lien, sans rien inventer.
    Une image, un son, une vidéo, un livre numérique ou une archive n'ont pas
    de texte à lire ici : la réponse te le dit, donne alors seulement le lien
    à l'étudiant, sans rien affirmer sur leur contenu.
    Paramètres : url (lien direct du fichier), a_partir_du_caractere (0 pour
    commencer au début), rechercher (mot ou expression à trouver, vide pour
    lire le texte).
    """
    try:
        return _lire_document_externe(url, a_partir_du_caractere, rechercher)
    except Exception as e:
        logging.error(f"ERREUR outil lecture document externe : {e}")
        return "Erreur : la lecture du document a échoué, réessaie."
