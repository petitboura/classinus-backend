"""Catalogue des modèles Higgsfield ouverts par l'API (clé partagée).

Seuls les modèles dont le schéma a été lu dans la documentation officielle
(docs.higgsfield.ai, 25/10/2026) sont ici. Pour en ajouter un : une entrée de
plus dans MODELES_VIDEO ou MODELES_IMAGE, rien d'autre à toucher.

Chaque modèle vidéo a deux adresses : "texte" (vidéo depuis une description) et
"image" (vidéo depuis une image de départ). Les valeurs permises viennent du
schéma officiel de chaque adresse.
"""

MODELE_VIDEO_DEFAUT = "seedance"
MODELE_IMAGE_DEFAUT = "grok"

MODELES_VIDEO = {
    "seedance": {
        "label": "Seedance 2.0",
        "texte": "bytedance/seedance-2.0/text-to-video",
        "image": "bytedance/seedance-2.0/image-to-video",
        "duree": (4, 15),
        "duree_defaut": 5,
        # Format : seulement depuis du texte (avec une image, le cadrage suit l'image).
        "formats": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "qualites": ["480p", "720p", "1080p", "4k"],
        "qualite_defaut": "720p",
        "champ_son": "generate_audio",
        "son_booleen": True,
        "champ_image_fin": "end_image_url",
        "prompt_obligatoire_avec_image": False,
    },
    "kling": {
        "label": "Kling 3.0 Pro",
        "texte": "kling-video/v3.0/pro/text-to-video",
        "image": "kling-video/v3.0/pro/image-to-video",
        "duree": (3, 15),
        "duree_defaut": 5,
        "formats": ["16:9", "9:16", "1:1"],
        "qualites": None,
        "qualite_defaut": None,
        "champ_son": "sound",
        "son_booleen": False,
        "champ_image_fin": "last_image_url",
        "prompt_obligatoire_avec_image": True,
    },
}

MODELES_IMAGE = {
    "grok": {
        "label": "Grok Image 2.0",
        # Un seul point d'entrée : crée une image, ou en modifie jusqu'à 10 si on en donne.
        "endpoint": "xai/grok-imagine-image-2.0",
        "formats": ["auto", "1:1", "1:2", "2:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16"],
        "format_defaut": "auto",
        "qualites": ["1k", "2k"],
        "qualite_defaut": "1k",
        "max_references": 10,
    },
}


def noms_modeles_video() -> str:
    return ", ".join(MODELES_VIDEO)


def noms_modeles_image() -> str:
    return ", ".join(MODELES_IMAGE)
