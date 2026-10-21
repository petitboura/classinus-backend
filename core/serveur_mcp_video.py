"""Passerelle Classinus vers mcp-video, sécurisée par conversation.

Les 83 outils amont restent accessibles via video_lister_outils et
video_executer_outil : cela évite d'envoyer 83 schémas au modèle à chaque tour.
Tous les chemins sont bornés à l'espace de travail du propriétaire. Les résultats
vidéo sont publiés dans le stockage existant pour fournir un lien lisible par le web.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import importlib.util
import json
import logging
import mimetypes
import os
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer as FastMCP, Context

from core.video_workspaces import (
    chemin_interne,
    chemin_video,
    restaurer_workspace,
    synchroniser_workspace,
    workspace_dir,
)

def _installer_compat_fastmcp():
    """Adapte uniquement les décorateurs amont, sans remplacer le MCP 2.0 du backend.

    mcp-video 1.2.1 utilise mcp.server.fastmcp, absent de la version MCP 2.0
    déjà utilisée par Classinus. On ne sert pas ce FastMCP amont directement :
    on collecte ses fonctions et leurs schémas pour les exécuter derrière la
    passerelle sécurisée Classinus. Le serveur HTTP reste le MCPServer du
    backend, sans rétrograder la dépendance globale.
    """
    try:
        importlib.import_module("mcp.server.fastmcp")
        return
    except ModuleNotFoundError:
        pass

    import sys
    import types
    from typing import get_type_hints
    from pydantic import create_model

    class _OutilCompat:
        def __init__(self, fonction, nom: str | None = None, description: str | None = None):
            self.fn = fonction
            self.name = nom or fonction.__name__
            self.description = (description or fonction.__doc__ or "").strip()
            self.parameters = self._creer_schema(fonction)
            self.inputSchema = self.parameters

        @staticmethod
        def _creer_schema(fonction) -> dict:
            try:
                annotations = get_type_hints(fonction, include_extras=True)
            except Exception:
                annotations = {}
            champs = {}
            for parametre in inspect.signature(fonction).parameters.values():
                if parametre.name in {"ctx", "context"} or parametre.kind in {
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                }:
                    continue
                annotation = annotations.get(parametre.name, parametre.annotation)
                if annotation is inspect.Parameter.empty or isinstance(annotation, str):
                    annotation = Any
                defaut = ... if parametre.default is inspect.Parameter.empty else parametre.default
                champs[parametre.name] = (annotation, defaut)
            modele = create_model(f"{fonction.__name__.title().replace('_', '')}Arguments", **champs)
            return modele.model_json_schema()

    class _GestionnaireOutilsCompat:
        def __init__(self):
            self._tools: dict[str, _OutilCompat] = {}

    class _FastMCPCompat:
        def __init__(self, name: str, **kwargs):
            self.name = name
            self.instructions = kwargs.get("instructions")
            self._tool_manager = _GestionnaireOutilsCompat()

        def tool(self, name: str | None = None, description: str | None = None, **kwargs):
            # Supporte @mcp.tool et @mcp.tool() ; mcp-video utilise surtout
            # la seconde forme, mais cette compatibilité couvre les deux.
            if callable(name):
                fonction = name
                self._tool_manager._tools[fonction.__name__] = _OutilCompat(fonction, description=description)
                return fonction

            def enregistrer(fonction):
                outil = _OutilCompat(fonction, nom=name, description=description)
                self._tool_manager._tools[outil.name] = outil
                return fonction
            return enregistrer

        def resource(self, *args, **kwargs):
            # Les resources amont ne sont pas exposées par l'atelier Classinus ;
            # on préserve l'import des modules sans enregistrer d'endpoint amont.
            def decorateur(fonction):
                return fonction
            if args and callable(args[0]) and len(args) == 1:
                return args[0]
            return decorateur

        def prompt(self, *args, **kwargs):
            return self.resource(*args, **kwargs)

    module_compat = types.ModuleType("mcp.server.fastmcp")
    module_compat.FastMCP = _FastMCPCompat
    module_compat.__all__ = ["FastMCP"]
    sys.modules["mcp.server.fastmcp"] = module_compat
    serveur_mcp = sys.modules.get("mcp.server")
    if serveur_mcp is not None:
        setattr(serveur_mcp, "fastmcp", module_compat)


try:
    _installer_compat_fastmcp()
    from mcp_video import server as _source_server
    _SOURCE_TOOLS = getattr(getattr(_source_server.mcp, "_tool_manager", None), "_tools", {})
    if not isinstance(_SOURCE_TOOLS, dict) or not _SOURCE_TOOLS:
        raise RuntimeError("mcp-video n'a importé aucun outil.")
except Exception:  # le backend peut démarrer même si la dépendance est absente en dev
    logging.exception("Initialisation de mcp-video impossible.")
    _SOURCE_TOOLS = {}


mcp_video = FastMCP(name="classinus-video")
PATH_KEYS = {
    "input_path", "video_path", "audio_path", "image_path", "mask_path",
    "subtitle_path", "subtitle_file", "project_path", "project_dir",
    "font_path", "file_path", "source_path", "input", "video", "audio",
    "image", "clips", "images", "paths", "output_path", "output_dir",
}
EXTENSIONS_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
EXTENSIONS_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
EXTENSIONS_SORTIE = {".mp4", ".webm", ".mov", ".gif", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".srt", ".vtt", ".json"}

# Les capacités optionnelles très lourdes restent hors de l'image principale
# pour ne pas fragiliser le chat/Classinus lors d'un déploiement ordinaire.
# Elles sont activables via requirements-video-ai.txt après validation worker.
DEPENDANCES_OPTIONNELLES = {
    "video_ai_transcribe": [("whisper", "openai-whisper")],
    "video_ai_stem_separation": [
        ("demucs", "demucs"),
        ("torch", "torch"),
        ("torchaudio", "torchaudio"),
    ],
    "video_ai_upscale": [
        ("realesrgan", "realesrgan"),
        ("torch", "torch"),
        ("cv2", "opencv-contrib-python"),
    ],
}


def _dependances_manquantes(nom_outil: str) -> list[str]:
    manquantes = []
    for module, paquet in DEPENDANCES_OPTIONNELLES.get(nom_outil, []):
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            present = False
        if not present:
            manquantes.append(paquet)
    if nom_outil.startswith("remotion_"):
        for executable in ("node", "npm", "npx"):
            if shutil.which(executable) is None:
                manquantes.append(executable)
    return manquantes


def _context_owner(ctx: Context) -> tuple[str, str, Path]:
    request = ctx.request_context.request
    headers = request.headers
    attendu = os.environ.get("SUPABASE_SECRET", "")
    recu = (headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not attendu or not secrets.compare_digest(recu, attendu):
        raise PermissionError("Accès interne MCP refusé.")
    params = request.query_params
    user_id = params.get("user_id", "")
    conversation_id = params.get("conversation_id", "")
    if not user_id or not conversation_id:
        raise PermissionError("Montage vidéo disponible seulement dans une conversation authentifiée.")
    return user_id, conversation_id, workspace_dir(user_id, conversation_id)


def _tools_dict() -> dict:
    if isinstance(_SOURCE_TOOLS, dict):
        return _SOURCE_TOOLS
    return {getattr(tool, "name", ""): tool for tool in _SOURCE_TOOLS}


def _schema(tool: Any) -> dict:
    schema = getattr(tool, "parameters", None)
    if isinstance(schema, dict):
        return schema
    schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    metadata = getattr(tool, "fn_metadata", None)
    model = getattr(metadata, "arg_model", None)
    if model is not None:
        try:
            return model.model_json_schema()
        except Exception:
            pass
    return {"type": "object", "properties": {}}


def _description(tool: Any) -> str:
    return str(getattr(tool, "description", None) or getattr(tool, "__doc__", None) or "").strip()


@mcp_video.tool()
def video_lister_outils(ctx: Context, recherche: str = "") -> dict[str, Any]:
    """Découvre les capacités vidéo disponibles (montage, audio, effets, analyse, Remotion).

    recherche: mots décrivant la capacité recherchée (ex. 'crop zone', 'sous-titres',
    'transcription audio', 'Remotion motion graphics'). Vide pour lister les catégories.
    """
    _context_owner(ctx)
    tools = _tools_dict()
    if not tools:
        return {"success": False, "error": "mcp-video n'est pas installé ou ses outils n'ont pas pu être chargés."}
    query = (recherche or "").strip().lower()
    categories: dict[str, int] = {}
    for name, tool in tools.items():
        if name.startswith("remotion_"):
            category = "remotion"
        elif name.startswith(("audio_", "video_add_audio", "video_audio_")):
            category = "audio"
        elif name.startswith(("effect_", "transition_", "video_text_", "video_mograph_", "video_layout_")):
            category = "effets-et-motion-design"
        elif name.startswith(("image_",)):
            category = "image"
        elif name.startswith(("video_ai_", "video_analyze", "video_quality", "video_design", "video_fix")):
            category = "analyse-et-qualité-IA"
        else:
            category = "montage-video"
        categories[category] = categories.get(category, 0) + 1
    if not query:
        return {"success": True, "total_outils": len(tools), "categories": categories,
                "consigne": "Utilise recherche pour obtenir les outils et leurs schémas adaptés à la demande."}
    tokens = [word for word in query.split() if word]
    hits = []
    for name, tool in tools.items():
        text = f"{name} {_description(tool)}".lower()
        score = sum(1 for token in tokens if token in text)
        if score:
            hits.append((score, name, tool))
    hits.sort(key=lambda item: (-item[0], item[1]))
    return {
        "success": True,
        "total_outils": len(tools),
        "recherche": recherche,
        "outils": [
            {
                "nom": name,
                "description": _description(tool)[:1200],
                "schema": _schema(tool),
                "disponible": not _dependances_manquantes(name),
                "dependances_manquantes": _dependances_manquantes(name),
            }
            for _, name, tool in hits[:12]
        ],
        "suite_possible": len(hits) > 12,
        "note": (
            "Les outils avec disponible=false exigent les dependances indiquées. "
            "Ne les lance pas avant qu'elles soient installées."
        ),
    }


def _sortie_par_defaut(nom_outil: str, arguments: dict, root: Path) -> None:
    schema = _schema(_tools_dict().get(nom_outil))
    proprietes = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not isinstance(proprietes, dict):
        proprietes = {}
    cle_sortie = next((key for key in ("output_path", "output_file") if key in proprietes), None)
    if cle_sortie and not arguments.get(cle_sortie):
        if nom_outil in {"video_thumbnail", "video_extract_frame", "video_still", "remotion_still", "video_export_frames"} or nom_outil.startswith("image_"):
            extension = ".png"
        elif nom_outil.startswith("audio_") or nom_outil == "video_extract_audio":
            extension = ".wav"
        elif nom_outil in {"video_generate_subtitles", "video_text_subtitles"}:
            extension = ".srt"
        else:
            extension = ".mp4"
        dossier_sortie = root / "outputs"
        dossier_sortie.mkdir(parents=True, exist_ok=True)
        arguments[cle_sortie] = str(dossier_sortie / f"{nom_outil}_{uuid.uuid4().hex}{extension}")
    if "output_dir" in proprietes and not arguments.get("output_dir"):
        dossier = root / ("projects" if nom_outil == "remotion_create_project" else "outputs")
        dossier.mkdir(parents=True, exist_ok=True)
        arguments["output_dir"] = str(dossier / f"{nom_outil}_{uuid.uuid4().hex}")


def _cle_est_chemin(cle: str) -> bool:
    return (
        cle in PATH_KEYS
        or cle.endswith(("_path", "_file", "_dir", "_paths", "_files", "_video"))
        or cle.startswith("output_")
        or cle in {
            "input", "video", "audio", "image", "clips", "images", "paths",
            "project_root", "working_directory", "work_dir", "workspace_dir",
        }
    )


def _normaliser_arguments(nom_outil: str, arguments: dict, root: Path) -> dict:
    nettoyes = dict(arguments)
    _sortie_par_defaut(nom_outil, nettoyes, root)

    def normaliser(valeur: Any, cle: str = "") -> Any:
        if isinstance(valeur, str) and _cle_est_chemin(cle):
            est_sortie = cle.startswith("output_")
            est_projet = cle in {"output_dir", "project_path", "project_dir", "project_root"} or (
                nom_outil.startswith("remotion_") and est_sortie
            )
            return chemin_interne(root, valeur, sortie=est_sortie, projet=est_projet)
        if isinstance(valeur, list):
            return [normaliser(item, cle) for item in valeur]
        if isinstance(valeur, dict):
            return {key: normaliser(item, str(key)) for key, item in valeur.items()}
        return valeur

    # Valide aussi les chemins dans les listes/dictionnaires imbriqués, par
    # exemple les clips d'une séquence. Aucun outil ne peut sortir du workspace.
    nettoyes = {key: normaliser(value, key) for key, value in nettoyes.items() if value is not None}
    return nettoyes


def _restaurer_sources_dans_arguments(valeur: Any, user_id: str, conversation_id: str) -> None:
    """Restaure les sources R2 référencées par leur chemin relatif uploads/<uuid>.<ext>."""
    if isinstance(valeur, dict):
        for item in valeur.values():
            _restaurer_sources_dans_arguments(item, user_id, conversation_id)
        return
    if isinstance(valeur, list):
        for item in valeur:
            _restaurer_sources_dans_arguments(item, user_id, conversation_id)
        return
    if not isinstance(valeur, str):
        return
    normalise = valeur.replace("\\", "/")
    morceaux = normalise.split("/")
    if len(morceaux) != 2 or morceaux[0] != "uploads":
        return
    nom = Path(morceaux[1])
    if nom.suffix.lower() not in {".mp4", ".webm", ".mov"}:
        return
    if len(nom.stem) != 32 or any(c not in "0123456789abcdef" for c in nom.stem.lower()):
        return
    # Vérifie la propriété de la source par utilisateur + conversation et la
    # restaure sur l'instance Railway courante quand son cache local manque.
    chemin_video(user_id, conversation_id, nom.stem)


def _serialiser(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _serialiser(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialiser(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _chemins_sortie(value: Any, root: Path) -> list[Path]:
    trouves: list[Path] = []
    def parcourir(item: Any, cle: str = ""):
        if isinstance(item, dict):
            for k, v in item.items():
                parcourir(v, str(k))
        elif isinstance(item, (list, tuple)):
            for v in item:
                parcourir(v, cle)
        elif isinstance(item, str) and (cle in {"output_path", "output_file", "rendered_path"}):
            try:
                path = Path(item).resolve()
                sorties = (root / "outputs").resolve()
                if sorties in path.parents and path.is_file() and path.suffix.lower() in EXTENSIONS_SORTIE:
                    trouves.append(path)
            except Exception:
                pass
    parcourir(_serialiser(value))
    return list(dict.fromkeys(trouves))


def _sorties_depuis_arguments(arguments: dict, root: Path) -> list[Path]:
    """Récupère aussi les sorties explicites même si l'outil omet leur chemin dans son résultat."""
    candidates: list[Path] = []
    for key, value in arguments.items():
        if not key.startswith("output_") or key == "output_dir" or not isinstance(value, str):
            continue
        try:
            path = Path(value).resolve()
            outputs = (root / "outputs").resolve()
            if outputs in path.parents and path.is_file() and path.suffix.lower() in EXTENSIONS_SORTIE:
                candidates.append(path)
        except OSError:
            continue

    for key in ("output_dir",):
        value = arguments.get(key)
        if not isinstance(value, str):
            continue
        try:
            folder = Path(value).resolve()
            outputs = (root / "outputs").resolve()
            if outputs in folder.parents and folder.is_dir():
                for path in folder.rglob("*"):
                    if path.is_file() and path.suffix.lower() in EXTENSIONS_SORTIE:
                        candidates.append(path)
                        if len(candidates) >= 25:
                            break
        except OSError:
            continue
    return list(dict.fromkeys(candidates))


def _publier_sorties(paths: list[Path], user_id: str) -> list[dict[str, str]]:
    publiees = []
    for path in paths:
        try:
            from core import stockage_r2
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:20]
            key = f"montages-video/{user_key}/{uuid.uuid4().hex}-{path.name}"
            bucket = stockage_r2.from_("images-publiques")
            # Ne pas charger un rendu MP4 complet en RAM : Remotion et les
            # rendus longs peuvent produire des fichiers bien plus lourds
            # que les uploads d'entrée du chat.
            with path.open("rb") as contenu:
                bucket.upload(key, contenu, {"content-type": mime})
            publiees.append({"nom": path.name, "url": bucket.get_public_url(key), "type_mime": mime})
        except Exception:
            logging.exception("Publication R2 échouée pour une sortie vidéo.")
    return publiees


@mcp_video.tool()
def video_executer_outil(ctx: Context, nom_outil: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Exécute un outil précis de mcp-video après découverte via video_lister_outils.

    nom_outil: nom exact renvoyé par video_lister_outils.
    arguments: paramètres de l'outil découverts. Les chemins doivent référencer
    la vidéo de la conversation ou un fichier produit dans son espace de travail.
    """
    user_id, _conversation_id, root = _context_owner(ctx)
    tool = _tools_dict().get(nom_outil)
    if tool is None or not callable(getattr(tool, "fn", None)):
        return {"success": False, "error": f"Outil vidéo inconnu : {nom_outil}"}
    manquantes = _dependances_manquantes(nom_outil)
    if manquantes:
        return {
            "success": False,
            "outil": nom_outil,
            "dependances_manquantes": manquantes,
            "error": (
                "Cette capacité n'est pas activée sur le backend principal. "
                "Dépendances manquantes : " + ", ".join(manquantes)
                + ". Elles sont isolées dans requirements-video-ai.txt pour éviter "
                "de rendre le service principal instable."
            ),
        }
    try:
        # Un appel MCP peut atterrir sur une autre instance Railway que le
        # POST initial. Recharge les projets/résultats du workspace, puis la
        # vidéo source nommée par ses identifiants opaques.
        restaurer_workspace(user_id, _conversation_id, root=root)
        _restaurer_sources_dans_arguments(arguments or {}, user_id, _conversation_id)
        args = _normaliser_arguments(nom_outil, arguments or {}, root)
        fonction = tool.fn
        result = fonction(**args)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        result = _serialiser(result)
        # Persiste les versions intermédiaires AVANT de renvoyer le contrôle
        # au modèle, pour qu'une opération suivante survive à un redémarrage.
        synchroniser_workspace(user_id, _conversation_id, root=root)
        sorties = _chemins_sortie(result, root) + _sorties_depuis_arguments(args, root)
        urls = _publier_sorties(list(dict.fromkeys(sorties)), user_id)
        if isinstance(result, dict):
            result["liens_telechargement"] = urls
        return {"success": True, "outil": nom_outil, "resultat": result}
    except Exception as exc:
        logging.exception("Échec outil mcp-video %s", nom_outil)
        return {"success": False, "outil": nom_outil, "error": str(exc)}
