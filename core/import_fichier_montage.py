"""
Pont entre les fichiers joints du chat et les outils de montage vidéo
(26/10/2026, demande Bourama).

Les outils de montage (core/serveur_mcp_video.py) ne travaillent QUE sur des
fichiers du dossier de la conversation (uploads/<id>.<ext>) : les adresses
internet leur sont refusées. Or une vidéo, un audio ou une image joints avec le
« + » restent dans la bibliothèque de l'étudiant et n'arrivaient jamais dans ce
dossier (seul le panneau d'édition vidéo y déposait une vidéo). Ce module copie
un fichier joint dans le dossier de la conversation, au même endroit et avec le
même stockage durable que le panneau d'édition, et renvoie son chemin.

Sécurité : le fichier est retrouvé par son lien réel ET par le compte de
l'utilisateur ET par l'origine « chat » (core/lecture_media_conversation.py:
retrouver_fichier). Un lien inventé ou appartenant à un autre compte ne donne
rien. Le résultat est toujours un dictionnaire, jamais une exception.
"""

import logging
import mimetypes
import os
import tempfile

from core.lecture_media_conversation import lire_infos, retrouver_fichier
from core.video_workspaces import EXTENSIONS_MIME, enregistrer_video, mime_canonique


def importer_fichier_conversation(user_id: str, conversation_id: str, url_fichier: str) -> dict:
    url_fichier = (url_fichier or "").strip()
    if not url_fichier:
        return {"success": False, "error": "url_fichier manquant (le lien réel indiqué juste après le fichier joint)."}

    try:
        trouve = retrouver_fichier(url_fichier, user_id)
    except Exception as e:
        logging.error(f"ERREUR lecture du fichier joint pour le montage : {e}")
        return {"success": False, "error": "Impossible de relire ce fichier, réessaie."}
    if trouve is None:
        return {"success": False, "error": "Ce fichier est introuvable, ou ne t'appartient pas."}
    ligne, contenu = trouve

    nom = ligne.get("nom_fichier") or "fichier"
    mime = mime_canonique(ligne.get("type_mime") or mimetypes.guess_type(nom)[0] or "")
    if mime not in EXTENSIONS_MIME:
        return {
            "success": False,
            "error": "Seuls une vidéo, un audio ou une image peuvent être importés pour le montage.",
        }
    type_media = mime.split("/")[0]
    extension = EXTENSIONS_MIME[mime]

    duree = None
    if type_media in ("video", "audio"):
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporaire:
            temporaire.write(contenu)
            chemin_temporaire = temporaire.name
        try:
            duree = lire_infos(chemin_temporaire, len(contenu))["duree_secondes"]
        except Exception as e:
            logging.error(f"ERREUR ffprobe import montage ({nom}) : {e}")
            return {"success": False, "error": "Ce fichier n'est pas un média lisible."}
        finally:
            if os.path.exists(chemin_temporaire):
                os.remove(chemin_temporaire)

    try:
        meta = enregistrer_video(
            user_id=user_id, conversation_id=conversation_id, nom=nom,
            mime=mime, contenu=contenu, duree_secondes=duree,
        )
    except Exception as e:
        logging.error(f"ERREUR import montage ({nom}) : {e}")
        return {"success": False, "error": "Le stockage du fichier est indisponible, réessaie dans un instant."}

    return {
        "success": True,
        "type": type_media,
        "nom_fichier": meta["nom_fichier"],
        "source_path": f"uploads/{meta['video_id']}{extension}",
        "duree_secondes": meta.get("duree_secondes"),
        "taille_octets": meta["taille_octets"],
        "consigne": (
            "Utilise source_path comme entrée des outils de montage. Il est en lecture seule : "
            "écris chaque résultat dans outputs/ pour conserver l'original."
        ),
    }
