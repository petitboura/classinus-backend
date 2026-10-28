"""Configuration de l'import depuis une autre IA (27 et 28/10/2026, demande Bourama).

Tous les boutons (pages Mémoire, Skills, Configuration et bandeau du chat) font la même chose et
disent la même chose au LLM. Seul le texte que l'utilisateur voit change selon sa section
(voir components/ImportDepuisAutreIA.tsx). `origine` ne sert donc qu'à ranger le lien de la
notification de fin vers la section d'où l'utilisateur est parti.

Deux textes, un seul de chaque :
- PROMPT_EXPORT : ce que l'utilisateur envoie A L'AUTRE IA pour obtenir un zip complet ;
- CONSIGNE_LLM : ce que le LLM de Classinus reçoit, comme si l'utilisateur l'avait écrit dans le
  chat avec le zip joint (voir core/import_depuis_autre_ia.py).

La liste des applications connectées est toujours demandée. Hors du chat on ne peut rien connecter :
le LLM la garde dans la mémoire de l'utilisateur pour la lui rappeler quand ils discuteront.

Tout ce qui peut changer sans toucher à la logique vit ici : textes, liste des IA, modèles de lien.
A terme, la liste des IA pourra venir d'une table Supabase.

Aucun double tiret dans les textes : règle du dépôt (CLAUDE.md).
"""
from urllib.parse import quote

# Section d'où part l'utilisateur. "chat" est le bandeau au dessus de la barre de saisie.
ORIGINES = ("memoire", "skills", "configuration", "chat")

# Page de l'appli où l'utilisateur retrouve le résultat (lien de la notification de fin).
PAGES_RESULTAT = {
    "memoire": "/memoire",
    "skills": "/comportements",
    "configuration": "/bureau/configuration",
    "chat": "/",
}

# `lien` contient {prompt} quand l'IA accepte un prompt déjà rempli dans l'adresse.
# Sans {prompt}, l'appli copie le prompt et ouvre simplement l'IA (prerempli = False).
# A vérifier à chaque ajout : le comportement de chaque IA peut changer.
IAS_EXPORT = [
    {"id": "claude", "nom": "Claude", "lien": "https://claude.ai/new?q={prompt}"},
    {"id": "chatgpt", "nom": "ChatGPT", "lien": "https://chatgpt.com/?q={prompt}"},
    {"id": "gemini", "nom": "Gemini", "lien": "https://gemini.google.com/app"},
]

PROMPT_EXPORT = {
    "fr": (
        "Je quitte cette IA pour passer sur Classinus. Prépare-moi un export complet de tout ce que tu as sur moi, "
        "dans UN SEUL fichier zip que je pourrai télécharger. Le zip contient : "
        "memoire.md (tout ce que tu retiens sur moi : identité, métier, projets, préférences, habitudes, contexte personnel, "
        "un fait par ligne, regroupés par thème, avec la date si tu l'as) ; "
        "un dossier skills/ avec un sous-dossier par skill, chacun avec son SKILL.md complet (nom, description, instructions) "
        "et ses fichiers annexes s'il y en a ; "
        "instructions.md (mes instructions personnalisées et mes préférences de style, de ton et de format, mot pour mot) ; "
        "applications-connectees.md (chaque application ou connecteur relié à mon compte, avec son nom et ce que j'en fais) ; "
        "LISEZMOI.md qui décrit le contenu du zip. "
        "Règles : n'invente rien, ne résume pas, donne les contenus tels quels. "
        "N'inclus jamais de mot de passe, de clé ni de jeton. "
        "Si tu n'as rien dans une catégorie, crée quand même le fichier et écris \"aucun\". "
        "Si tu ne peux pas créer de zip, donne chaque fichier dans un bloc de code précédé de son chemin exact."
    ),
    "en": (
        "I am leaving this AI for Classinus. Prepare a complete export of everything you have on me, "
        "in ONE single zip file I can download. The zip contains: "
        "memoire.md (everything you remember about me: identity, job, projects, preferences, habits, personal context, "
        "one fact per line, grouped by theme, with the date if you have it); "
        "a skills/ folder with one subfolder per skill, each with its complete SKILL.md (name, description, instructions) "
        "and its extra files if any; "
        "instructions.md (my custom instructions and my style, tone and format preferences, word for word); "
        "applications-connectees.md (every app or connector linked to my account, with its name and what I use it for); "
        "LISEZMOI.md describing the content of the zip. "
        "Rules: invent nothing, do not summarize, give the contents as they are. "
        "Never include a password, key or token. "
        "If you have nothing in a category, still create the file and write \"none\". "
        "If you cannot create a zip, give each file in a code block preceded by its exact path."
    ),
}

# Ce que le LLM de Classinus reçoit comme message de l'utilisateur, avec le zip joint.
# Demande explicite d'écrire : le prompt système interdit d'écrire sans demande claire.
CONSIGNE_LLM = {
    "fr": (
        "Je t'ai joint un zip exporté d'une autre IA. Il peut contenir ma mémoire, mes skills, mes instructions personnalisées "
        "et la liste de mes applications connectées. Range chaque chose au bon endroit, sans rien inventer. "
        "Mémoire : enregistre dans ta mémoire de moi chaque fait durable, sans doublon avec ce que tu sais déjà, et ignore le temporaire. "
        "Skills : pour chaque skill du zip, crée un skill avec le nom et la description de son SKILL.md, puis ajoute ses fichiers annexes ; "
        "ne modifie pas mes skills existants. "
        "Configuration : range mes instructions et préférences au bon endroit de ma configuration, sans toucher à ce qui existe déjà. "
        "Applications connectées : tu ne peux pas les connecter pour l'instant, alors enregistre dans ta mémoire de moi, dans une "
        "sous-catégorie nommée applications_a_reconnecter, la liste de ces applications avec la note de me rappeler de les "
        "connecter un autre jour, quand on discutera. "
        "Quand tu as fini, dis-moi en quelques lignes ce que tu as fait et ce que tu n'as pas pu faire, avec la raison."
    ),
    "en": (
        "I attached a zip exported from another AI. It may contain my memory, my skills, my custom instructions "
        "and the list of my connected apps. Put each thing in the right place, inventing nothing. "
        "Memory: save to your memory of me every lasting fact, without duplicating what you already know, and ignore anything temporary. "
        "Skills: for each skill in the zip, create a skill with the name and description from its SKILL.md, then add its extra files; "
        "do not change my existing skills. "
        "Configuration: put my instructions and preferences in the right place of my configuration, leaving what already exists untouched. "
        "Connected apps: you cannot connect them for now, so save to your memory of me, in a subcategory named "
        "applications_a_reconnecter, the list of these apps with a note to remind me to connect them another day, when we chat. "
        "When you are done, tell me in a few lines what you did and what you could not do, with the reason."
    ),
}

# Titre de la conversation enregistrée dans l'historique.
LIBELLE_HISTORIQUE = {
    "fr": "Import depuis une autre IA",
    "en": "Import from another AI",
}

NOTIFICATIONS = {
    "termine": {
        "fr": ("Import terminé", "L'import depuis l'autre IA est terminé. Ouvre la page pour vérifier le résultat."),
        "en": ("Import finished", "The import from the other AI is finished. Open the page to check the result."),
    },
    "echec": {
        "fr": ("Import interrompu", "L'import depuis l'autre IA s'est arrêté avant la fin. Rien n'est perdu, tu peux réessayer."),
        "en": ("Import stopped", "The import from the other AI stopped before the end. Nothing is lost, you can try again."),
    },
}


def _langue(langue: str | None) -> str:
    return "en" if langue == "en" else "fr"


def prompt_export(langue: str | None) -> str:
    """Prompt complet à envoyer à l'autre IA (le même pour tous les boutons)."""
    return PROMPT_EXPORT[_langue(langue)]


def consigne_llm(langue: str | None) -> str:
    return CONSIGNE_LLM[_langue(langue)]


def libelle_historique(langue: str | None) -> str:
    return LIBELLE_HISTORIQUE[_langue(langue)]


def textes_notification(cle: str, langue: str | None) -> tuple[str, str]:
    return NOTIFICATIONS[cle][_langue(langue)]


def ias_export(langue: str | None) -> list[dict]:
    """Liste des IA proposées, avec l'adresse à ouvrir. `prerempli` vaut False quand le prompt doit être copié."""
    texte = prompt_export(langue)
    resultat = []
    for ia in IAS_EXPORT:
        prerempli = "{prompt}" in ia["lien"]
        url = ia["lien"].replace("{prompt}", quote(texte, safe="")) if prerempli else ia["lien"]
        resultat.append({"id": ia["id"], "nom": ia["nom"], "url": url, "prerempli": prerempli})
    return resultat
