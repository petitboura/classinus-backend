"""Configuration de l'import depuis une autre IA (27/10/2026, demande Bourama).

Trois cibles, chacune avec son bouton dans l'appli : memoire, skills, configuration.
Pour chaque cible, deux textes :
- PROMPTS_EXPORT : ce que l'utilisateur envoie A L'AUTRE IA pour obtenir un zip ;
- CONSIGNES_LLM : ce que le LLM de Classinus reçoit, comme si l'utilisateur l'avait écrit
  dans le chat avec le zip joint (voir core/import_depuis_autre_ia.py).

Tout ce qui peut changer sans toucher à la logique vit ici : textes, liste des IA,
modèles de lien. A terme, cette liste pourra venir d'une table Supabase.

Aucun double tiret dans les textes : règle du dépôt (CLAUDE.md).
"""
from urllib.parse import quote

CIBLES = ("memoire", "skills", "configuration")

# Page de l'appli où l'utilisateur retrouve le résultat (lien de la notification de fin).
PAGES_RESULTAT = {
    "memoire": "/memoire",
    "skills": "/comportements",
    "configuration": "/bureau/configuration",
}

# `lien` contient {prompt} quand l'IA accepte un prompt déjà rempli dans l'adresse.
# Sans {prompt}, l'appli copie le prompt et ouvre simplement l'IA (prerempli = False).
# A vérifier à chaque ajout : le comportement de chaque IA peut changer.
IAS_EXPORT = [
    {"id": "claude", "nom": "Claude", "lien": "https://claude.ai/new?q={prompt}"},
    {"id": "chatgpt", "nom": "ChatGPT", "lien": "https://chatgpt.com/?q={prompt}"},
    {"id": "gemini", "nom": "Gemini", "lien": "https://gemini.google.com/app"},
]

_REGLES_COMMUNES = {
    "fr": (
        "Règles : n'invente rien, ne résume pas, donne les contenus tels quels. "
        "N'inclus jamais de mot de passe, de clé ni de jeton. "
        "Si tu n'as rien dans cette catégorie, crée quand même le fichier et écris \"aucun\". "
        "Si tu ne peux pas créer de zip, donne chaque fichier dans un bloc de code précédé de son chemin exact."
    ),
    "en": (
        "Rules: invent nothing, do not summarize, give the contents as they are. "
        "Never include a password, key or token. "
        "If you have nothing in this category, still create the file and write \"none\". "
        "If you cannot create a zip, give each file in a code block preceded by its exact path."
    ),
}

PROMPTS_EXPORT = {
    "memoire": {
        "fr": (
            "Je quitte cette IA pour passer sur Classinus. Prépare-moi un export de tout ce que tu retiens sur moi, "
            "dans UN SEUL fichier zip que je pourrai télécharger. "
            "Le zip contient memoire.md (identité, métier, projets, préférences, habitudes, contexte personnel, "
            "un fait par ligne, regroupés par thème, avec la date si tu l'as) et LISEZMOI.md qui décrit le contenu. "
        ),
        "en": (
            "I am leaving this AI for Classinus. Prepare an export of everything you remember about me, "
            "in ONE single zip file I can download. "
            "The zip contains memoire.md (identity, job, projects, preferences, habits, personal context, "
            "one fact per line, grouped by theme, with the date if you have it) and LISEZMOI.md describing the content. "
        ),
    },
    "skills": {
        "fr": (
            "Je quitte cette IA pour passer sur Classinus. Prépare-moi un export de tous mes skills, "
            "dans UN SEUL fichier zip que je pourrai télécharger. "
            "Le zip contient un dossier skills/ avec un sous-dossier par skill. Chaque sous-dossier contient "
            "son SKILL.md complet (nom, description, instructions) et ses fichiers annexes s'il y en a. "
        ),
        "en": (
            "I am leaving this AI for Classinus. Prepare an export of all my skills, "
            "in ONE single zip file I can download. "
            "The zip contains a skills/ folder with one subfolder per skill. Each subfolder contains "
            "its complete SKILL.md (name, description, instructions) and its extra files if any. "
        ),
    },
    "configuration": {
        "fr": (
            "Je quitte cette IA pour passer sur Classinus. Prépare-moi un export de mes instructions personnalisées "
            "et de mes préférences de réponse, dans UN SEUL fichier zip que je pourrai télécharger. "
            "Le zip contient instructions.md avec mes instructions personnalisées et mes préférences de style, "
            "de ton et de format, mot pour mot. "
        ),
        "en": (
            "I am leaving this AI for Classinus. Prepare an export of my custom instructions "
            "and my response preferences, in ONE single zip file I can download. "
            "The zip contains instructions.md with my custom instructions and my style, tone and format preferences, "
            "word for word. "
        ),
    },
}

# Ce que le LLM de Classinus reçoit comme message de l'utilisateur, avec le zip joint.
# Demande explicite d'écrire : le prompt système interdit d'écrire sans demande claire.
CONSIGNES_LLM = {
    "memoire": {
        "fr": (
            "Je t'ai joint un zip exporté d'une autre IA. Il contient ma mémoire. Lis-le, puis enregistre dans ta mémoire "
            "de moi chaque fait durable qu'il contient, sans rien inventer et sans doublon avec ce que tu sais déjà. "
            "Ignore ce qui est temporaire. Quand tu as fini, dis-moi en quelques lignes ce que tu as enregistré."
        ),
        "en": (
            "I attached a zip exported from another AI. It contains my memory. Read it, then save to your memory of me "
            "every lasting fact it contains, inventing nothing and without duplicating what you already know. "
            "Ignore anything temporary. When you are done, tell me in a few lines what you saved."
        ),
    },
    "skills": {
        "fr": (
            "Je t'ai joint un zip exporté d'une autre IA. Il contient mes skills, un dossier par skill. Pour chacun, "
            "crée un skill avec le nom et la description de son SKILL.md, puis ajoute ses fichiers annexes à leur place. "
            "Ne modifie pas mes skills existants. Quand tu as fini, liste-moi les skills créés et ceux que tu n'as pas pu créer, avec la raison."
        ),
        "en": (
            "I attached a zip exported from another AI. It contains my skills, one folder per skill. For each one, "
            "create a skill with the name and description from its SKILL.md, then add its extra files in place. "
            "Do not change my existing skills. When you are done, list the skills you created and the ones you could not create, with the reason."
        ),
    },
    "configuration": {
        "fr": (
            "Je t'ai joint un zip exporté d'une autre IA. Il contient mes instructions personnalisées et mes préférences de réponse. "
            "Lis-le, puis range chaque élément au bon endroit de ma configuration, sans rien inventer et sans toucher à ce qui existe déjà. "
            "Quand tu as fini, dis-moi ce que tu as ajouté."
        ),
        "en": (
            "I attached a zip exported from another AI. It contains my custom instructions and my response preferences. "
            "Read it, then put each item in the right place of my configuration, inventing nothing and leaving what already exists untouched. "
            "When you are done, tell me what you added."
        ),
    },
}

# Titre de la conversation enregistrée dans l'historique (le message complet reste la consigne).
LIBELLES_HISTORIQUE = {
    "memoire": {"fr": "Import de ma mémoire depuis une autre IA", "en": "Importing my memory from another AI"},
    "skills": {"fr": "Import de mes skills depuis une autre IA", "en": "Importing my skills from another AI"},
    "configuration": {"fr": "Import de ma configuration depuis une autre IA", "en": "Importing my configuration from another AI"},
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


def prompt_export(cible: str, langue: str | None) -> str:
    """Prompt complet à envoyer à l'autre IA pour cette cible."""
    l = _langue(langue)
    return PROMPTS_EXPORT[cible][l] + _REGLES_COMMUNES[l]


def consigne_llm(cible: str, langue: str | None) -> str:
    return CONSIGNES_LLM[cible][_langue(langue)]


def libelle_historique(cible: str, langue: str | None) -> str:
    return LIBELLES_HISTORIQUE[cible][_langue(langue)]


def textes_notification(cle: str, langue: str | None) -> tuple[str, str]:
    return NOTIFICATIONS[cle][_langue(langue)]


def ias_pour_cible(cible: str, langue: str | None) -> list[dict]:
    """Liste des IA proposées, avec l'adresse à ouvrir. `prerempli` vaut False quand le prompt doit être copié."""
    texte = prompt_export(cible, langue)
    resultat = []
    for ia in IAS_EXPORT:
        prerempli = "{prompt}" in ia["lien"]
        url = ia["lien"].replace("{prompt}", quote(texte, safe="")) if prerempli else ia["lien"]
        resultat.append({"id": ia["id"], "nom": ia["nom"], "url": url, "prerempli": prerempli})
    return resultat
