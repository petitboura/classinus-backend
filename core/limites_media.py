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
