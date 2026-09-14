"""
Outil MCP dédié aux fichiers UPLOADÉS PAR L'ÉTUDIANT en pièce jointe de
conversation (document, image, audio, vidéo -- origine="chat"), SÉPARÉ
de gerer_document_bibliotheque (core/outils_bibliotheque.py) qui couvre
la bibliothèque "officielle" (ajouts manuels + générations IA).

Ajouté le 14/09/2026 (demande Bourama). Contexte : ces fichiers ont
souvent un nom d'origine inexploitable pour une recherche ("IMG_2384.pdf",
"scan001.pdf"), contrairement à un document de la bibliothèque
(toujours nommé au moment de l'ajout) ou une génération IA (toujours
nommée par le modèle, voir core/outils_generation_documents.py et
core/outils_generation_media.py). Décision Bourama : c'est au modèle de
juger si le nom d'origine est exploitable, et de le renommer sinon --
UN SEUL mécanisme générique, valable pour N'IMPORTE QUEL type de
fichier qui passe par le chemin upload en chat (api/uploads.py),
aujourd'hui ET pour un futur type d'upload, sans rien à recoder ici :
cet outil ne connaît que url_fichier/nom, jamais un détail propre à un
type de fichier précis.

Remplace aussi l'ancien outil "chercher_fichier" (retiré le 14/09/2026,
voir core/outils_bibliotheque.py) qui demandait au modèle de fournir
lui-même agent_id/user_id -- jamais communiqués nulle part dans ses
instructions système, donc toujours vide en pratique. Ici, user_id
vient de `ctx` (authentifié côté serveur), jamais demandé au modèle.
"""

import logging

from core.bibliotheque_fichiers import (
    chercher_fichiers as _chercher_fichiers,
    renommer_fichier_par_url as _renommer_fichier_par_url,
)
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def gerer_fichier_conversation(action: str, ctx: Context, url_fichier: str = "", nom: str = "", recherche: str = "") -> str:
    """
    Gère les fichiers UPLOADÉS PAR L'ÉTUDIANT en pièce jointe de cette
    conversation (document, image, audio, vidéo -- n'importe quel type
    qui passe par la case upload en chat), séparé de
    gerer_document_bibliotheque qui couvre la bibliothèque
    "officielle" (ajouts manuels + générations IA). Ces fichiers ont
    souvent un nom d'origine inexploitable pour les retrouver plus
    tard (ex. "IMG_2384.pdf", "scan001.pdf") : c'est à toi de juger.

    `action` doit être l'une de :
    - "nommer" : à faire JUSTE APRÈS chaque upload d'un fichier en
      conversation, AVANT même que l'étudiant ne demande quoi que ce
      soit -- tu vois déjà le nom d'origine ET le contenu (texte
      extrait, transcription, ou description de l'image) dans le même
      message. Si le nom d'origine décrit déjà bien le contenu,
      renomme-le quand même avec ce même nom (obligatoire dans tous
      les cas, jamais sauté). Sinon, choisis un vrai nom court et
      clair basé sur le contenu, avec la bonne extension. Paramètres :
      `url_fichier` (le lien réel du fichier, visible entre crochets
      juste après son upload -- jamais inventé), `nom` (le nom choisi,
      avec son extension).
    - "chercher" : retrouve un fichier uploadé plus tôt dans cette
      conversation par son nom (celui donné via "nommer" ci-dessus).
      À utiliser si son lien n'est plus visible plus haut dans la
      conversation. Paramètre : `recherche` (mot-clé).
    """
    if ctx is None:
        return "Erreur : contexte manquant."
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."

    if action == "nommer":
        url_val = (url_fichier or "").strip()
        nom_val = (nom or "").strip()
        if not url_val or not nom_val:
            return "Erreur : url_fichier et nom sont obligatoires pour \"nommer\"."
        try:
            ligne = _renommer_fichier_par_url(url_val, nom_val, user_id)
        except Exception as e:
            logging.error(f"ERREUR gerer_fichier_conversation (nommer) : {e}")
            return "Erreur : impossible de nommer ce fichier, réessaie."
        if ligne is None:
            return "Erreur : ce fichier est introuvable, ou ne t'appartient pas."
        return f"Fichier nommé « {nom_val} »."

    if action == "chercher":
        recherche_val = (recherche or "").strip()
        if not recherche_val:
            return "Erreur : recherche manquante pour \"chercher\"."
        try:
            resultats = _chercher_fichiers(recherche_val, user_id=user_id, origine="chat")
        except Exception as e:
            logging.error(f"ERREUR gerer_fichier_conversation (chercher) : {e}")
            return "Erreur : la recherche a échoué, réessaie."
        if not resultats:
            return "Aucun fichier de conversation trouvé pour cette recherche."
        return "\n".join(
            f"- {f.get('description') or f.get('nom_fichier')} ({f.get('type_mime', 'inconnu')}) : {f['url_publique']}"
            for f in resultats
        )

    return "Erreur : action inconnue. Actions valides : nommer, chercher."
