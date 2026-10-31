"""Registre des capacites Higgsfield de Classinus.

Une seule source de verite pour le routeur : chaque capacite declare la voie
qui sait reellement l'executer. Regle de Bourama (31/10/2026) : l'API
Classinus passe toujours en premier ; notre MCP partage ne sert que pour les
fonctions absentes de l'API. Aucun equivalent invente : si aucune voie ne
sait faire, la capacite est indisponible.

Les noms d'outils MCP sont des candidats publics du MCP officiel : leur
presence reelle est verifiee en direct (tools/list) avant tout appel, jamais
supposee. Le compte MCP de l'utilisateur n'est pas dans ce registre : son
fonctionnement reste inchange.
"""


CAPACITES = [
    {
        "id": "video",
        "label": "Video (texte, image animee, references)",
        "famille": "generation",
        "voie": "api",
        "modeles_api": ["seedance", "kling"],
        "outils_mcp": [],
        "medias_requis": [],
    },
    {
        "id": "image",
        "label": "Image (generation et edition par references)",
        "famille": "generation",
        "voie": "api",
        "modeles_api": ["grok"],
        "outils_mcp": [],
        "medias_requis": [],
    },
    {
        "id": "audio_tts",
        "label": "Audio : texte vers voix",
        "famille": "generation",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["generate_audio", "generate_audio_batch", "list_voices"],
        "medias_requis": [],
    },
    {
        "id": "clonage_voix",
        "label": "Clonage de voix",
        "famille": "generation",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["create_voice", "create_voice_from_confirmed_audio"],
        "medias_requis": ["audio"],
    },
    {
        "id": "voice_change",
        "label": "Remplacement de voix sur video",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["voice_change"],
        "medias_requis": ["video"],
    },
    {
        "id": "doublage",
        "label": "Doublage video traduit avec lip-sync",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["dubbing"],
        "medias_requis": ["video"],
    },
    {
        "id": "generation_3d",
        "label": "Generation 3D (mesh GLB)",
        "famille": "generation",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["generate_3d", "animation_actions"],
        "medias_requis": [],
    },
    {
        "id": "scene_3d",
        "label": "3D Jutsu : scenes, assets et apercu",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": [
            "scene_builder_3d_create_project", "scene_builder_3d_import_asset",
            "scene_builder_3d_get_glb", "scene_builder_3d_get_blend",
            "scene_builder_3d_show_scene", "scene_builder_3d_list_projects",
            "scene_builder_3d_list_generations",
        ],
        "medias_requis": [],
    },
    {
        "id": "upscale_image",
        "label": "Agrandissement d'image",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["upscale_image"],
        "medias_requis": ["image"],
    },
    {
        "id": "upscale_video",
        "label": "Agrandissement de video",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["upscale_video"],
        "medias_requis": ["video"],
    },
    {
        "id": "suppression_fond",
        "label": "Suppression de fond (image et video)",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["remove_background"],
        "medias_requis": ["image ou video"],
    },
    {
        "id": "outpaint",
        "label": "Extension d'image (outpaint)",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["outpaint_image"],
        "medias_requis": ["image"],
    },
    {
        "id": "reframe",
        "label": "Recadrage video vers un autre format",
        "famille": "edition",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["reframe"],
        "medias_requis": ["video"],
    },
    {
        "id": "shorts_studio",
        "label": "Shorts Studio : clips courts depuis une video",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": [
            "shorts_studio_create", "shorts_studio_create_preset",
            "shorts_studio_list_presets", "shorts_studio_list_sessions",
            "shorts_studio_status",
        ],
        "medias_requis": ["video"],
    },
    {
        "id": "personal_clipper",
        "label": "Personal Clipper : YouTube vers clips",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": [
            "personal_clipper_create", "personal_clipper_jobs",
            "personal_clipper_status",
        ],
        "medias_requis": ["lien YouTube"],
    },
    {
        "id": "analyse_video",
        "label": "Analyse video scene par scene",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": [
            "video_analysis_create", "video_analysis_jobs", "video_analysis_status",
        ],
        "medias_requis": ["video"],
    },
    {
        "id": "viralite",
        "label": "Prediction de viralite",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": ["virality_predictor"],
        "medias_requis": ["video"],
    },
    {
        "id": "marketing_studio",
        "label": "Marketing Studio complet (presets, avatars, video)",
        "famille": "studio",
        "voie": "mcp",
        "modeles_api": [],
        "outils_mcp": [
            "show_marketing_studio_v2", "marketing_studio_v2_presets",
            "marketing_studio_v2_avatars", "marketing_studio_v2_create",
            "marketing_studio_v2_status",
        ],
        "medias_requis": [],
    },
]

_PAR_ID = {c["id"]: c for c in CAPACITES}

# Outils MCP autorises sur le compte partage : union des candidats du
# registre. Tout outil absent de cette liste est refuse, meme s'il existe
# sur le serveur (pas d'acces libre au compte Classinus).
OUTILS_MCP_AUTORISES = frozenset(
    outil for capacite in CAPACITES for outil in capacite["outils_mcp"]
)


def capacite_par_id(identifiant):
    return _PAR_ID.get((identifiant or "").strip().lower())


def capacites_par_voie(voie):
    return [c for c in CAPACITES if c["voie"] == voie]
