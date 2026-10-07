"""
Outil MCP lire_video : lecture de ce qui est dit dans une vidéo YouTube
(07/10/2026, demande Bourama, étape 2 de la recherche de vidéos).

La logique est dans core/lecture_video.py. Ce fichier ne fait que déclarer
l'outil sur `mcp_generation`, comme rechercher_video (core/outils_generation_media.py),
et son chargement se fait par l'import dans core/serveur_mcp_generation.py.

Outil de LECTURE : le texte complet est renvoyé au modèle, qui en a besoin
pour répondre (contrairement aux outils de génération, qui ne renvoient
qu'une confirmation).
"""

import logging

from core.lecture_video import lire_contenu_video as _lire_contenu_video
from core.outils_generation_commun import mcp_generation


@mcp_generation.tool()
def lire_video(url: str, a_partir_de_minute: int = 0) -> str:
    """
    Lit ce qui est DIT dans une vidéo YouTube (ses sous-titres), pour
    répondre à une question sur la vidéo, la résumer, l'expliquer ou en
    citer un passage. À utiliser dès que tu as besoin du contenu d'une vidéo
    (une vidéo trouvée par rechercher_video ou dont on te donne le lien) :
    n'utilise PAS tavily_extract ni tavily_research pour une vidéo YouTube,
    ils ne donnent pas ce qui est dit dedans. Renvoie le texte parlé avec des
    repères [m:ss]. Une vidéo longue est lue par tranches : si la réponse
    indique de rappeler l'outil, fais-le avec a_partir_de_minute pour lire la
    suite avant de conclure. Si la vidéo est illisible (pas de sous-titres,
    privée...), l'outil te le dit : transmets-le clairement à l'étudiant sans
    rien inventer. Paramètres : url (adresse de la vidéo), a_partir_de_minute
    (0 pour commencer au début).
    """
    try:
        return _lire_contenu_video(url, a_partir_de_minute)
    except Exception as e:
        logging.error(f"ERREUR outil lecture vidéo : {e}")
        return "Erreur : la lecture de la vidéo a échoué, réessaie."
