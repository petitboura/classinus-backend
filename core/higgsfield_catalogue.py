"""Catalogue des modèles Higgsfield ouverts par l'API (clé partagée).

Seuls les modèles dont le schéma a été lu dans la documentation officielle
(docs.higgsfield.ai, 25/10/2026) sont ici. Pour en ajouter un : une entrée de
plus dans MODELES_VIDEO, MODELES_IMAGE ou MODELES_GENJUTSU, rien d'autre à toucher.

Chaque modèle vidéo a deux adresses : "texte" (vidéo depuis une description) et
"image" (vidéo depuis une image de départ), plus "reference" quand le modèle accepte
des références. Les valeurs permises viennent du
schéma officiel de chaque adresse. Genjutsu transforme une vidéo existante.
"""

MODELE_VIDEO_DEFAUT = "seedance"
MODELE_IMAGE_DEFAUT = "grok"
MODELE_GENJUTSU_DEFAUT = "genjutsu-motion"

MODELES_VIDEO = {
    "seedance": {
        "label": "Seedance 2.0",
        "texte": "bytedance/seedance-2.0/text-to-video",
        "image": "bytedance/seedance-2.0/image-to-video",
        "reference": "bytedance/seedance-2.0/reference-to-video",
        "max_references": {"images": 9, "videos": 3, "audios": 3},
        "duree": (4, 15),
        "duree_defaut": 5,
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
        "reference": None,
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
        "endpoint": "xai/grok-imagine-image-2.0",
        "formats": ["auto", "1:1", "1:2", "2:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16"],
        "format_defaut": "auto",
        "qualites": ["1k", "2k"],
        "qualite_defaut": "1k",
        "max_references": 10,
        "style": False,
    },
    # Soul 2.0 : portraits et mode. Schéma lu sur docs.higgsfield.ai le 07/11/2026.
    # Le style se choisit par un identifiant (style_id). Sans identifiant, Higgsfield
    # applique le style général, dont voici l'identifiant officiel. La documentation
    # ne prévoit pas d'image de référence envoyée : max_references vaut 0.
    "soul": {
        "label": "Soul 2.0",
        "endpoint": "higgsfield-ai/soul/v2/standard",
        "formats": ["1:1", "9:16", "16:9", "4:3", "3:4", "2:3", "3:2"],
        "format_defaut": "1:1",
        "qualites": ["720p", "1080p"],
        "qualite_defaut": "720p",
        "max_references": 0,
        "style": True,
        "style_defaut": "3db34ab5-3439-4317-9e03-08dc30852e69",
    },
}

# Genjutsu : transformation vidéo-à-vidéo (motion, object swap, restyle).
# Schémas lus sur open.higgsfield.ai le 01/11/2026.
MODELES_GENJUTSU = {
    "genjutsu-motion": {
        "label": "Genjutsu Motion Transfer",
        "endpoint": "higgsfield/genjutsu/motion-transfer/v1.0",
        "duree": (4, 30),
        "resolutions": ["480p", "720p", "1080p"],
        "resolution_defaut": "720p",
        "max_images": 8,
        "prompt_optionnel": True,
        "preset_requis": False,
        "light": False,
    },
    "genjutsu-object": {
        "label": "Genjutsu Object Swap",
        "endpoint": "higgsfield/genjutsu/object-swap/v1.0",
        "duree": (4, 30),
        "resolutions": ["480p", "720p", "1080p"],
        "resolution_defaut": "720p",
        "max_images": 8,
        "prompt_optionnel": True,
        "preset_requis": False,
        "light": False,
    },
    "genjutsu-restyle": {
        "label": "Genjutsu Restyle (preset)",
        "endpoint": "higgsfield/genjutsu/restyle/v1.0",
        "duree": (4, 30),
        "resolutions": ["480p", "720p", "1080p"],
        "resolution_defaut": "720p",
        "max_images": 5,
        "prompt_optionnel": True,
        "preset_requis": True,
        "light": False,
    },
    "genjutsu-light-motion": {
        "label": "Genjutsu Light Motion Transfer",
        "endpoint": "higgsfield/genjutsu-light/motion-transfer/v1.0",
        "duree": (4, 15),
        "resolutions": ["480p", "720p", "1080p"],
        "resolution_defaut": "720p",
        "max_images": 8,
        "prompt_optionnel": True,
        "preset_requis": False,
        "light": True,
    },
    "genjutsu-light-object": {
        "label": "Genjutsu Light Object Swap",
        "endpoint": "higgsfield/genjutsu-light/object-swap/v1.0",
        "duree": (4, 15),
        "resolutions": ["480p", "720p", "1080p"],
        "resolution_defaut": "720p",
        "max_images": 8,
        "prompt_optionnel": True,
        "preset_requis": False,
        "light": True,
    },
}


def noms_modeles_video() -> str:
    return ", ".join(MODELES_VIDEO)


def noms_modeles_image() -> str:
    return ", ".join(MODELES_IMAGE)


def noms_modeles_genjutsu() -> str:
    return ", ".join(MODELES_GENJUTSU)
