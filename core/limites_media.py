"""
Limites des vidéos et audios joints à une conversation (26/10/2026, demande
Bourama : « les limites pour l'instant non, mais qu'elles soient modifiables
rapidement »).

Les valeurs par défaut sont EXACTEMENT celles qui existaient en dur dans
api/uploads.py (vidéo 40 Mo et 120 s, audio 20 Mo). Pour les changer, il suffit
de modifier une variable d'environnement sur Railway puis de redéployer, sans
toucher au code :

- MEDIA_VIDEO_TAILLE_MAX_MO : taille maximale d'une vidéo jointe (40 par défaut)
- MEDIA_VIDEO_DUREE_MAX_SECONDES : durée maximale d'une vidéo jointe (120 par défaut)
- MEDIA_AUDIO_TAILLE_MAX_MO : taille maximale d'un audio joint (20 par défaut)
- MEDIA_TRANCHE_TRANSCRIPTION_SECONDES : durée transcrite par appel de l'outil
  lire_media_conversation (600 par défaut, soit environ 19 Mo de wav 16 kHz mono,
  sous la limite de 25 Mo de Groq)
- MEDIA_IMAGES_MAX : nombre maximal d'images décrites par appel (8 par défaut)

Une valeur absente, vide ou invalide retombe sur le défaut (jamais d'erreur au
démarrage).
"""

import os


def _entier_env(nom: str, defaut: int) -> int:
    try:
        valeur = int(os.environ.get(nom, "").strip())
    except (ValueError, AttributeError):
        return defaut
    return valeur if valeur > 0 else defaut


def taille_max_video_octets() -> int:
    return _entier_env("MEDIA_VIDEO_TAILLE_MAX_MO", 40) * 1024 * 1024


def duree_max_video_secondes() -> int:
    return _entier_env("MEDIA_VIDEO_DUREE_MAX_SECONDES", 120)


def taille_max_audio_octets() -> int:
    return _entier_env("MEDIA_AUDIO_TAILLE_MAX_MO", 20) * 1024 * 1024


def tranche_transcription_secondes() -> int:
    return _entier_env("MEDIA_TRANCHE_TRANSCRIPTION_SECONDES", 600)


def images_max_par_appel() -> int:
    return _entier_env("MEDIA_IMAGES_MAX", 8)


# Documents et fichiers joints lus à la demande de l'IA (27/10/2026, demande
# Bourama) : mêmes règles que les médias, valeurs modifiables par variable
# d'environnement, valeur absente ou invalide = défaut.
#
# - DOCUMENT_TRANCHE_CARACTERES : texte renvoyé par appel de lire_document_conversation
#   (30000 par défaut, la même taille que l'ancienne lecture à l'envoi)
# - DOCUMENT_PAGES_MAX_PAR_APPEL : nombre maximal de pages lues par appel (15 par défaut)
# - DOCUMENT_RECHERCHE_RESULTATS_MAX : nombre maximal d'extraits renvoyés par une recherche (20 par défaut)
# - EXECUTION_CODE_IMPORT_TAILLE_MAX_MO : taille maximale d'un fichier joint copié dans
#   l'espace d'exécution de code (15 par défaut, la limite d'envoi d'un document)


def tranche_document_caracteres() -> int:
    return _entier_env("DOCUMENT_TRANCHE_CARACTERES", 30000)


def pages_max_par_appel_document() -> int:
    return _entier_env("DOCUMENT_PAGES_MAX_PAR_APPEL", 15)


def resultats_max_recherche_document() -> int:
    return _entier_env("DOCUMENT_RECHERCHE_RESULTATS_MAX", 20)


def taille_max_import_code_octets() -> int:
    return _entier_env("EXECUTION_CODE_IMPORT_TAILLE_MAX_MO", 15) * 1024 * 1024
