"""English labels for chat tools and streaming progress events.

This module translates only UI-facing tool labels and progress messages. Tool
results, user documents, IDs, and business data are deliberately not touched.
"""

import re
from typing import Any

LIBELLES_OUTILS_EN: dict[str, str] = {
    "Génération d'un PDF/texte": "Generate a PDF or text document",
    "Génération d'un Word": "Generate a Word document",
    "Génération d'un Excel": "Generate an Excel spreadsheet",
    "Génération d'un PowerPoint": "Generate a PowerPoint presentation",
    "Génération d'un document LaTeX": "Generate a LaTeX document",
    "Génération de code": "Generate code",
    "Génération d'un site (zip)": "Generate a website archive",
    "Génération d'une archive": "Generate an archive",
    "Génération d'une image": "Generate an image",
    "Génération audio": "Generate audio",
    "Génération d'une vidéo": "Generate a video",
    "Génération d'un modèle 3D": "Generate a 3D model",
    "Envoi pour signature": "Send for signature",
    "Statut d'une génération": "Generation status",
    "Déploiement d'un site": "Deploy a website",
    "Export de données": "Export data",
    "Calcul symbolique": "Symbolic calculation",
    "Calcul Wolfram": "Wolfram calculation",
    "Recherche web": "Web search",
    "Extraction d'une page": "Extract page content",
    "Exploration d'un site": "Explore a website",
    "Cartographie d'un site": "Map a website",
    "Recherche approfondie": "Deep research",
    "Recherche d'image": "Image search",
    "Recherche de vidéo": "Video search",
    "Lecture d'une vidéo": "Watch a video",
    "Recherche de document": "Document search",
    "Lecture d'un document": "Read a document",
    "Lecture d'un fichier externe": "Read an external file",
    "Génération d'une vidéo": "Generate a video",
    "Suivi d'une vidéo": "Video status",
    "Programmes publics": "Public programs",
    "Ajout d'un commentaire public": "Add a public comment",
    "Suppression d'un commentaire public": "Delete a public comment",
    "Ma bibliothèque": "My library",
    "Fichiers du chat": "Chat files",
    "Catalogue public": "Public catalog",
    "Aide Classinus": "Classinus help",
    "Dépôt GitHub": "GitHub repository",
    "Recherche dans Notion": "Search Notion",
    "Ouvrir une page Notion": "Open a Notion page",
    "Base Notion (SQL)": "Notion data source (SQL)",
    "Interrogation d'une vue Notion": "Query a Notion database view",
    "Notes de réunion Notion": "Notion meeting notes",
    "Commentaires Notion": "Notion comments",
    "Tâche Notion en cours": "Notion task in progress",
    "Liste des équipes Notion": "List Notion teams",
    "Liste des utilisateurs Notion": "List Notion users",
    "Pièce jointe Notion": "Notion attachment",
    "Création d'une page Notion": "Create a Notion page",
    "Modification d'une page Notion": "Edit a Notion page",
    "Déplacement d'une page Notion": "Move a Notion page",
    "Duplication d'une page Notion": "Duplicate a Notion page",
    "Création d'une base Notion": "Create a Notion database",
    "Schéma d'une base Notion": "Notion database schema",
    "Commentaire dans Notion": "Comment on Notion",
    "Joindre un fichier Notion": "Attach a file in Notion",
    "Création d'une vue Notion": "Create a Notion view",
    "Modification d'une vue Notion": "Edit a Notion view",
    "Recherche IA dans Notion": "AI search in Notion",
    "Recherche d'agents Notion": "Search Notion agents",
    "Recherche de sessions Notion": "Search Notion sessions",
    "Recherche de skills Notion": "Search Notion skills",
    "Plusieurs bases Notion": "Multiple Notion databases",
    "Sessions Notion": "Notion sessions",
    "Évènement de session Notion": "Notion session event",
    "Pages favorites Notion": "Favorite Notion pages",
    "Liste des pages privées Notion": "List private Notion pages",
    "Pages Notion récentes": "Recent Notion pages",
    "Historique de session Notion": "Notion session history",
    "Pages partagées Notion": "Shared Notion pages",
    "Statut de session Notion": "Notion session status",
    "Droits d'accès Notion": "Notion access permissions",
    "Étapes suivantes Notion": "Next steps in Notion",
    "Télécharger un skill Notion": "Download a Notion skill",
    "Analyse avancée Notion": "Advanced Notion analysis",
    "Création d'un dossier Notion": "Create a Notion folder",
    "Modifier un dossier Notion": "Edit a Notion folder",
    "Envoi d'un fichier dans Notion": "Upload a file to Notion",
    "Page Notion en skill": "Convert a Notion page to a skill",
    "Import d'un skill dans Notion": "Import a skill into Notion",
    "Lancer une session Notion": "Start a Notion session",
    "Message à une session Notion": "Message a Notion session",
    "Arrêt de session Notion": "Stop a Notion session",
    "Recherche d'un fichier Drive": "Search Drive files",
    "Lecture d'un fichier Drive": "Read a Drive file",
    "Téléchargement Drive": "Download from Drive",
    "Fichiers Drive récents": "Recent Drive files",
    "Infos d'un fichier Drive": "Drive file details",
    "Création d'un fichier Drive": "Create a Drive file",
    "Copie d'un fichier Drive": "Copy a Drive file",
    "Envoi d'un message": "Send a message",
    "Aperçu de ta mémoire": "Preview your memory",
    "Lecture de ta mémoire": "Read your memory",
    "Enregistrement dans ta mémoire": "Save to your memory",
    "Consultation de ton profil": "View your profile",
    "Mise à jour de ton profil": "Update your profile",
    "Joindre ma position": "Attach my location",
    "Formule ou réaction chimique": "Formula or chemical reaction",
    "Éditeur maths live": "Live math editor",
    "Forcer une recherche web": "Force a web search",
    "Dessin et croquis": "Drawing and sketching",
    "Mode vocal": "Voice mode",
    "Prendre une photo": "Take a photo",
    "Mes dossiers": "My folders",
    "Conversations passées": "Previous conversations",
    "Lire une conversation": "Read a conversation",
    "Matière active": "Active subject",
    "Annuler la modification": "Undo the change",
    "Mes skills": "My skills",
    "Skills des chapitres": "Chapter skills",
    "Programme": "Curriculum",
    "Consultation de l'avancement": "Check progress",
    "Vérification du code actif": "Check the active code",
    "Changement de mode": "Change mode",
    "Lecture des réponses QCM": "Read quiz answers",
    "Rappel d'un résultat précédent": "Recall a previous result",
    "Rappel d'un échange précédent": "Recall a previous exchange",
    "Archivage d'un sujet terminé": "Archive a completed topic",
    "Mon téléphone": "My phone",
    "Dossier en direct": "Live folder",
    "Recherche d'un outil": "Search for a tool",
    "Action dans l'application": "In-app action",
    "Minuteur": "Timer",
    "Clic dans l'application": "In-app click",
    "Pointer un élément": "Point to an item",
    "Écriture dans un champ": "Type in a field",
    "Lecture de la page": "Read the page",
    "Clic à l'écran": "On-screen click",
    "Pointage à l'écran": "On-screen pointing",
    "Marque à l'écran": "On-screen marking",
    "Saisie au clavier": "Keyboard input",
    "Raccourci clavier": "Keyboard shortcut",
    "Ouverture d'une application": "Open an application",
    "Lecture de l'écran": "Read the screen",
    "Lecture de l'écran du téléphone": "Read the phone screen",
    "Marque sur l'écran du téléphone": "Mark the phone screen",
    "Lecture de l'éditeur de code": "Read the code editor",
    "Montrer dans l'éditeur": "Show in the editor",
    "Écrire dans l'éditeur": "Write in the editor",
    "Message en direct à l'étudiant": "Live message to the student",
    "Ouverture du canal en direct": "Open the live channel",
    "Activation du canal en direct": "Enable the live channel",
    "Couper le canal en direct": "Disable the live channel",
    "Dossiers publics": "Public folders",
    "Skills publics": "Public skills",
    "Étoile du catalogue public": "Rate the public catalog",
    "Concentration": "Focus",
    "Lecture du temps d'écran": "Read screen time",
    "Planification d'un rappel": "Schedule a reminder",
    "Consultation d'un signalement": "Review a report",
    "Note sur un signalement": "Add a note to a report",
    "Rattacher un signalement": "Attach a report",
}

VERBES_STATUT_EN: dict[str, str] = {
    "Recherche": "Search",
    "Liste": "List",
    "Consultation": "View",
    "Lecture": "Read",
    "Ouverture": "Open",
    "Exploration": "Explore",
    "Création": "Create",
    "Ajout": "Add",
    "Lancement": "Start",
    "Démarrage": "Start",
    "Activation": "Enable",
    "Exécution": "Run",
    "Arrêt": "Stop",
    "Publication": "Publish",
    "Modification": "Edit",
    "Renommage": "Rename",
    "Mise à jour": "Update",
    "Réglage": "Set",
    "Nommage": "Name",
    "Suppression": "Delete",
    "Effacement": "Clear",
    "Retrait": "Remove",
    "Déclassement": "Unlist",
    "Rangement": "Organize",
    "Classement": "Sort",
    "Déplacement": "Move",
    "Fusion": "Merge",
    "Copie": "Copy",
    "Envoi": "Send",
}

STATUTS_EN: dict[str, str] = {
    "Lecture de l'image...": "Reading image...",
    "Lecture de l'image effectuée": "Image reading completed",
    "Lecture de l'image a échoué": "Image reading failed",
}


def _base_vers_anglais(texte: str) -> str:
    exact = STATUTS_EN.get(texte) or LIBELLES_OUTILS_EN.get(texte) or VERBES_STATUT_EN.get(texte)
    if exact:
        return exact
    plateforme = re.fullmatch(r"(Action sur|Consultation de)\s+(.+)", texte)
    if plateforme:
        debut, nom = plateforme.groups()
        return f"Action on {nom}" if debut == "Action sur" else f"Viewing {nom}"
    composite = re.fullmatch(r"(.+?)\s+\((.+)\)", texte)
    if composite:
        verbe, libelle = composite.groups()
        verbe_en = VERBES_STATUT_EN.get(verbe, verbe)
        libelle_en = LIBELLES_OUTILS_EN.get(libelle, libelle)
        if verbe_en != verbe or libelle_en != libelle:
            return f"{verbe_en} ({libelle_en})"
    return texte


def traduire_libelle_outil(texte: Any) -> Any:
    """Translate a tool label or progress phrase, preserving unknown strings."""
    if not isinstance(texte, str) or not texte:
        return texte

    exact = STATUTS_EN.get(texte) or LIBELLES_OUTILS_EN.get(texte)
    if exact:
        return exact

    suffixes = (
        (" a échoué", " failed"),
        (" effectuée", " completed"),
        (" effectué", " completed"),
        (" annulée", " canceled"),
        (" annulé", " canceled"),
        ("...", "..."),
        ("…", "…"),
    )
    for suffix_fr, suffix_en in suffixes:
        if texte.endswith(suffix_fr):
            base = texte[: -len(suffix_fr)].rstrip()
            base_en = _base_vers_anglais(base)
            if base_en != base:
                return base_en + suffix_en

    return _base_vers_anglais(texte)
