"""
Outil MCP lire_media_conversation : lecture, À LA DEMANDE DU MODÈLE, d'une vidéo ou
d'un audio joint par l'étudiant à la conversation (26/10/2026, demande Bourama).

La logique est dans core/lecture_media_conversation.py. Ce fichier ne fait que
déclarer l'outil sur `mcp_generation`, comme lire_video (core/outils_lecture_video.py),
et son chargement se fait par l'import dans core/serveur_mcp_generation.py.

Outil de LECTURE : le texte est renvoyé au modèle, qui en a besoin pour répondre.
"""

import logging

from core.lecture_media_conversation import lire_media as _lire_media
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def lire_media_conversation(
    ctx: Context,
    url_fichier: str,
    mode: str = "infos",
    debut_secondes: float = 0,
    fin_secondes: float = 0,
    nb_images: int = 5,
    langue: str = "",
) -> str:
    """
    Lit une VIDÉO ou un AUDIO que l'étudiant a joint à la conversation. Ces
    fichiers ne sont PAS lus automatiquement : le message ne contient que leur
    nom, leur durée, leur taille, leur résolution et si la vidéo a du son, avec
    leur lien réel entre crochets. C'est à toi de décider si tu as besoin de
    leur contenu pour répondre, et de quelle partie.

    `url_fichier` : le lien réel du fichier, visible entre crochets juste
    après « [Lien réel du fichier : ... ] » (jamais inventé).

    `mode` doit être l'un de :
    - "infos" : seulement les informations (durée, taille, résolution, son).
    - "transcription" : ce qui est DIT, avec des repères [m:ss]. À utiliser pour
      un cours, une explication, une interview, une dictée, un audio.
    - "images" : quelques images de la vidéo, décrites en texte, avec leur
      instant. À utiliser pour ce qui se VOIT : un schéma au tableau, une
      manipulation, un écran, une expérience. Inutile pour un audio.
    - "les_deux" : transcription puis images. À utiliser quand le son et
      l'image comptent tous les deux.

    Pour un passage précis, donne `debut_secondes` et `fin_secondes` (0 pour
    fin = jusqu'à la fin). Un média long est lu par tranches : si la réponse
    t'indique de rappeler l'outil, fais-le avec le nouveau `debut_secondes`
    avant de conclure. `nb_images` : nombre d'images à décrire (5 par défaut,
    1 pour regarder un instant précis avec `debut_secondes`). `langue` : code
    de langue (« fr », « en »...) seulement si la détection automatique se
    trompe, sinon laisse vide.

    Si le fichier est illisible ou sans son exploitable, dis-le clairement à
    l'étudiant sans rien inventer.
    """
    if ctx is None:
        return "Erreur : contexte manquant."
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        return _lire_media(url_fichier, user_id, mode, debut_secondes, fin_secondes or None, nb_images, langue)
    except Exception as e:
        logging.error(f"ERREUR outil lire_media_conversation : {e}")
        return "Erreur : la lecture du fichier a échoué, réessaie."
