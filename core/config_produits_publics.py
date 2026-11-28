"""Réglages des produits publics (28/11/2026, demande de Bourama).

Toutes les limites sont ici et peuvent être changées par variable d'environnement, sans toucher
au code des routes. Un produit public est publié tout de suite par n'importe quel compte, puis
retiré après signalement : ces plafonds limitent les abus sans validation préalable.
"""
import os


def _entier_env(nom: str, defaut: int) -> int:
    try:
        return int(os.getenv(nom, "") or defaut)
    except ValueError:
        return defaut


# Bucket R2 logique où vivent les images (le même que les images publiques du chat).
BUCKET_IMAGES = "images-publiques"
# Dossier des images d'un produit dans ce bucket : produits/<id du compte>/<fichier>.
DOSSIER_IMAGES = "produits"

TYPES_PRODUIT = ("site", "appli", "plateforme")

NOM_MIN, NOM_MAX = 2, 80
ACCROCHE_MIN, ACCROCHE_MAX = 5, 140
DESCRIPTION_MAX = 5000
URL_MAX = 500
ETIQUETTE_MIN, ETIQUETTE_MAX = 2, 24
ETIQUETTES_MAX = 5

IMAGES_MAX = _entier_env("PRODUITS_PUBLICS_IMAGES_MAX", 8)
PRODUITS_PAR_COMPTE_MAX = _entier_env("PRODUITS_PUBLICS_PAR_COMPTE_MAX", 20)

# Images envoyées par le créateur.
IMAGE_TAILLE_MAX_OCTETS = _entier_env("PRODUITS_PUBLICS_IMAGE_TAILLE_MAX_OCTETS", 8 * 1024 * 1024)
IMAGE_LARGEUR_MAX = _entier_env("PRODUITS_PUBLICS_IMAGE_LARGEUR_MAX", 1800)
LOGO_COTE_MAX = _entier_env("PRODUITS_PUBLICS_LOGO_COTE_MAX", 512)
TYPES_IMAGE_ACCEPTES = ("image/png", "image/jpeg", "image/webp")

# Capture automatique du site : bureau puis téléphone.
CAPTURES_PAR_HEURE_ET_COMPTE = _entier_env("PRODUITS_PUBLICS_CAPTURES_PAR_HEURE", 12)
CAPTURES_SIMULTANEES_MAX = _entier_env("PRODUITS_PUBLICS_CAPTURES_SIMULTANEES", 2)
CAPTURE_DELAI_CHARGEMENT_S = _entier_env("PRODUITS_PUBLICS_CAPTURE_DELAI_S", 20)
CAPTURE_ATTENTE_APRES_CHARGEMENT_MS = _entier_env("PRODUITS_PUBLICS_CAPTURE_ATTENTE_MS", 1500)
CAPTURE_BUREAU = (1440, 900)
CAPTURE_TELEPHONE = (390, 844)

# Liste publique.
LISTE_LIMITE_DEFAUT = 24
LISTE_LIMITE_MAX = 60
RECHERCHE_MOTS_MAX = 5
