"""API authentifiée de gestion des autorisations personnelles des outils MCP."""

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_secret, utilisateur_courant
from core.permissions_outils import charger_permissions_outils, enregistrer_permission_outil
from mcp_tools import lister_outils_autorises_pour_agent
from registre_outils import REGISTRE_AFFICHAGE_OUTILS

router = APIRouter(prefix="/api/outils/permissions", tags=["permissions des outils"])

DESCRIPTIONS_CLAIRES = {
    "gerer_depot_github": "Explore les dépôts GitHub et lit leurs fichiers. Selon l’action choisie, cet outil peut aussi créer des branches, modifier ou supprimer des fichiers, gérer des issues et des pull requests, ou déclencher une fusion.",
    "gerer_document_bibliotheque": "Recherche et consulte les documents de la bibliothèque Classinus. Selon l’action, l’outil peut aussi enregistrer, organiser ou supprimer des documents et des fichiers.",
    "gerer_dossier_bibliotheque": "Gère les dossiers de ta bibliothèque personnelle : consulter leur contenu, créer, renommer, déplacer des fichiers ou supprimer un dossier et potentiellement ses fichiers.",
    "gerer_comportement": "Consulte et gère tes comportements, règles et compétences personnalisées. Certaines actions peuvent modifier ou supprimer ces données.",
    "gerer_fichier_conversation": "Accède aux fichiers associés à la conversation en cours et peut, selon l’action, les lire, les préparer ou les enregistrer.",
    "gerer_minuteur": "Consulte, crée, modifie ou arrête les minuteurs de la conversation selon l’action demandée.",
    "generer_document": "Crée un document téléchargeable ou du texte à partir de ta demande.",
    "generer_document_word": "Crée un document Word téléchargeable à partir de ta demande.",
    "generer_document_excel": "Crée un classeur Excel avec le contenu et la structure demandés.",
    "generer_document_powerpoint": "Crée une présentation PowerPoint à partir de ton sujet ou de tes consignes.",
    "generer_code": "Produit du code ou des fichiers de code adaptés au résultat demandé.",
    "generer_image": "Crée une nouvelle image. Certaines générations peuvent consommer des crédits du fournisseur.",
    "lancer_generation_video": "Lance la création d’une vidéo. Le rendu peut prendre du temps et peut consommer des crédits.",
    "lancer_generation_3d": "Génère un modèle ou une scène 3D téléchargeable.",
    "lancer_video_higgsfield": "Lance une génération vidéo via ton compte Higgsfield, potentiellement payante ou consommatrice de crédits.",
    "tavily_search": "Recherche des pages web sur un sujet et renvoie titres, extraits et liens sources.",
    "tavily_extract": "Récupère et extrait le contenu utile d’une page web pour que Clovis puisse le lire.",
    "tavily_crawl": "Explore les pages d’un site pour retrouver son contenu pertinent ; l’opération peut parcourir plusieurs pages.",
    "tavily_map": "Cartographie les pages et les liens d’un site afin d’identifier ses principales URLs.",
    "tavily_research": "Mène une recherche web approfondie et rassemble les sources nécessaires à une synthèse.",
    "rechercher_image": "Recherche des images existantes en ligne ; cet outil ne génère pas de nouvelles images.",
    "rechercher_video": "Recherche des vidéos déjà publiées en ligne ; cet outil ne lance pas une génération vidéo.",
    "consulter_statut_generation": "Vérifie l’état d’une génération déjà lancée : en cours, terminée ou en échec.",
    "deployer_site": "Déploie ou publie un site. Cette action peut rendre son contenu accessible publiquement.",
    "envoyer_pour_signature": "Envoie un document aux destinataires prévus afin de démarrer une procédure de signature électronique.",
    "exporter_donnees": "Prépare un fichier contenant les données demandées. Vérifie son contenu avant de le partager.",
    "calculer_symbolique": "Effectue un calcul symbolique ou mathématique à partir de l’expression fournie.",
    "WolframLanguageEvaluator": "Envoie une expression à Wolfram pour effectuer un calcul ou évaluer un résultat mathématique.",
    "supabase_execute_sql": "Exécute du SQL directement sur une base de données. La requête peut lire, modifier ou supprimer des données selon son contenu.",
    "supabase_apply_migration": "Applique une migration à un projet Supabase ; elle peut changer le schéma ou les données de la base.",
    "supabase_list_tables": "Liste les tables d’un projet Supabase sans modifier leur contenu.",
    "supabase_get_project": "Consulte les informations d’un projet Supabase.",
    "vercel_create_deployment": "Lance un nouveau déploiement Vercel. Vérifie l’environnement ciblé avant d’autoriser cette action.",
    "vercel_cancel_deployment": "Annule un déploiement Vercel en cours.",
    "railway_set_variables": "Modifie les variables d’environnement d’un service Railway ; cela peut changer le comportement d’une application déployée.",
    "railway_delete_service": "Supprime un service Railway. Cette action peut interrompre l’application et être difficile à annuler.",
}

class PermissionOutilBody(BaseModel):
    mode: Literal["autoriser", "demander", "refuser"] = Field(
        description="Autoriser toujours, demander une confirmation à chaque utilisation, ou toujours refuser."
    )

def _nom_sans_prefixe(nom: str) -> str:
    # Les noms de serveurs personnels sont préfixés lors de leur exposition au LLM.
    for prefixe in ("higgsfield_", "vercel_", "railway_", "supabase_"):
        if nom.startswith(prefixe):
            return nom[len(prefixe):]
    return nom

def _application(nom: str) -> str:
    entree = REGISTRE_AFFICHAGE_OUTILS.get(nom)
    if entree and entree.get("appli"):
        return {
            "github": "GitHub",
            "notion": "Notion",
            "google_drive": "Google Drive",
            "drive": "Google Drive",
            "higgsfield": "Higgsfield",
            "vercel": "Vercel",
            "railway": "Railway",
            "supabase": "Supabase",
        }.get(str(entree["appli"]).lower(), str(entree["appli"]).replace("_", " ").title())
    simple = _nom_sans_prefixe(nom)
    if simple.startswith(("notion-", "notion_")):
        return "Notion"
    if simple.startswith("tavily_"):
        return "Recherche web"
    if simple.startswith("Wolfram") or simple.startswith("wolfram_"):
        return "Wolfram"
    if simple == "gerer_depot_github" or simple.startswith("github_"):
        return "GitHub"
    if simple.startswith("lancer_video_higgsfield"):
        return "Higgsfield"
    for prefixe, label in (
        ("vercel_", "Vercel"),
        ("railway_", "Railway"),
        ("supabase_", "Supabase"),
        ("higgsfield_", "Higgsfield"),
    ):
        if nom.startswith(prefixe):
            return label
    if simple in {"search_files", "read_file_content", "download_file_content", "list_recent_files", "get_file_metadata", "create_file", "copy_file"}:
        return "Google Drive"
    return "Classinus"

def _categorie(nom: str) -> str:
    action = _nom_sans_prefixe(nom).lower().replace("-", "_")
    if action.startswith("gerer_"):
        return "mixte"
    if action.startswith(("generer_", "lancer_generation", "rendre_", "render_", "create_image", "create_video")):
        return "generation"
    lecture = {"search", "list", "get", "read", "fetch", "query", "inspect", "find", "lookup", "describe", "retrieve", "show", "view", "open", "extract", "crawl", "map", "check", "count", "preview", "whoami", "status"}
    modification = {"create", "update", "edit", "delete", "remove", "move", "copy", "upload", "send", "start", "stop", "deploy", "publish", "merge", "commit", "write", "set", "add", "duplicate", "execute", "run", "launch", "install", "restart", "cancel", "archive", "trash", "branch", "fork", "comment", "star", "close", "reopen", "push", "apply", "trigger"}
    verbes_fr_lecture = {"rechercher", "chercher", "consulter", "lire", "lister", "obtenir", "verifier", "vérifier", "inspecter", "afficher", "explorer", "extraire", "analyser", "cartographier", "ouvrir", "telecharger", "télécharger"}
    verbes_fr_modification = {"creer", "créer", "modifier", "supprimer", "ajouter", "deplacer", "déplacer", "renommer", "envoyer", "publier", "deployer", "déployer", "lancer", "annuler", "arreter", "arrêter", "ranger", "partager", "ecrire", "écrire", "executer", "exécuter", "fusionner", "installer", "configurer", "dupliquer", "activer", "desactiver", "désactiver"}
    mots = action.split("_")
    if mots[0] in lecture or mots[0] in verbes_fr_lecture:
        return "lecture"
    if mots[0] in modification or mots[0] in verbes_fr_modification:
        return "modification"
    if len(mots) > 1 and (mots[1] in lecture or mots[1] in verbes_fr_lecture):
        return "lecture"
    if len(mots) > 1 and (mots[1] in modification or mots[1] in verbes_fr_modification):
        return "modification"
    return "operation"

def _description(nom: str, description_technique: str, application: str, disponible: bool) -> str:
    if not disponible:
        return "Cet outil n’est pas présent dans le catalogue actif. Sa règle est conservée et reprendra effet s’il redevient disponible."
    simple = _nom_sans_prefixe(nom).replace("-", "_")
    description_claire = DESCRIPTIONS_CLAIRES.get(nom) or DESCRIPTIONS_CLAIRES.get(simple)
    if description_claire:
        return description_claire
    categorie = _categorie(nom)
    if categorie == "lecture":
        return f"Consulte ou recherche des informations dans {application}. Cette action est classée en lecture/recherche ; le détail du connecteur ci-dessous précise les données concernées."
    if categorie == "modification":
        return f"Agit sur {application} : selon les paramètres transmis, cette action peut créer, modifier, envoyer ou supprimer des données. Lis les détails du connecteur avant de lui donner un accès permanent."
    if categorie == "generation":
        return f"Produit du contenu ou un fichier via {application}. Une opération peut mobiliser du temps de calcul ou des crédits du fournisseur."
    if categorie == "mixte":
        return f"Regroupe plusieurs actions de {application}. L’effet dépend du paramètre « action » : certaines opérations lisent les données, d’autres les modifient ou les suppriment."
    if description_technique:
        return f"Effectue une opération du connecteur {application}. Le détail du connecteur ci-dessous décrit ses paramètres et le comportement annoncé."
    return f"Effectue une opération du connecteur {application}. Sa fonction précise reste à documenter avant de pouvoir conseiller une autorisation permanente."

def _libelle(nom: str) -> str:
    entree = REGISTRE_AFFICHAGE_OUTILS.get(nom)
    if entree and isinstance(entree.get("label"), str):
        return entree["label"]
    simple = _nom_sans_prefixe(nom).replace("-", "_")
    mots = simple.split("_")
    verbes = {
        "search": "Rechercher", "find": "Rechercher", "list": "Lister",
        "get": "Consulter", "read": "Lire", "fetch": "Récupérer",
        "query": "Interroger", "inspect": "Inspecter", "create": "Créer",
        "update": "Modifier", "edit": "Modifier", "delete": "Supprimer",
        "remove": "Supprimer", "move": "Déplacer", "copy": "Copier",
        "upload": "Importer", "download": "Télécharger", "send": "Envoyer",
        "start": "Démarrer", "stop": "Arrêter", "deploy": "Déployer",
        "publish": "Publier", "merge": "Fusionner", "execute": "Exécuter",
        "run": "Exécuter", "cancel": "Annuler", "apply": "Appliquer",
        "rechercher": "Rechercher", "consulter": "Consulter", "modifier": "Modifier",
        "supprimer": "Supprimer", "creer": "Créer", "créer": "Créer",
    }
    if mots and mots[0] in verbes:
        reste = " ".join(mots[1:]).replace("sql", "SQL").replace("api", "API")
        return verbes[mots[0]] + (" " + reste if reste else "")
    return " ".join(m.capitalize() for m in mots)

def _outil_presentable(nom: str, description_technique: str, mode: str, disponible: bool) -> dict:
    return {
        "nom": nom,
        "label": _libelle(nom),
        "application": _application(nom),
        "description": _description(nom, description_technique or "", _application(nom), disponible),
        "description_technique": description_technique or None,
        "categorie": _categorie(nom) if disponible else "indisponible",
        "mode": mode if mode in {"autoriser", "demander", "refuser"} else "demander",
        "disponible": disponible,
    }

@router.get("")
def lister_permissions(utilisateur=Depends(utilisateur_courant)):
    try:
        regles = charger_permissions_outils(str(utilisateur.id))
        outils_bruts, _ = lister_outils_autorises_pour_agent(
            get_secret, user_id=str(utilisateur.id), agent_id="clovis", appliquer_permissions=False
        )
    except Exception as e:
        logging.exception("Impossible de charger le catalogue ou les règles des outils.")
        raise HTTPException(status_code=503, detail="Impossible de charger les outils et leurs règles pour le moment.") from e

    outils = []
    disponibles = set()
    for item in outils_bruts:
        fonction = item.get("function", {})
        nom = fonction.get("name")
        if not nom:
            continue
        disponibles.add(nom)
        outils.append(_outil_presentable(nom, fonction.get("description") or "", regles.get(nom, "demander"), True))

    # Les autorisations enregistrées restent visibles même si l'outil est déconnecté
    # ou désactivé à l'échelle de la plateforme.
    for nom, mode in regles.items():
        if nom not in disponibles:
            outils.append(_outil_presentable(nom, "", mode, False))

    outils.sort(key=lambda outil: (outil["application"].casefold(), outil["label"].casefold(), outil["nom"]))
    return {"outils": outils}

@router.put("/{nom_outil}")
def definir_permission(nom_outil: str, payload: PermissionOutilBody, utilisateur=Depends(utilisateur_courant)):
    nom = nom_outil.strip()
    if not nom or len(nom) > 200 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", nom):
        raise HTTPException(status_code=400, detail="Nom d’outil invalide.")
    try:
        regles = charger_permissions_outils(str(utilisateur.id))
        outils_bruts, _ = lister_outils_autorises_pour_agent(
            get_secret, user_id=str(utilisateur.id), agent_id="clovis", appliquer_permissions=False
        )
        disponibles = {item.get("function", {}).get("name") for item in outils_bruts}
        outils_connus = set(REGISTRE_AFFICHAGE_OUTILS) | set(regles)
        if nom not in disponibles and nom not in outils_connus:
            raise HTTPException(status_code=404, detail="Cet outil n’existe pas dans le catalogue actuel.")
        enregistrer_permission_outil(str(utilisateur.id), nom, payload.mode)
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Impossible d’enregistrer une règle d’autorisation MCP.")
        raise HTTPException(status_code=503, detail="La règle n’a pas pu être enregistrée. Réessaie plus tard.") from e
    return {"nom": nom, "mode": payload.mode}
