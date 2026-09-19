"""
Registre des outils (bras) MCP actifs.

POUR AJOUTER UN NOUVEL OUTIL :
Ajoute une entree dans SERVEURS_MCP ci-dessous. C'est le seul fichier a
modifier. Ni mcp_tools.py (le moteur generique) ni main.py n'ont besoin
d'etre touches.

Deux modes d'authentification sont supportes, car les serveurs MCP ne
s'authentifient pas tous pareil :
- pas de cle du tout (ex: Wolfram)          -> url_builder seul
- cle glissee dans l'URL (ex: Tavily)       -> url_builder seul
- cle envoyee en header HTTP (si besoin un jour) -> url_builder + headers_builder

Chaque *_builder est une fonction qui recoit (get_secret, user_id, agent_id)
et retourne soit une URL (str), soit des headers (dict), soit None. Les
parametres user_id/agent_id sont ignores par la plupart des outils (cle
API globale, comme Tavily/Wolfram) ; ils ne sont utiles que pour un outil
"par utilisateur" (cle "necessite_utilisateur": True), ou chaque utilisateur
connecte son propre compte plutot que d'utiliser une cle partagee par
toute l'app. Pour Notion specifiquement, la connexion est scopee par
user_id seul (compte unifie, juillet 2026) : un utilisateur connecte a
Notion depuis n'importe quel agent l'est automatiquement pour tous les
autres agents de la plateforme -> voir connexions/notion.py.

POUR UN OUTIL "PAR UTILISATEUR" (ex: Notion) :
Ajoute "necessite_utilisateur": True dans son entree. Le dispatcher
(mcp_tools.py) l'ignore alors automatiquement si aucun utilisateur n'est
connecte a l'app, ou si headers_builder renvoie None (utilisateur connecte a
l'app mais pas encore a CET outil POUR CET AGENT) -> pas de bloc if/else
a ecrire ici.
"""

import os

from connexions.notion import obtenir_token_valide

def _url_generation(get_secret, user_id, agent_id, conversation_id=None):
    # Serveur MCP interne, pas un tiers externe (voir
    # core/serveur_mcp_generation.py, monté dans api/main.py). C'est
    # TOUJOURS le même process/port que celui qui répond à cette
    # requête (localhost, jamais un vrai domaine externe), donc pas
    # besoin de BACKEND_URL ici : on lit directement $PORT, la variable
    # que Railway fournit et qu'uvicorn utilise pour écouter.
    #
    # user_id/agent_id ajoutés en query params (2026-07-22) : nécessaire
    # pour planifier_rappel (notifications push), le premier outil de ce
    # serveur qui a besoin de savoir QUI l'appelle -- récupérés côté
    # serveur via ctx.request_context.request.query_params (voir
    # serveur_mcp_generation.py). Inoffensif pour les autres outils qui
    # n'en ont pas besoin.
    #
    # conversation_id ajouté en query param (08/09/2026, demande Bourama
    # -- mode actif) : avant ça, aucun outil appelé par le LLM (documents,
    # programme...) ne pouvait savoir dans quelle conversation il était
    # appelé, donc ne pouvait jamais savoir quel prof est actif pour cette
    # conversation (voir core/mode_actif_conversation.py). Optionnel
    # (absent si conversation_id vaut None) pour ne rien casser des
    # outils qui n'en ont pas besoin. Utilisé pour l'instant seulement par
    # gerer_document_bibliotheque (core/outils_bibliotheque.py) --
    # programme pas encore branché, un pas à la fois.
    port = os.environ.get("PORT", "8000")
    url = f"http://localhost:{port}/mcp/generation?user_id={user_id}&agent_id={agent_id}"
    if conversation_id:
        url += f"&conversation_id={conversation_id}"
    return url


def _url_github(get_secret, user_id, agent_id, conversation_id=None):
    # Même logique que _url_generation ci-dessus -- serveur MCP interne
    # (core/serveur_mcp_github.py), pas un tiers externe.
    port = os.environ.get("PORT", "8000")
    return f"http://localhost:{port}/mcp/github"


def _url_tavily(get_secret, user_id, agent_id, conversation_id=None):
    return f"https://mcp.tavily.com/mcp/?tavilyApiKey={get_secret('TAVILY_API_KEY')}"


def _url_wolfram(get_secret, user_id, agent_id, conversation_id=None):
    # CORRECTIF 2026-08-01 bis (Bourama : "j'ai pas mis de clé wolfram
    # hein" -> creuse). L'URL precedente (services.wolfram.com/api/mcp,
    # "Wolfram MCP Service") est une offre PAYANTE necessitant un
    # abonnement + une cle API (voir support.wolfram.com/73463) -- pas la
    # bonne offre pour ce cas d'usage. La veritable offre gratuite est un
    # produit DIFFERENT, "Wolfram Cloud MCP", confirme sans authentification
    # par DEUX pages officielles distinctes (support.wolfram.com/75237 et
    # wolfram.com/artificial-intelligence/mcp/cloud) : "free to use and
    # does not require any authentication". Limite connue et acceptee pour
    # cet usage (question -> reponse, pas de session multi-etapes) : usage
    # personnel limite, une seule requete a la fois, pas d'upload/download
    # de fichier, pas d'interaction locale.
    return "https://agenttools.wolfram.com/mcp"


def _url_notion(get_secret, user_id, agent_id, conversation_id=None):
    return "https://mcp.notion.com/mcp"


def _headers_notion(get_secret, user_id, agent_id):
    # agent_id fait partie de la signature commune a tous les *_builder
    # (voir docstring en tete de fichier) mais n'est plus utilise ici :
    # la connexion Notion est scopee par user_id seul (compte unifie).
    token = obtenir_token_valide(user_id)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _url_google_drive(get_secret, user_id, agent_id, conversation_id=None):
    # Serveur MCP Drive OFFICIEL de Google (tiers externe, comme Notion),
    # pas un serveur interne -- voir connexions/oauth_generique.py pour
    # le detail (client OAuth a creer manuellement dans Google Cloud
    # Console, scopes drive.readonly + drive.file). Encore en
    # "Developer Preview" cote Google au 01/09/2026.
    return "https://drivemcp.googleapis.com/mcp/v1"


def _headers_google_drive(get_secret, user_id, agent_id):
    # Meme principe que _headers_notion, mais scope par user_id ET
    # service ("google_drive") -- voir connexions/oauth_generique.py,
    # ce fichier gere plusieurs services generiques (Github, Drive...)
    # contrairement a connexions/notion.py qui n'en gere qu'un seul.
    from connexions.oauth_generique import obtenir_token_valide as _token_generique
    token = _token_generique("google_drive", user_id)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


SERVEURS_MCP = [
    # Wolfram DESACTIVE (10/09/2026, demande Bourama) : le serveur
    # agenttools.wolfram.com renvoyait des 503 Service Unavailable de
    # facon repetee, et le code retentait la connexion (1s de backoff)
    # avant de continuer -- environ 12 secondes perdues a CHAQUE message
    # (tous agents, tous modeles confondus, puisque la liste d'outils MCP
    # est reconstruite avant tout appel LLM), pris a tort pour de la
    # lenteur du modele (DeepSeek) alors que lui repondait en moins d'1s.
    # _url_wolfram (juste au-dessus) reste en place pour reactivation
    # facile si le service redevient fiable -- juste redecommenter
    # l'entree ci-dessous.
    # {"nom": "wolfram", "url_builder": _url_wolfram},
    {
        "nom": "tavily",
        "url_builder": _url_tavily,
        # Réactivé 2026-07-23 (demande de Bourama) -- la plomberie
        # existait déjà (builder d'URL ci-dessus, libellés de statut
        # tavily_search/tavily_extract/... dans core/main.py, option
        # dans le créateur d'agent) mais l'entrée manquait ici, donc
        # injoignable même pour un agent l'ayant coché dans ses droits.
        #
        # ATTENTION connue (voir commentaire sur "notion" plus bas) :
        # Notion (20 outils) + Tavily cumulés dépassaient la limite
        # 8000 TPM du tier Groq gratuit -> 413 Payload Too Large, qui
        # faisait basculer sur le fallback Gemini SANS AUCUN outil.
        # Le nouveau système de droits par agent (filtrage par outil,
        # plus par serveur) limite le risque -- mais évite quand même
        # d'activer Notion ET Tavily ensemble pour un même agent tant
        # que ce n'est pas revérifié en conditions réelles.
    },
    {
        "nom": "generation",
        "url_builder": _url_generation,
        # Pas de "outils_autorises" fixe ici : categorie 1, filtree
        # dynamiquement par agent (agents_outils_generation croise avec
        # registre_outils_plateforme.disponible), voir mcp_tools.py ->
        # _outils_generation_actifs_pour_agent. Ce serveur est TOUJOURS
        # interroge (voir lister_tous_les_outils), contrairement a
        # wolfram/github/notion qui dependent de agents_serveurs.
    },
    {
        "nom": "github",
        "url_builder": _url_github,
        # Un seul outil consolidé le 26/08 (ex explorer_depot_github,
        # lire_fichier_depot_github, modifier_fichier_depot_github) :
        # gerer_depot_github. Les actions "explorer" et "lire_fichier"
        # sont sans risque (lecture seule). "modifier_fichier" ÉCRIT
        # réellement sur un dépôt, dans OUTILS_SENSIBLES plus bas (format
        # "nom_outil:action"), donc TOUJOURS interrompu pour confirmation
        # avant exécution, quel que soit le mode (direct ou branche+PR).
    },
    {
        "nom": "notion",
        "url_builder": _url_notion,
        "headers_builder": _headers_notion,
        "necessite_utilisateur": True,
        # Notion active a 100% (01/08, demande Bourama) -- plus de
        # restriction "outils_autorises" : les 20 outils Notion
        # (recherche + creation/edition de pages, bases de donnees,
        # commentaires, equipes...) sont desormais tous disponibles.
        # L'ancienne restriction a notion-search seul datait d'une
        # inquietude sur le budget 8000 TPM du tier Groq gratuit
        # (Notion + Tavily cumules -> 413 Payload Too Large) ; elle est
        # bien moins critique depuis le systeme "bouton Outils"
        # (25-26/07) qui n'envoie de toute facon plus qu'UN OU PLUSIEURS
        # outils selectionnes explicitement au LLM, jamais le catalogue
        # entier. Les outils d'ecriture (notion-create-pages,
        # notion-update-page, notion-move-pages, etc.) restent proteges :
        # ils sont tous dans OUTILS_SENSIBLES plus bas, donc TOUJOURS
        # interrompus pour confirmation utilisateur avant execution.
    },
    {
        "nom": "google_drive",
        "url_builder": _url_google_drive,
        "headers_builder": _headers_google_drive,
        "necessite_utilisateur": True,
        # Tri demande par Bourama le 01/09 (meme raison que la
        # desactivation de Notion cote web : trop d'outils MCP, les
        # etudiants n'en utilisent qu'une petite partie). Sur les 8
        # outils du Drive MCP officiel de Google, 7 retenus -- tout sauf
        # get_file_permissions (voir qui a acces a un fichier, jamais
        # utile a un etudiant).
        #
        # NOMS D'OUTILS NON VERIFIES EN CONDITIONS REELLES (comme
        # d'habitude pour un tiers externe, voir Pollinations dans
        # generation_images.py) -- ceux ci-dessous viennent de la
        # documentation Google (developers.google.com/workspace/drive/
        # api/reference/mcp), a reverifier au premier vrai test : si un
        # nom ne correspond pas exactement a celui expose par le serveur
        # MCP, cet outil precis restera simplement invisible (aucun
        # risque de planter le reste), a corriger ici le cas echeant.
        "outils_autorises": [
            "search_files",
            "read_file_content",
            "download_file_content",
            "list_recent_files",
            "get_file_metadata",
            "create_file",
            "copy_file",
        ],
    },
]

# Outils qui MODIFIENT reellement quelque chose chez l'utilisateur (creation,
# edition, suppression, deplacement...). main.py interrompt le flux et
# demande une confirmation explicite avant d'executer l'un de ces outils,
# quel que soit le serveur MCP dont il provient. Pour l'instant aucun
# outil d'ecriture n'est dans `outils_autorises` ci-dessus (donc cette
# liste n'a pas encore d'effet visible) : elle sert de garde-fou pret a
# l'emploi le jour ou on active par ex. "notion-create-pages".
OUTILS_SENSIBLES = {
    "notion-create-pages",
    "notion-update-page",
    "notion-move-pages",
    "notion-duplicate-page",
    "notion-create-database",
    "notion-update-data-source",
    "notion-create-comment",
    "notion-create-view",
    "notion-update-view",
    "notion-create-attachment",
    # 19/09/2026 (demande Bourama, répartition validée) -- les 8 outils
    # parmi les 25 nouveaux (voir REGISTRE_AFFICHAGE_OUTILS plus bas) qui
    # écrivent réellement quelque chose ou déclenchent une action côté
    # Notion (création/modification de dossier ou fichier, transformation
    # d'une page, lancement/pilotage d'une session d'agent tiers) : même
    # logique que les outils d'écriture Notion ci-dessus, TOUJOURS
    # interrompus pour confirmation avant exécution.
    "notion-create-folder",
    "notion-update-folder",
    "notion-create-file-upload",
    "notion-convert-page-to-skill",
    "notion-upload-skill",
    "notion-spawn-session",
    "notion-send-message-to-session",
    "notion-stop-session",
    # Google Drive (01/09) -- ÉCRIVENT réellement dans le Drive de
    # l'utilisateur (creation/copie de fichier), meme logique que les
    # outils d'ecriture Notion/GitHub ci-dessus : TOUJOURS interrompus
    # pour confirmation avant execution.
    "create_file",
    "copy_file",
    # ÉCRIT réellement sur un dépôt GitHub (voir
    # core/serveur_mcp_github.py, gerer_depot_github action
    # "modifier_fichier", consolidé le 26/08, ex modifier_fichier_depot_github) :
    # TOUJOURS interrompu pour confirmation, que ce soit en mode "direct"
    # (commit sur la branche de base) ou "branche_pr" (nouvelle branche,
    # Pull Request). Aucun des deux modes n'est silencieux. Format
    # "nom_outil:action" (voir plus bas pour gerer_document_bibliotheque) :
    # seule cette action est sensible, "explorer" et "lire_fichier" non.
    "gerer_depot_github:modifier_fichier",
    # Entrées "supprimer_programme"/"supprimer_matiere"/"supprimer_chapitre"/
    # "supprimer_document_programme"/"supprimer_exercice_programme"/
    # "supprimer_examen" retirées le 29/08/2026 -- ces outils n'existent
    # plus (fonctionnalité "Programme" désactivée et isolée, voir
    # _desactive_programme/LISEZ_MOI_NE_JAMAIS_REUTILISER.md).
    # Consolidé le 26/08 en une action de gerer_comportement (voir format
    # "nom_outil:action" expliqué plus bas pour gerer_document_bibliotheque).
    "gerer_comportement:supprimer",
    # Portés depuis core/serveur_mcp_espace.py le 17/08 (demande Bourama :
    # "ajoute à Clovis tout ce que Claude peut faire") -- mêmes garanties
    # que côté MCP externe (destructive_hint=True là-bas), transposées
    # ici via OUTILS_SENSIBLES puisque c'est le mécanisme propre à
    # l'agent interne.
    # Consolidé le 26/08 en une action de gerer_document_bibliotheque (et
    # non plus un outil séparé) : clé "nom_outil:action" -- seule cette
    # action précise est sensible, pas les 11 autres du même outil (voir
    # _est_outil_sensible dans main.py, qui sait lire ce format composite).
    "gerer_document_bibliotheque:supprimer",
    # Consolidé le 26/08 en une action de gerer_memoire_utilisateur (même
    # format composite "nom_outil:action").
    "gerer_memoire_utilisateur:effacer",
    # Dossiers de la bibliothèque personnelle (22/08, demande Bourama) :
    # peut supprimer des fichiers avec le dossier (voir
    # core/dossiers_bibliotheque.py:supprimer_dossier) -- irréversible,
    # toujours confirmé, même logique que les autres suppressions ci-dessus.
    # Consolidé le 26/08 en une action de gerer_dossier_bibliotheque (voir
    # format "nom_outil:action" expliqué au-dessus pour
    # gerer_document_bibliotheque:supprimer).
    "gerer_dossier_bibliotheque:supprimer",
}


# Registre d'affichage unique (2026-08-15, demande Bourama : "qu'à un
# nouvel outil, on ne touche pas au frontend" + "beaucoup d'outils
# affichent leur nom brut / une icône générique").
#
# AVANT : deux listes tenues à la main en parallèle -- NOMS_OUTILS_LISIBLES
# dans core/main.py (12 entrées sur 83 outils réels) côté backend, et
# OUTILS_DISPONIBLES dans classgpt-frontend/lib/outils.ts (~24/83) côté
# frontend -- d'où le nom brut ("generer_document_word") ou l'icône
# générique (Wrench) pour tout le reste.
#
# MAINTENANT : ce dict est la SEULE source de vérité pour les deux, sur
# les deux dépôts. Pour ajouter un nouvel outil, une seule ligne à ajouter
# ICI, rien d'autre :
# - Backend (core/main.py, _nom_lisible) : lit ce dict directement.
# - Frontend (classgpt-frontend/lib/outils.ts) : va chercher ce dict via
#   GET /api/outils/registre (voir api/outils_registre.py) au chargement
#   du chat -- aucune modification du frontend nécessaire, aucun rebuild
#   ni redéploiement du dépôt frontend.
#
# `icone` est une chaîne = un nom d'export de lucide-react (vérifié
# présent dans la version installée, classgpt-frontend/package.json).
# Exception : "notion-logo", un cas spécial connu du frontend (logo
# Notion, pas un export lucide-react).
#
# `onglet` correspond aux catégories du menu "Outils" du frontend :
# "generer" / "rechercher" / "action_app" / "utilitaires".
# `appli` (optionnel) : regroupe sous un connecteur externe ("github" ou
# "notion") dans l'onglet "action_app" -- absent pour tout le reste.
REGISTRE_AFFICHAGE_OUTILS = {
    # --- Génération ---
    "generer_document": {"label": "Génération d'un PDF/texte", "icone": "FileText", "onglet": "generer"},
    "generer_document_word": {"label": "Génération d'un Word", "icone": "FileType", "onglet": "generer"},
    "generer_document_excel": {"label": "Génération d'un Excel", "icone": "FileSpreadsheet", "onglet": "generer"},
    "generer_document_powerpoint": {"label": "Génération d'un PowerPoint", "icone": "Presentation", "onglet": "generer"},
    "generer_document_latex": {"label": "Génération d'un document LaTeX", "icone": "FileDigit", "onglet": "generer"},
    "generer_code": {"label": "Génération de code", "icone": "Code", "onglet": "generer"},
    "generer_site_zip": {"label": "Génération d'un site (zip)", "icone": "Package", "onglet": "generer"},
    "generer_bundle": {"label": "Génération d'une archive", "icone": "Archive", "onglet": "generer"},
    "generer_image": {"label": "Génération d'une image", "icone": "Image", "onglet": "generer"},
    "generer_audio": {"label": "Génération audio", "icone": "AudioLines", "onglet": "generer"},
    "lancer_generation_video": {"label": "Génération d'une vidéo", "icone": "Video", "onglet": "generer"},
    "lancer_generation_3d": {"label": "Génération d'un modèle 3D", "icone": "Box", "onglet": "generer"},
    "envoyer_pour_signature": {"label": "Envoi pour signature", "icone": "FileSignature", "onglet": "generer"},
    "consulter_statut_generation": {"label": "Vérification du statut d'une génération", "icone": "RefreshCw", "onglet": "generer"},
    "deployer_site": {"label": "Déploiement d'un site", "icone": "Rocket", "onglet": "generer"},
    "exporter_donnees": {"label": "Export de données", "icone": "FileOutput", "onglet": "generer"},
    "calculer_symbolique": {"label": "Calcul symbolique (résoudre, dériver, intégrer)", "icone": "Divide", "onglet": "generer"},
    # Ajouté 10/09/2026 (demande Bourama) : Wolfram n'avait aucune entrée
    # ici, donc aucun libellé français pour la recherche interne d'outils
    # (voir core/boucle_agent.py). "WolframLanguageEvaluator" est le nom
    # confirmé (mention explicite dans profils_agents.py + documentation
    # publique de Wolfram Cloud MCP, agenttools.wolfram.com/mcp) -- pas une
    # supposition. Ce serveur peut exposer d'autres outils non vérifiés ici
    # (WolframLanguageContext, TestReport...) : à ajouter au besoin si l'un
    # d'eux s'avère utilisé.
    "WolframLanguageEvaluator": {"label": "Calcul et données du monde réel (Wolfram)", "icone": "Calculator", "onglet": "generer"},

    # --- Recherche ---
    "tavily_search": {"label": "Recherche web", "icone": "Search", "onglet": "rechercher"},
    "tavily_extract": {"label": "Extraction d'une page", "icone": "FileSearch", "onglet": "rechercher"},
    "tavily_crawl": {"label": "Exploration d'un site", "icone": "Globe", "onglet": "rechercher"},
    "tavily_map": {"label": "Cartographie d'un site", "icone": "Map", "onglet": "rechercher"},
    "tavily_research": {"label": "Recherche approfondie", "icone": "BookOpen", "onglet": "rechercher"},
    # "chercher_fichier" retiré le 14/09/2026 (outil cassé, jamais de
    # user_id réel, voir core/outils_bibliotheque.py) -- remplacé par
    # gerer_fichier_conversation, onglet=None comme les autres outils
    # consolidés par action (voir plus bas).
    # Ajouté 01/09 -- recherche d'IMAGE existante sur le web (galerie),
    # à ne pas confondre avec generer_image ci-dessus (qui en crée une
    # nouvelle). Icône "ImageSearch" NON VÉRIFIÉE dans cette version de
    # lucide-react (0.383.0) -- repli automatique sur Wrench sinon, voir
    # resoudreIcone (clovis-frontend/lib/outils.ts).
    "rechercher_image": {"label": "Recherche d'image", "icone": "ImageSearch", "onglet": "rechercher"},
    # gerer_document_bibliotheque (consolidé le 26/08, ex 12 outils
    # séparés -- consulter_bibliotheque, consulter_bibliotheque_publique,
    # lister/ajouter/supprimer/classer/déclasser/ranger/retirer/lire_entier,
    # voir serveur_mcp_generation.py) : une seule entrée d'affichage
    # désormais, même onglet "rechercher" que l'ancien consulter_bibliotheque
    # (seule action manuellement cliquable, les autres restent onglet=None
    # en pratique côté modèle -- pas besoin de doublon d'entrée pour ça).
    "gerer_document_bibliotheque": {"label": "Bibliothèque personnelle", "icone": "Library", "onglet": "rechercher"},
    # Ajouté 14/09/2026 (demande Bourama) : outil séparé pour les
    # pièces jointes de conversation (origine="chat"), pas cliquable
    # manuellement (onglet=None), même logique que les autres outils
    # consolidés par action.
    "gerer_fichier_conversation": {"label": "Fichiers de la conversation", "icone": "Paperclip", "onglet": None},
    # Composites "nom_outil:action" (28/08, bug remonté par Bourama :
    # l'entrée générique ci-dessus s'affichait pour TOUTES les actions
    # de cet outil, y compris chercher_publique/trouver_catalogue_public/
    # lire_catalogue_public/lister_catalogue_public -- qui ne concernent
    # PAS la bibliothèque personnelle mais le catalogue public ou les
    # plugins publics. Même format composite que OUTILS_SENSIBLES
    # ci-dessus, lu ici par _nom_lisible (core/main.py) au lieu de
    # _est_outil_sensible. `onglet: None` volontaire : ne doivent jamais
    # apparaître comme bouton cliquable séparé dans le menu Outils (voir
    # docstring de la route /api/outils/registre) -- seul le libellé
    # affiché PENDANT/APRÈS l'exécution change, pas la liste des outils
    # sélectionnables.
    "gerer_document_bibliotheque:trouver_catalogue_public": {"label": "Catalogue public", "icone": "Library", "onglet": None},
    "gerer_document_bibliotheque:lire_catalogue_public": {"label": "Catalogue public", "icone": "Library", "onglet": None},
    "gerer_document_bibliotheque:lister_catalogue_public": {"label": "Catalogue public", "icone": "Library", "onglet": None},
    "gerer_base_connaissance": {"label": "Base de connaissances de Classinus", "icone": "BookMarked", "onglet": "rechercher"},

    # --- Action dans l'app : GitHub ---
    "gerer_depot_github": {"label": "Dépôt GitHub", "icone": "Github", "onglet": "action_app", "appli": "github"},

    # --- Action dans l'app : Notion ---
    "notion-search": {"label": "Recherche dans Notion", "icone": "notion-logo", "onglet": "action_app", "appli": "notion"},
    "notion-fetch": {"label": "Ouverture d'une page/base Notion", "icone": "FileSearch", "onglet": "action_app", "appli": "notion"},
    "notion-query-data-sources": {"label": "Interrogation d'une base Notion (SQL)", "icone": "Table2", "onglet": "action_app", "appli": "notion"},
    "notion-query-database-view": {"label": "Interrogation d'une vue Notion", "icone": "LayoutGrid", "onglet": "action_app", "appli": "notion"},
    "notion-query-meeting-notes": {"label": "Recherche dans les notes de réunion Notion", "icone": "StickyNote", "onglet": "action_app", "appli": "notion"},
    "notion-get-comments": {"label": "Lecture des commentaires Notion", "icone": "MessagesSquare", "onglet": "action_app", "appli": "notion"},
    "notion-get-async-task": {"label": "Suivi d'une tâche Notion en cours", "icone": "Clock", "onglet": "action_app", "appli": "notion"},
    "notion-get-teams": {"label": "Liste des équipes Notion", "icone": "Users", "onglet": "action_app", "appli": "notion"},
    "notion-get-users": {"label": "Liste des utilisateurs Notion", "icone": "UserCog", "onglet": "action_app", "appli": "notion"},
    "notion-download-attachment": {"label": "Téléchargement d'une pièce jointe Notion", "icone": "Download", "onglet": "action_app", "appli": "notion"},
    "notion-create-pages": {"label": "Création d'une page Notion", "icone": "FilePlus", "onglet": "action_app", "appli": "notion"},
    "notion-update-page": {"label": "Modification d'une page Notion", "icone": "Edit3", "onglet": "action_app", "appli": "notion"},
    "notion-move-pages": {"label": "Déplacement d'une page Notion", "icone": "Move", "onglet": "action_app", "appli": "notion"},
    "notion-duplicate-page": {"label": "Duplication d'une page Notion", "icone": "Copy", "onglet": "action_app", "appli": "notion"},
    "notion-create-database": {"label": "Création d'une base Notion", "icone": "Database", "onglet": "action_app", "appli": "notion"},
    "notion-update-data-source": {"label": "Modification du schéma d'une base Notion", "icone": "Settings2", "onglet": "action_app", "appli": "notion"},
    "notion-create-comment": {"label": "Commentaire dans Notion", "icone": "MessageSquare", "onglet": "action_app", "appli": "notion"},
    "notion-create-attachment": {"label": "Ajout d'une pièce jointe Notion", "icone": "Paperclip", "onglet": "action_app", "appli": "notion"},
    "notion-create-view": {"label": "Création d'une vue Notion", "icone": "PanelsTopLeft", "onglet": "action_app", "appli": "notion"},
    "notion-update-view": {"label": "Modification d'une vue Notion", "icone": "SlidersHorizontal", "onglet": "action_app", "appli": "notion"},

    # --- Action dans l'app : Notion (25 outils supplémentaires, 19/09/2026,
    # demande Bourama) --- le connecteur Notion en expose désormais 45 au
    # total (contre 20 avant, bloc ci-dessus), écart constaté en comparant
    # ce registre au catalogue Notion actuel. Ces 25 n'avaient encore aucune
    # entrée ici : invisibles à la recherche interne d'outils (le libellé
    # français de CE registre est ce qui sert de libelle_supplementaire à
    # rechercher_outils_pertinents, voir core/boucle_agent.py) et non
    # couverts par OUTILS_SENSIBLES. Tous les libellés incluent explicitement
    # le mot "Notion" (demande Bourama : sans ça, une recherche en français
    # matche mal -- même problème déjà rencontré avec Tavily).
    # Icônes vérifiées une à une dans lucide-react 0.383.0 installé
    # (classgpt-frontend/package.json), pas de repli Wrench attendu.
    "notion-ai-search": {"label": "Recherche IA dans Notion", "icone": "Sparkles", "onglet": "action_app", "appli": "notion"},
    "notion-search-agents": {"label": "Recherche d'agents Notion", "icone": "Users", "onglet": "action_app", "appli": "notion"},
    "notion-search-sessions": {"label": "Recherche de sessions d'agent Notion", "icone": "Search", "onglet": "action_app", "appli": "notion"},
    "notion-search-skills": {"label": "Recherche de skills Notion", "icone": "ScrollText", "onglet": "action_app", "appli": "notion"},
    "notion-query-multiple-data-sources": {"label": "Interrogation de plusieurs bases Notion", "icone": "Layers", "onglet": "action_app", "appli": "notion"},
    "notion-query-sessions": {"label": "Liste des sessions d'agent Notion", "icone": "ListChecks", "onglet": "action_app", "appli": "notion"},
    "notion-read-session-event": {"label": "Lecture d'un évènement de session Notion", "icone": "FileText", "onglet": "action_app", "appli": "notion"},
    "notion-list-favorite-pages": {"label": "Liste des pages favorites Notion", "icone": "Star", "onglet": "action_app", "appli": "notion"},
    "notion-list-private-pages": {"label": "Liste des pages privées Notion", "icone": "Lock", "onglet": "action_app", "appli": "notion"},
    "notion-list-recent-pages": {"label": "Liste des pages Notion récentes", "icone": "Clock", "onglet": "action_app", "appli": "notion"},
    "notion-list-session-events": {"label": "Historique d'une session d'agent Notion", "icone": "History", "onglet": "action_app", "appli": "notion"},
    "notion-list-shared-pages": {"label": "Liste des pages partagées Notion", "icone": "Share2", "onglet": "action_app", "appli": "notion"},
    "notion-get-session-status": {"label": "Statut d'une session d'agent Notion", "icone": "Activity", "onglet": "action_app", "appli": "notion"},
    "notion-get-tool-access": {"label": "Vérification des droits d'accès Notion", "icone": "ShieldCheck", "onglet": "action_app", "appli": "notion"},
    "notion-check-mcp-next-steps": {"label": "Vérification des étapes suivantes Notion", "icone": "ArrowRight", "onglet": "action_app", "appli": "notion"},
    "notion-download-skill": {"label": "Téléchargement d'un skill Notion", "icone": "Download", "onglet": "action_app", "appli": "notion"},
    "notion-show-advanced-analysis-next-steps": {"label": "Étapes suivantes d'analyse avancée Notion", "icone": "ArrowRight", "onglet": "action_app", "appli": "notion"},
    # --- Écriture/action (marqués sensibles, voir OUTILS_SENSIBLES plus haut) ---
    "notion-create-folder": {"label": "Création d'un dossier Notion", "icone": "FolderPlus", "onglet": "action_app", "appli": "notion"},
    "notion-update-folder": {"label": "Modification d'un dossier Notion", "icone": "FolderCog", "onglet": "action_app", "appli": "notion"},
    "notion-create-file-upload": {"label": "Envoi d'un fichier dans Notion", "icone": "UploadCloud", "onglet": "action_app", "appli": "notion"},
    "notion-convert-page-to-skill": {"label": "Conversion d'une page Notion en skill", "icone": "Wand2", "onglet": "action_app", "appli": "notion"},
    "notion-upload-skill": {"label": "Import d'un skill dans Notion", "icone": "Upload", "onglet": "action_app", "appli": "notion"},
    "notion-spawn-session": {"label": "Lancement d'une session d'agent Notion", "icone": "PlayCircle", "onglet": "action_app", "appli": "notion"},
    "notion-send-message-to-session": {"label": "Envoi d'un message à une session d'agent Notion", "icone": "MessageSquare", "onglet": "action_app", "appli": "notion"},
    "notion-stop-session": {"label": "Arrêt d'une session d'agent Notion", "icone": "StopCircle", "onglet": "action_app", "appli": "notion"},

    # --- Action dans l'app : Google Drive ---
    # Noms d'outils NON VÉRIFIÉS en conditions réelles, voir le
    # commentaire "outils_autorises" du serveur google_drive plus haut
    # dans ce fichier -- si un nom ne correspond pas, seul son libellé
    # reste invisible, rien d'autre ne casse.
    "search_files": {"label": "Recherche d'un fichier Drive", "icone": "FolderSearch", "onglet": "action_app", "appli": "google_drive"},
    "read_file_content": {"label": "Lecture d'un fichier Drive", "icone": "FileText", "onglet": "action_app", "appli": "google_drive"},
    "download_file_content": {"label": "Téléchargement d'un fichier Drive", "icone": "Download", "onglet": "action_app", "appli": "google_drive"},
    "list_recent_files": {"label": "Fichiers Drive récents", "icone": "Clock", "onglet": "action_app", "appli": "google_drive"},
    "get_file_metadata": {"label": "Infos d'un fichier Drive", "icone": "Info", "onglet": "action_app", "appli": "google_drive"},
    "create_file": {"label": "Création d'un fichier Drive", "icone": "FilePlus", "onglet": "action_app", "appli": "google_drive"},
    "copy_file": {"label": "Copie d'un fichier Drive", "icone": "Copy", "onglet": "action_app", "appli": "google_drive"},

    # --- Utilitaires ---
    #
    # !!! LIRE AVANT DE TOUCHER À CETTE SECTION (18/08, consigne explicite
    # de Bourama, à respecter systématiquement, séance après séance) !!!
    # Ce bouton s'est déjà fait polluer/casser plusieurs fois sans qu'on
    # le lui demande : le 17/08, 22 outils de programme s'y sont
    # retrouvés étiquetés "utilitaires" par erreur (28 entrées au lieu de
    # 6), et un simple crash de prod ailleurs dans le backend a suffi à le
    # faire disparaître entièrement. Consigne : NE JAMAIS ajouter un
    # outil ici (nouveau ou existant) juste parce qu'il EXISTE ou qu'il
    # semble "logique" de l'y mettre -- onglet="utilitaires" est une
    # décision consciente à chaque fois, prise avec Bourama, jamais un
    # défaut. Un nouvel outil backend (programme, bibliothèque, mémoire,
    # profil, etc.) doit être onglet=None SAUF instruction explicite du
    # contraire. Avant toute modif de ce fichier : relire ce bloc en
    # entier, et vérifier après coup que ce bouton affiche encore
    # exactement ce qu'il doit afficher (ne jamais faire confiance à un
    # "ça devrait marcher" sans revérifier la liste réelle).
    #
    # Mémoire/profil/message RETIRES d'ici le 18/08 (demande Bourama :
    # "enlève tout ce qui a lien avec mémoire ou profil et envoi d'un
    # message aussi") -- onglet=None comme les blocs Programme/
    # Bibliothèque plus bas : gardent leur icône pour la bulle "résultat
    # d'outil", mais ne sont plus des boutons cliquables ici. planifier_
    # rappel, lui, avait déjà été retiré le 17/08 (voir plus bas dans
    # l'historique git de ce fichier).
    "envoyer_message": {"label": "Envoi d'un message", "icone": "Send", "onglet": None},
    "gerer_memoire_utilisateur": {"label": "Ta mémoire", "icone": "Brain", "onglet": None},
    "consulter_profil_utilisateur": {"label": "Consultation de ton profil", "icone": "UserCircle", "onglet": None},
    "mettre_a_jour_profil_utilisateur": {"label": "Mise à jour de ton profil", "icone": "UserCog", "onglet": None},

    # --- Actions locales UI (préfixe "ui_") ---
    # Ajoutées ici le 17/08 (bug signalé par Bourama) : ces 6 entrées
    # existaient avant le 15/08 dans le bouton Utilitaires (venaient alors
    # de l'ancienne liste statique OUTILS_DISPONIBLES côté frontend), mais
    # ont disparu quand ce bouton est passé à ce registre backend comme
    # source vivante -- elles n'y avaient jamais été migrées. PAS de vrais
    # outils MCP (interceptées par le préfixe "ui_" dans BarreDeSaisie.tsx,
    # estOutilActif/executerActionOutil -- jamais envoyées au routeur ni au
    # modèle), donc aucun risque à les lister ici : ce registre est de
    # l'affichage pur (label/icône/onglet), pas la liste réelle des outils
    # exécutables. Autorisation par agent déjà en base (agents_actions_
    # locales + registre_outils_plateforme catégorie 4, vérifié le 17/08
    # pour "clovis" : les 6 y sont déjà cochées et disponibles).
    #
    # Depuis le 18/08 (voir avertissement en tête de section), CE SONT
    # LES 6 SEULES ENTRÉES QUE CE BOUTON DOIT AFFICHER. Si tu envisages
    # d'en ajouter une 7e, relis d'abord l'avertissement ci-dessus.
    "ui_localisation": {"label": "Joindre ma position", "icone": "MapPin", "onglet": "utilitaires"},
    "ui_formule": {"label": "Insérer une formule / réaction chimique", "icone": "Sigma", "onglet": "utilitaires"},
    "ui_editeur_maths": {"label": "Éditeur maths live (texte + formules)", "icone": "Calculator", "onglet": "utilitaires"},
    "ui_recherche": {"label": "Forcer une recherche web", "icone": "Search", "onglet": "utilitaires"},
    "ui_dessin": {"label": "Dessiner (géométrie, graphe, croquis)", "icone": "PenLine", "onglet": "utilitaires"},
    "ui_mode_vocal": {"label": "Mode vocal (bientôt disponible)", "icone": "AudioLines", "onglet": "utilitaires"},

    # --- Bibliothèque (gestion) --- toutes les actions de gestion
    # (lister/ajouter/supprimer/classer/déclasser/ranger/retirer/lire_entier)
    # sont désormais dans gerer_document_bibliotheque ci-dessus (fusion du
    # 26/08) -- plus d'entrées séparées ici, onglet=None n'avait de toute
    # façon aucun effet visuel puisque ces actions n'étaient jamais des
    # boutons cliquables (autonomie du modèle).

    # --- Dossiers de la bibliothèque (22/08, demande Bourama) : NON
    # consolidés (groupe distinct, resource "dossier" plutôt que
    # "document"), onglet=None (autonomie du modèle, pas des boutons
    # cliqués par l'utilisateur).
    # --- Dossiers de la bibliothèque (22/08, demande Bourama ; consolidé
    # le 26/08 en un seul outil gerer_dossier_bibliotheque, ex 5 outils
    # séparés) : onglet=None (autonomie du modèle, pas des boutons cliqués
    # par l'utilisateur).
    "gerer_dossier_bibliotheque": {"label": "Dossiers de la bibliothèque", "icone": "FolderTree", "onglet": None},

    # --- Historique (porté le 17/08 depuis serveur_mcp_espace.py) ---
    # Même onglet=None : section "Historique" à part entière de "Mon
    # espace", pas un bouton du menu Outils du chat.
    "lister_conversations_historique": {"label": "Liste des conversations passées", "icone": "History", "onglet": None},
    "lire_conversation_historique": {"label": "Lecture d'une conversation passée", "icone": "History", "onglet": None},

    # --- Programme adaptatif (interne) ---
    # Bloc entier retiré le 29/08/2026 (demande Bourama) : ces outils
    # n'existent plus (fonctionnalité "Programme" désactivée et isolée,
    # voir _desactive_programme/LISEZ_MOI_NE_JAMAIS_REUTILISER.md). NE
    # JAMAIS réintroduire ces entrées sans reconstruire la fonctionnalité
    # à neuf.
    "consulter_matiere_active": {"label": "Consultation de la matière active", "icone": "BookOpen", "onglet": None},
    "annuler_derniere_modification": {"label": "Annulation de la dernière modification", "icone": "Undo2", "onglet": None},
    "gerer_comportement": {"label": "Skills personnels", "icone": "ScrollText", "onglet": None},
    # Routage en deux niveaux (22/08/2026, demande Bourama) : jamais un
    # outil que le grand LLM appelle lui-même (pas de tool MCP réel), c'est
    # le petit routeur "à la skill" (core/main.py) qui déclenche ça en
    # coulisse -- mais on veut quand même que ça s'affiche comme un
    # résultat d'outil normal dans le fil de conversation (voir
    # OutilResultatBulle.tsx), d'où cette entrée dans ce registre bien qu'il
    # n'existe aucun outil MCP de ce nom.
    "consulter_skills_chapitres_matiere": {"label": "Consultation des skills des chapitres", "icone": "ScrollText", "onglet": None},

    # --- Confiance pédagogique : avancement des notions (Partie 3,
    # 06/09/2026) --- onglet=None, même logique que les blocs
    # "Programme adaptatif"/"Bibliothèque" plus haut : outils que le
    # modèle appelle lui-même en autonomie, jamais des boutons cliqués.
    "gerer_avancement_notions": {"label": "Avancement du programme", "icone": "ListChecks", "onglet": None},
    "consulter_avancement_notion": {"label": "Consultation de l'avancement", "icone": "BookOpen", "onglet": None},

    # --- Vérification "mode cours" (12/09/2026) --- outil unique qui
    # absorbe consulter_avancement_notion et consulter_signalements_pertinents
    # (les deux entrées ci-dessus/ci-dessous sont gardées pour l'affichage
    # correct des anciens messages déjà en base, jamais réutilisées pour
    # de nouveaux appels).
    "verifier_consignes_code_actif": {"label": "Vérification du code actif", "icone": "ShieldCheck", "onglet": None},

    # --- Actions sur le téléphone de l'étudiant (26/08/2026) ---
    # onglet=None, même logique que les blocs "Programme adaptatif"/
    # "Bibliothèque" plus haut : outils que le modèle appelle lui-même en
    # autonomie pendant la conversation, jamais des boutons cliqués.
    "gerer_dossier_telephone": {"label": "Dossiers du téléphone", "icone": "FolderPen", "onglet": None},
    "explorer_dossier": {"label": "Exploration du dossier en direct", "icone": "FolderOpen", "onglet": None},

    # --- Outil interne demander_outils (etape 5, chantier "demander_outils",
    # 06/09/2026, decision explicite de Bourama) --- onglet=None, meme
    # logique que les blocs ci-dessus : jamais un bouton cliquable (ce
    # n'est PAS un vrai outil MCP, voir routage_outils._outil_demander_outils).
    # Contrairement a garder_outils (totalement invisible, aucune entree
    # ici), demander_outils EST affiche : Bourama a choisi de montrer a
    # l'utilisateur le moment ou le modele realise en direct qu'il lui
    # manque un outil et va en chercher un -- voir le bloc d'evenements
    # statut/statut_termine/outil_resultat dans _agent_groq (core/boucle_agent.py).
    # Icone "PackageSearch" NON VERIFIEE dans cette version de lucide-react
    # (0.383.0, meme situation que "ImageSearch" plus haut) -- repli
    # automatique sur Wrench sinon, rien d'autre ne casse.
    "demander_outils": {"label": "Recherche d'un outil", "icone": "PackageSearch", "onglet": None},

    # --- Agent applicatif (chantier C, 16/09/2026) --- onglet=None,
    # meme logique que les blocs ci-dessus : l'etudiant ne clique jamais
    # ce bouton, c'est le modele qui l'appelle en autonomie. A activer
    # via forcer_rechargement_catalogue_outils ou redemarrage Railway
    # (cache 24h connu, voir plan-agent-applicatif-clovis.md section 2).
    "executer_action_application": {"label": "Action dans l'application", "icone": "MousePointerClick", "onglet": None},
    # Chantier D : lecture de l'etat pousse en continu, meme rappel de
    # cache 24h que ci-dessus.
    "lister_actions_disponibles": {"label": "Liste des actions disponibles", "icone": "MousePointerClick", "onglet": None},
    # Chantier F : filet de securite generique, meme rappel de cache 24h.
    "executer_clic_generique": {"label": "Clic générique dans l'application", "icone": "MousePointerClick", "onglet": None},
    # Chantier G : mode guidage, meme rappel de cache 24h.
    "montrer_element_application": {"label": "Pointer un élément de l'application", "icone": "MousePointerClick", "onglet": None},
}

# --- Categorisation pour demander_outils (19/09/2026, demande Bourama) ---
# Le pool total d'outils actifs (verifie en base le 19/09 : 40 sur le
# serveur "generation" + 45 Notion + 7 Drive + github/tavily) est devenu
# trop grand pour une seule recherche BM25 a plat : les 45 outils Notion
# se melangeaient entre eux et avec le reste, certains ne remontant
# quasiment jamais (signale par Bourama). Categories statiques, decidees
# a la main : un outil peut apparaitre dans plusieurs categories si
# besoin (simple liste Python, pas un mapping outil -> categorie unique).
#
# "notion" n'a volontairement AUCUNE liste figee ici : les 45 outils
# partagent tous le prefixe "notion-", verifie par prefixe dans
# outils_de_la_categorie() plus bas -- fiable meme si Notion ajoute encore
# des outils au connecteur, contrairement a une liste a remettre a jour a
# la main a chaque fois.
CATEGORIES_OUTILS = {
    "generation_documents": [
        "generer_document", "generer_document_word", "generer_document_excel",
        "generer_document_powerpoint", "generer_document_latex", "generer_code",
        "generer_site_zip", "generer_bundle", "generer_image", "deployer_site",
        "exporter_donnees", "calculer_symbolique",
    ],
    # rechercher_image range ici (avec Tavily), pas dans generation_documents :
    # onglet="rechercher" dans REGISTRE_AFFICHAGE_OUTILS ci-dessus, c'est une
    # recherche d'image EXISTANTE sur le web, pas une creation (voir
    # generer_image, qui lui reste dans generation_documents).
    "recherche_web": [
        "tavily_search", "tavily_extract", "tavily_crawl", "tavily_map",
        "tavily_research", "rechercher_image",
    ],
    "bibliotheque": [
        "gerer_document_bibliotheque", "gerer_dossier_bibliotheque",
        "gerer_fichier_conversation",
    ],
    "catalogue_public": [
        "gerer_entree_catalogue_public", "gerer_dossier_catalogue_public",
    ],
    "base_connaissance": ["gerer_base_connaissance"],
    "pedagogie": [
        "gerer_avancement_notions", "consulter_avancement_notion",
        "verifier_consignes_code_actif", "consulter_signalement",
        "consulter_signalements_pertinents", "enregistrer_note_signalement",
        "rattacher_signalement_notion",
    ],
    "comportement": ["gerer_comportement", "gerer_comportement_public"],
    "memoire": ["gerer_memoire_utilisateur"],
    "telephone_etudiant": [
        "gerer_dossier_telephone", "explorer_dossier", "gerer_action_mobile",
        "lire_temps_ecran", "gerer_session_concentration",
    ],
    "historique": ["lister_conversations_historique", "lire_conversation_historique"],
    "agent_applicatif": [
        "executer_action_application", "lister_actions_disponibles",
        "executer_clic_generique", "montrer_element_application",
    ],
    "github": ["gerer_depot_github"],
    "google_drive": [
        "search_files", "read_file_content", "download_file_content",
        "list_recent_files", "get_file_metadata", "create_file", "copy_file",
    ],
}

# Categories reconnues par prefixe de nom d'outil plutot que par liste
# figee (voir commentaire au-dessus de CATEGORIES_OUTILS).
CATEGORIES_OUTILS_PAR_PREFIXE = {
    "notion": "notion-",
}

NOMS_CATEGORIES_OUTILS = list(CATEGORIES_OUTILS.keys()) + list(CATEGORIES_OUTILS_PAR_PREFIXE.keys())

# Texte compact envoye dans la description de demander_outils (voir
# routage_outils._outil_demander_outils) : les categories evidentes sont
# nommees seules, les autres ont une parenthese pour lever l'ambiguite.
INDEX_CATEGORIES_OUTILS = (
    "Catégories : notion, google_drive, github, generation_documents, "
    "recherche_web (web + recherche d'image), bibliotheque (documents/dossiers "
    "personnels), catalogue_public, base_connaissance (Classinus lui même), "
    "pedagogie (avancement, signalements), comportement (skills), memoire, "
    "telephone_etudiant (mobile, écran, concentration), historique "
    "(conversations passées), agent_applicatif (actions dans l'appli)."
)


def outils_de_la_categorie(nom_categorie, outils_candidats):
    """
    Sous-ensemble de `outils_candidats` (liste au format outils_pour_llm,
    voir mcp_tools.py) appartenant a `nom_categorie`. Verifie d'abord
    CATEGORIES_OUTILS (liste figee de noms), puis
    CATEGORIES_OUTILS_PAR_PREFIXE (prefixe de nom, voir "notion").
    Categorie inconnue -> liste vide : jamais un repli silencieux sur
    toute la liste, un nom de categorie invalide doit rester sans
    resultat plutot que de chercher partout sans que personne ne le sache.
    """
    noms_fixes = set(CATEGORIES_OUTILS.get(nom_categorie, []))
    prefixe = CATEGORIES_OUTILS_PAR_PREFIXE.get(nom_categorie)
    return [
        o for o in outils_candidats
        if o["function"]["name"] in noms_fixes
        or (prefixe and o["function"]["name"].startswith(prefixe))
    ]

