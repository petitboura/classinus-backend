"""
Outil MCP lire_document_conversation : lecture, À LA DEMANDE DU MODÈLE, d'un document
joint par l'étudiant à la conversation (27/10/2026, demande Bourama).

La logique est dans core/lecture_document_conversation.py. Ce fichier ne fait que
déclarer l'outil sur `mcp_generation`, comme lire_media_conversation
(core/outils_lecture_media.py), et son chargement se fait par l'import dans
core/serveur_mcp_generation.py.

Outil de LECTURE : le texte est renvoyé au modèle, qui en a besoin pour répondre.
Il ne modifie jamais le fichier d'origine.
"""

import logging

from core.lecture_document_conversation import lire_document as _lire_document
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def lire_document_conversation(
    ctx: Context,
    url_fichier: str,
    mode: str = "infos",
    debut_page: int = 0,
    fin_page: int = 0,
    debut_caractere: int = 0,
    recherche: str = "",
) -> str:
    """
    Lit un DOCUMENT que l'étudiant a joint à la conversation (PDF, Word, Excel,
    PowerPoint, texte, code, ancien format Office). Ces fichiers ne sont PAS lus
    automatiquement : le message ne contient que leur nom, leur type, leur taille et
    leur nombre de pages, avec leur lien réel entre crochets. C'est à toi de décider
    si tu as besoin de leur contenu pour répondre, et de quelle partie.

    `url_fichier` : le lien réel du fichier, visible entre crochets juste après
    « [Lien réel du fichier : ... ] » (jamais inventé).

    `mode` doit être l'un de :
    - "infos" : seulement les informations (type, taille, nombre de pages, feuilles).
    - "texte" : le texte, depuis le début ou depuis `debut_page` / `debut_caractere`.
    - "pages" : un intervalle de pages (PDF) ou de diapositives (PowerPoint), avec
      `debut_page` et `fin_page` (0 pour fin = jusqu'à la fin, dans la limite d'un appel).
    - "recherche" : les passages qui contiennent le mot ou l'expression donnée dans
      `recherche`, avec leur page. À utiliser sur un long document pour trouver
      un passage avant de le lire, plutôt que de tout lire.

    Un long document est lu par tranches : si la réponse t'indique de rappeler l'outil
    (avec un nouveau `debut_page` ou `debut_caractere`), fais-le avant de conclure si tu
    as besoin du reste. Une page sans texte natif (scan) est lue par reconnaissance de
    texte, seulement quand tu la demandes.

    Pour TRAVAILLER sur ce fichier avec du code (convertir, calculer, tracer, transformer),
    ne le lis pas ici : copie-le d'abord dans l'espace d'exécution de code avec
    gerer_execution_code, action importer_fichier. Pour une vidéo ou un audio, utilise
    lire_media_conversation.

    Si le fichier est illisible, dis-le clairement à l'étudiant sans rien inventer.
    """
    if ctx is None:
        return "Erreur : contexte manquant."
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        return _lire_document(url_fichier, user_id, mode, debut_page, fin_page, debut_caractere, recherche)
    except Exception as e:
        logging.error(f"ERREUR outil lire_document_conversation : {e}")
        return "Erreur : la lecture du fichier a échoué, réessaie."
