"""
Réglages du rendu vidéo des animations du chat (07/10/2026, demande
Bourama : télécharger une animation guidée en vidéo, y compris en 9:16,
sans faire travailler le navigateur de l'utilisateur, donc aussi sur
téléphone).

Une seule source pour les valeurs : rien n'est écrit en dur dans les
autres modules du rendu (core/rendu_animation_travaux.py,
core/rendu_animation_processus.py, api/rendu_animation.py).
"""

import os
import tempfile
from pathlib import Path

# Formats proposés et taille de la vidéo (largeur, hauteur) en pixels.
# Les clés doivent rester celles du frontend (classinus-frontend,
# components/chat/animation/styleRenduVideo.ts) : le document HTML envoyé
# par l'appli est déjà mis en page pour son format.
FORMATS: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}

IMAGES_PAR_SECONDE = 30

# Durée maximale d'une animation convertie en vidéo, en secondes. Au delà,
# le rendu serait trop long pour un serveur partagé. Le message d'erreur
# RENDU_VIDEO_TROP_LONGUE (core/erreurs.py) annonce la même limite.
DUREE_MAX_S = 120

# Image finale gardée à l'écran après la fin de l'animation, en secondes,
# pour que le résultat reste lisible dans la vidéo.
MAINTIEN_FIN_S = 1.0

# Taille maximale du document HTML reçu (code de l'animation compris).
TAILLE_MAX_DOCUMENT_OCTETS = 1_500_000

# Temps laissé à la page pour être prête (chargement de three.js compris).
DELAI_CHARGEMENT_S = 20

# Temps maximal d'un rendu complet. Passé ce délai, le processus est tué.
DELAI_TOTAL_S = 15 * 60

# Durée pendant laquelle une vidéo terminée reste téléchargeable.
CONSERVATION_S = 30 * 60

# Rendus lancés en même temps (le rendu occupe beaucoup le processeur) et
# nombre maximal de demandes en attente derrière eux.
TRAVAUX_SIMULTANES = max(1, int(os.environ.get("RENDU_ANIMATION_SIMULTANES", "1")))
ATTENTE_MAX = max(1, int(os.environ.get("RENDU_ANIMATION_ATTENTE_MAX", "5")))

DOSSIER_TRAVAIL = Path(tempfile.gettempdir()) / "classinus-rendu-animation"
SCRIPT_PROCESSUS = Path(__file__).with_name("rendu_animation_processus.py")

# Copie locale de three.js (même version que le frontend, voir
# construireDocumentAnimation.ts). Le navigateur du rendu n'a AUCUN accès au
# réseau : cette copie lui est servie à la place du CDN.
FICHIER_THREE = Path(__file__).parent / "ressources_rendu_animation" / "three.r128.min.js"
