"""
Registre des outils (bras) MCP actifs.

POUR AJOUTER UN NOUVEL OUTIL :
Ajoute une entree dans SERVEURS_MCP ci-dessous. C'est le seul fichier a
modifier. Ni mcp_tools.py (le moteur generique) ni main.py n'ont besoin
d'etre touches.

Deux modes d'authentification sont supportes, car les serveurs MCP ne
s'authentifient pas tous pareil :
- pas de cle du tout (ex: Wolfram)          -> url_builder seul
- cle envoyee en header HTTP (ex: Tavily)  -> url_builder + headers_builder
  (jamais de cle dans une URL : elle finit en clair dans les logs)

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
from connexions.higgsfield_mcp import obtenir_token_valide as obtenir_token_higgsfield
from connexions.platform_mcp_oauth import obtenir_token_valide as obtenir_token_platform_mcp

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


def _url_video(get_secret, user_id, agent_id, conversation_id=None):
    # Serveur dédié au montage vidéo (core/serveur_mcp_video.py).
    # Interrogé avec un contexte vidéo, ou sans vidéo jointe si le registre plateforme l'active.
    port = os.environ.get("PORT", "8000")
    from urllib.parse import urlencode
    params = urlencode({"user_id": user_id or "", "conversation_id": conversation_id or ""})
    return f"http://localhost:{port}/mcp/video/?{params}"


def _headers_video(get_secret, user_id, agent_id):
    # Jeton serveur-à-serveur : aucune clé ne passe dans l'URL.
    secret = get_secret("SUPABASE_SECRET")
    return {"Authorization": f"Bearer {secret}"} if secret else None


def _url_github(get_secret, user_id, agent_id, conversation_id=None):
    # Même logique que _url_generation ci-dessus -- serveur MCP interne
    # (core/serveur_mcp_github.py), pas un tiers externe.
    #
    # 21/10/2026 (demande de Bourama) : user_id ajouté en paramètre d'adresse,
    # comme pour _url_generation. Avant, l'outil ne savait jamais QUI l'appelait
    # et répondait "aucune personne connectée" pour toute action sur le compte
    # (mes dépôts, issues, écriture), même avec GitHub bien relié.
    port = os.environ.get("PORT", "8000")
    url = f"http://localhost:{port}/mcp/github"
    if user_id:
        url += f"?user_id={user_id}"
    return url


def _url_execution_code(get_secret, user_id, agent_id, conversation_id=None):
    from urllib.parse import urlencode

    port = os.environ.get("PORT", "8000")
    params = {"user_id": user_id}
    if conversation_id:
        params["conversation_id"] = conversation_id
    return f"http://localhost:{port}/mcp/execution-code?{urlencode(params)}"


def _headers_execution_code(get_secret, user_id, agent_id):
    secret = get_secret("SUPABASE_SECRET")
    return {"X-Classinus-Internal": secret} if secret else None


def _url_tavily(get_secret, user_id, agent_id, conversation_id=None):
    # 04/10/2026, demande Bourama : la cle n'est plus dans l'URL (elle
    # apparaissait en clair dans les logs Railway a chaque requete). Elle
    # passe maintenant par l'en-tete Authorization, voir _headers_tavily.
    return "https://mcp.tavily.com/mcp/"


def _headers_tavily(get_secret, user_id, agent_id):
    cle = get_secret("TAVILY_API_KEY")
    if not cle:
        return None
    return {"Authorization": f"Bearer {cle}"}


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


def _url_diagnostic_classtech(get_secret, user_id, agent_id, conversation_id=None):
    # 28/10/2026 (demande Bourama) : serveur d'outils MCP Class-Tech
    # (diagnostic téléphone puis PC). Serveur public sans
    # authentification : pas de headers_builder. URL prévue du service
    # Render class-tech-outils, à corriger ici si le service déployé a
    # une autre adresse.
    return "https://class-tech-outils.onrender.com/mcp/diagnostic"


def _headers_notion(get_secret, user_id, agent_id):
    # agent_id fait partie de la signature commune a tous les *_builder
    # (voir docstring en tete de fichier) mais n'est plus utilise ici :
    # la connexion Notion est scopee par user_id seul (compte unifie).
    token = obtenir_token_valide(user_id)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _url_higgsfield(get_secret, user_id, agent_id, conversation_id=None):
    return "https://mcp.higgsfield.ai/mcp"


def _headers_higgsfield(get_secret, user_id, agent_id):
    token = obtenir_token_higgsfield(user_id)
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _url_vercel_mcp(get_secret, user_id, agent_id, conversation_id=None):
    return "https://mcp.vercel.com"


def _headers_vercel_mcp(get_secret, user_id, agent_id):
    token = obtenir_token_platform_mcp("vercel_mcp", user_id)
    return {"Authorization": f"Bearer {token}"} if token else None


def _url_railway_mcp(get_secret, user_id, agent_id, conversation_id=None):
    return "https://mcp.railway.com"


def _headers_railway_mcp(get_secret, user_id, agent_id):
    token = obtenir_token_platform_mcp("railway_mcp", user_id)
    return {"Authorization": f"Bearer {token}"} if token else None


def _url_supabase_mcp(get_secret, user_id, agent_id, conversation_id=None):
    return "https://mcp.supabase.com/mcp"


def _headers_supabase_mcp(get_secret, user_id, agent_id):
    token = obtenir_token_platform_mcp("supabase_mcp", user_id)
    return {"Authorization": f"Bearer {token}"} if token else None


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




def _url_mcp_constant(endpoint):
    """Build a common URL builder for fixed remote MCP endpoints."""
    def _builder(get_secret, user_id, agent_id, conversation_id=None):
        return endpoint
    return _builder


def _headers_platform_mcp(service):
    """Authorization header for a personal OAuth connection to an official MCP server."""
    def _builder(get_secret, user_id, agent_id):
        token = obtenir_token_platform_mcp(service, user_id)
        return {"Authorization": f"Bearer {token}"} if token else None
    return _builder


def _url_google_workspace(endpoint):
    return _url_mcp_constant(endpoint)


def _headers_google_workspace(service):
    """Per-product Google Workspace token; Google Drive remains its existing connector."""
    def _builder(get_secret, user_id, agent_id):
        from connexions.oauth_generique import obtenir_token_valide as obtenir_token_google
        token = obtenir_token_google(service, user_id)
        return {"Authorization": f"Bearer {token}"} if token else None
    return _builder


def _headers_render_mcp(get_secret, user_id, agent_id):
    """Clé personnelle Render de l'utilisateur, envoyée au serveur MCP hébergé par Render."""
    from connexions.render_mcp import obtenir_token_valide as obtenir_cle_render
    token = obtenir_cle_render(user_id)
    return {"Authorization": f"Bearer {token}"} if token else None


def _url_netlify_mcp(get_secret, user_id, agent_id, conversation_id=None):
    port = os.environ.get("PORT", "8000")
    return f"http://localhost:{port}/mcp/netlify?user_id={user_id}"


def _headers_netlify_mcp(get_secret, user_id, agent_id):
    from connexions.netlify_mcp import obtenir_token_valide as obtener_token_netlify
    if not obtener_token_netlify(user_id):
        return None
    secret = get_secret("SUPABASE_SECRET")
    return {"X-Classinus-MCP-Internal": secret} if secret else None

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
        "headers_builder": _headers_tavily,
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
        "nom": "execution_code",
        "url_builder": _url_execution_code,
        "headers_builder": _headers_execution_code,
        "necessite_utilisateur": True,
    },
    {
        "nom": "video",
        "url_builder": _url_video,
        "headers_builder": _headers_video,
        "necessite_utilisateur": True,
        # Avec un contexte vidéo validé : forcé, comme avant. Sans vidéo jointe : proposé
        # via demander_outils (catégorie montage_video) quand le registre plateforme le
        # déclare disponible (migrations/2026_10_24_outils_montage_video.sql).
        # Ne pas ajouter ce serveur au menu d'outils manuel.
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
        "nom": "higgsfield_mcp",
        "url_builder": _url_higgsfield,
        "headers_builder": _headers_higgsfield,
        "necessite_utilisateur": True,
        # Prefixe ajoute au nom de chaque outil de ce serveur (voir mcp_tools.py) :
        # evite les collisions avec les autres serveurs et permet la categorie par prefixe.
        "prefixe_outils": "higgsfield_",
    },
    {
        "nom": "vercel_mcp",
        "url_builder": _url_vercel_mcp,
        "headers_builder": _headers_vercel_mcp,
        "necessite_utilisateur": True,
        # Prefixe ajoute au nom de chaque outil de ce serveur (voir mcp_tools.py) :
        # evite les collisions avec les autres serveurs et permet la categorie par prefixe.
        "prefixe_outils": "vercel_",
    },
    {
        "nom": "railway_mcp",
        "url_builder": _url_railway_mcp,
        "headers_builder": _headers_railway_mcp,
        "necessite_utilisateur": True,
        # Prefixe ajoute au nom de chaque outil de ce serveur (voir mcp_tools.py) :
        # evite les collisions avec les autres serveurs et permet la categorie par prefixe.
        "prefixe_outils": "railway_",
    },
    {
        "nom": "supabase_mcp",
        "url_builder": _url_supabase_mcp,
        "headers_builder": _headers_supabase_mcp,
        "necessite_utilisateur": True,
        # Prefixe ajoute au nom de chaque outil de ce serveur (voir mcp_tools.py) :
        # evite les collisions avec les autres serveurs et permet la categorie par prefixe.
        "prefixe_outils": "supabase_",
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

    # Official Google Workspace MCP servers. Drive is already registered above.
    {
        "nom": "google_gmail_mcp",
        "url_builder": _url_google_workspace("https://gmailmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_gmail_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gmail_",
    },
    {
        "nom": "google_docs_mcp",
        "url_builder": _url_google_workspace("https://docsmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_docs_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gdocs_",
    },
    {
        "nom": "google_sheets_mcp",
        "url_builder": _url_google_workspace("https://sheetsmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_sheets_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gsheets_",
    },
    {
        "nom": "google_slides_mcp",
        "url_builder": _url_google_workspace("https://slidesmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_slides_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gslides_",
    },
    {
        "nom": "google_calendar_mcp",
        "url_builder": _url_google_workspace("https://calendarmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_calendar_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gcal_",
    },
    {
        "nom": "google_chat_mcp",
        "url_builder": _url_google_workspace("https://chatmcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_chat_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gchat_",
    },
    {
        "nom": "google_classroom_mcp",
        "url_builder": _url_google_workspace("https://classroommcp.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_classroom_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gclass_",
    },
    {
        "nom": "google_people_mcp",
        "url_builder": _url_google_workspace("https://people.googleapis.com/mcp/v1"),
        "headers_builder": _headers_google_workspace("google_people_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "gpeople_",
    },
    {
        "nom": "microsoft_mcp",
        "url_builder": _url_mcp_constant("https://mcp.svc.cloud.microsoft/enterprise"),
        "headers_builder": _headers_platform_mcp("microsoft_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "ms365_",
    },
    {
        "nom": "render_mcp",
        "url_builder": _url_mcp_constant("https://mcp.render.com/mcp"),
        "headers_builder": _headers_render_mcp,
        "necessite_utilisateur": True,
        "prefixe_outils": "render_",
    },
    {
        "nom": "cloudflare_mcp",
        "url_builder": _url_mcp_constant("https://mcp.cloudflare.com/mcp"),
        "headers_builder": _headers_platform_mcp("cloudflare_mcp"),
        "necessite_utilisateur": True,
        "prefixe_outils": "cloudflare_",
    },
    {
        "nom": "netlify_mcp",
        "url_builder": _url_netlify_mcp,
        "headers_builder": _headers_netlify_mcp,
        "necessite_utilisateur": True,
        "prefixe_outils": "netlify_",
    },
    {
        "nom": "diagnostic_classtech",
        "url_builder": _url_diagnostic_classtech,
        # Pas de headers_builder : serveur public (phase test).
        # Pas de necessite_utilisateur : dispo pour tout le monde.
        # Pas d'outils_autorises : tous les outils du serveur exposés.
        # 29/10/2026 : via_app_telephone, l'exécution passe par l'appli PC
        # de l'utilisateur (canal agent applicatif type "outil_telephone",
        # relais local seul à voir le téléphone), jamais par le cloud
        # Render (voir _appeler_outil_telephone_via_app). Le catalogue
        # (schémas) vient toujours de Render.
        "via_app_telephone": True,
        # Sondes sans telephone (ping, verification, resume de symptome) :
        # toujours executees sur le cloud Render, meme sans appli PC
        # connectee (voir _route_via_app_telephone).
        "outils_serveur_seul": ["ping_serveur", "verifier_chaine", "resumer_symptome"],
    },
]

# Serveurs MCP personnels dont les outils portent un prefixe (voir
# "prefixe_outils" dans SERVEURS_MCP). Leur catalogue est trop grand et change
# trop souvent pour une liste a la main : un outil de ces serveurs est
# SENSIBLE (confirmation obligatoire) sauf s'il est reconnu en lecture seule.
PREFIXES_SERVEURS_PERSONNELS = tuple(
    s["prefixe_outils"] for s in SERVEURS_MCP if s.get("prefixe_outils")
) + ("custommcp_",)

# Premier mot du nom reel (tirets lus comme "_") d'un outil de lecture seule.
VERBES_LECTURE_SERVEURS_PERSONNELS = {
    "get", "list", "search", "fetch", "read", "describe", "whoami",
    "aggregate", "count", "query", "domain", "environment", "http",
    # Verbes français des outils du pont Netlify et de futurs MCP internes.
    "lister", "consulter", "rechercher", "lire", "explorer", "obtenir", "verifier",
}

# Lectures seules dont le nom commence par "generate" (verbe volontairement
# absent de la liste ci-dessus : "generate" cree souvent quelque chose, comme
# la generation d'une video ou d'un domaine public).
LECTURES_EXPLICITES_SERVEURS_PERSONNELS = {
    "generate_typescript_types", "generate_route",
    # Lecture seule du MCP Microsoft Graph Enterprise en préversion.
    "microsoft_graph_get", "microsoft_graph_suggest_queries", "microsoft_graph_list_properties",
}

# Outils en apparence de lecture mais qui exposent un secret (valeur de
# variable, identifiants) ou fabriquent un acces : toujours confirmes.
LECTURES_A_CONFIRMER_SERVEURS_PERSONNELS = {
    "get_access_to_vercel_url", "web_fetch_vercel_url", "get_shared_env_var",
    "get_project_env", "filter_project_envs", "get_bucket_credentials",
    "list_variables", "get_edge_config_token", "get_edge_config_tokens",
}


def est_outil_sensible_serveur_personnel(nom_outil):
    """
    True si `nom_outil` (nom expose au LLM, prefixe compris) vient d'un
    serveur personnel prefixe et n'est pas reconnu en lecture seule.
    False pour tout autre outil (les autres suivent OUTILS_SENSIBLES).
    """
    for prefixe in PREFIXES_SERVEURS_PERSONNELS:
        if nom_outil.startswith(prefixe):
            # Un outil externe arbitraire n'a pas de convention de lecture fiable :
            # même un nom qui commence par get/list doit être confirmé par l'utilisateur.
            if prefixe == "custommcp_":
                return True
            reel = nom_outil[len(prefixe):].replace("-", "_")
            if reel in LECTURES_A_CONFIRMER_SERVEURS_PERSONNELS:
                return True
            if reel in LECTURES_EXPLICITES_SERVEURS_PERSONNELS:
                return False
            return reel.split("_")[0] not in VERBES_LECTURE_SERVEURS_PERSONNELS
    return False


NOMS_PLATEFORMES_PAR_PREFIXE = {
    "higgsfield_": "Higgsfield",
    "vercel_": "Vercel",
    "railway_": "Railway",
    "supabase_": "Supabase",
    "gmail_": "Gmail",
    "gdocs_": "Google Docs",
    "gsheets_": "Google Sheets",
    "gslides_": "Google Slides",
    "gcal_": "Google Calendar",
    "gchat_": "Google Chat",
    "gclass_": "Google Classroom",
    "gpeople_": "Google People",
    "ms365_": "Microsoft",
    "render_": "Render",
    "cloudflare_": "Cloudflare",
    "netlify_": "Netlify",
}


def plateforme_outil_personnel(nom_outil):
    """
    Nom lisible de la plateforme d'où vient un outil MCP préfixé.
    Les services Google gardent leur nom complet dans les confirmations,
    au lieu des préfixes techniques qui évitent les collisions.
    """
    for prefixe in PREFIXES_SERVEURS_PERSONNELS:
        if nom_outil.startswith(prefixe):
            if prefixe == "custommcp_":
                return "Serveur MCP personnalisé"
            return NOMS_PLATEFORMES_PAR_PREFIXE.get(prefixe, prefixe.rstrip("_").capitalize())
    return None


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
    # Higgsfield (20/10/2026, demande de Bourama) : lance une generation
    # video par la cle API, potentiellement payante, donc TOUJOURS
    # interrompue pour confirmation avant execution.
    "lancer_video_higgsfield",
    # Image Higgsfield (25/10/2026) : payante aussi, donc TOUJOURS interrompue pour confirmation.
    "generer_image_higgsfield",
    # ÉCRIT réellement sur un dépôt GitHub (voir
    # core/serveur_mcp_github.py, gerer_depot_github action
    # "modifier_fichier", consolidé le 26/08, ex modifier_fichier_depot_github) :
    # TOUJOURS interrompu pour confirmation, que ce soit en mode "direct"
    # (commit sur la branche de base) ou "branche_pr" (nouvelle branche,
    # Pull Request). Aucun des deux modes n'est silencieux. Format
    # "nom_outil:action" (voir plus bas pour gerer_document_bibliotheque) :
    # seule cette action est sensible, "explorer" et "lire_fichier" non.
    "gerer_depot_github:modifier_fichier",
    # 25/10/2026 (demande Bourama) : ouvrir un domaine du réseau du workspace d'exécution de code
    # n'est jamais automatique, l'élève doit confirmer. Valable pour la conversation seulement.
    "gerer_execution_code:demander_acces_reseau",
    # Actions GitHub ajoutées le 20/10/2026 qui écrivent ou agissent au nom
    # de la personne connectée : toutes interrompues pour confirmation.
    "gerer_depot_github:creer_issue",
    "gerer_depot_github:commenter",
    "gerer_depot_github:fermer_ou_rouvrir_issue",
    "gerer_depot_github:creer_branche",
    "gerer_depot_github:ouvrir_pull_request",
    "gerer_depot_github:supprimer_fichier",
    "gerer_depot_github:fusionner_pull_request",
    "gerer_depot_github:etoiler",
    "gerer_depot_github:forker",
    "gerer_depot_github:creer_depot",
    "gerer_depot_github:relancer_ci",
    # Entrées "supprimer_programme"/"supprimer_matiere"/"supprimer_chapitre"/
    # "supprimer_document_programme"/"supprimer_exercice_programme"/
    # "supprimer_examen" retirées le 29/08/2026 -- ces outils n'existent
    # plus (fonctionnalité "Programme" désactivée et isolée, voir
    # _desactive_programme/LISEZ_MOI_NE_JAMAIS_REUTILISER.md).
    # Consolidé le 26/08 en une action de gerer_comportement, renommé gerer_configuration le 25/10 (voir format
    # "nom_outil:action" expliqué plus bas pour gerer_document_bibliotheque).
    "gerer_configuration:supprimer",
    # Skills avec dossier et fichiers (25/10/2026) : deux actions destructives.
    "gerer_skill:supprimer",
    "gerer_skill:supprimer_fichier",
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
    # Dossiers de la bibliothèque personnelle (22/08, demande Bourama) :
    # peut supprimer des fichiers avec le dossier (voir
    # core/dossiers_bibliotheque.py:supprimer_dossier) -- irréversible,
    # toujours confirmé, même logique que les autres suppressions ci-dessus.
    # Consolidé le 26/08 en une action de gerer_dossier_bibliotheque (voir
    # format "nom_outil:action" expliqué au-dessus pour
    # gerer_document_bibliotheque:supprimer).
    "gerer_dossier_bibliotheque:supprimer",
    # 28/10/2026 : action réelle du palier 80 % (vide les caches, qui
    # se reconstruisent seuls ensuite, jamais les données des applis).
    "vider_cache_applis",
    # 28/10/2026 : actions réelles du serveur diagnostic Class-Tech
    # (palier 100 %, sans root). Bip, vibration, appli photo : effet
    # physique. revoquer_permission : retire vraiment un accès.
    "tester_haut_parleur",
    "tester_vibreur",
    "tester_camera",
    "revoquer_permission",
    # 28/10/2026 : palier root DESACTIVE (19 outils, confirmation
    # exigee pour chacun, meme les lectures : un telephone roote
    # expose tout le systeme). Activation seulement sur ordre de Bourama.
    "root_verifier_acces",
    "root_lire_infos_root",
    "root_lister_fichiers_systeme",
    "root_lire_fichier_systeme",
    "root_lire_erreurs_noyau",
    "root_lire_paniques_passees",
    "root_lire_partitions",
    "root_verifier_integrite",
    "root_lire_batterie_brute",
    "root_lire_temperatures",
    "root_reinitialiser_stats_batterie",
    "root_lire_firmware",
    "root_valider_slot_demarre",
    "root_lister_processus",
    "root_lire_wakelocks",
    "root_nettoyer_fichiers_crash",
    "root_vider_cache_dalvik",
    "root_forcer_trim",
    "root_redemarrer",
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
# Exceptions : "notion-logo" et "github-logo", cas spéciaux connus du frontend (logos
# de marque, pas des exports lucide-react).
#
# `onglet` correspond aux catégories du menu "Outils" du frontend :
# "generer" / "rechercher" / "action_app" / "utilitaires".
# `appli` (optionnel) : regroupe sous un connecteur externe ("github" ou
# "notion") dans l'onglet "action_app" -- absent pour tout le reste.
# 05/10/2026 (demande Bourama) : libellés des 12 outils à actions raccourcis, car le chat
# affiche "Verbe (libellé)" et passait à la ligne sur téléphone. Garder ces libellés courts
# (environ 18 caractères maximum) pour tout nouvel outil à actions.
# 05/10/2026 (demande Bourama) : libellés des outils sans action raccourcis aussi (28 caractères
# au plus), pour éviter les retours à la ligne du chat sur téléphone.
REGISTRE_AFFICHAGE_OUTILS = {
    # --- Génération ---
    "generer_document": {"label": "Génération d'un PDF/texte", "icone": "FileText", "onglet": "generer"},
    "generer_document_word": {"label": "Génération d'un Word", "icone": "FileType", "onglet": "generer"},
    "generer_document_excel": {"label": "Génération d'un Excel", "icone": "FileSpreadsheet", "onglet": "generer"},
    "generer_document_powerpoint": {"label": "Génération d'un PowerPoint", "icone": "Presentation", "onglet": "generer"},
    "generer_document_latex": {"label": "Génération d'un document LaTeX", "icone": "FileDigit", "onglet": "generer"},
    "generer_code": {"label": "Génération de code", "icone": "Code", "onglet": "generer"},
    "gerer_execution_code": {"label": "Exécution de code", "icone": "Play", "onglet": "generer"},
    # Une icône et un libellé par action de l'outil (24/10/2026, demande de Bourama). Entrées
    # composites "outil:action", jamais cliquables dans le menu Outils (onglet None) : seul
    # l'affichage dans le chat change. Libellés de 18 caractères au plus (téléphone).
    "gerer_execution_code:run_code": {"label": "Exécution de code", "icone": "Play", "onglet": None},
    "gerer_execution_code:run_command": {"label": "Commande shell", "icone": "Terminal", "onglet": None},
    "gerer_execution_code:write_file": {"label": "Ajout d'un fichier", "icone": "FilePlus", "onglet": None},
    "gerer_execution_code:importer_fichier": {"label": "Import de fichier", "icone": "FilePlus", "onglet": None},
    "gerer_execution_code:read_file": {"label": "Lecture de fichier", "icone": "FileText", "onglet": None},
    "gerer_execution_code:list_files": {"label": "Liste des fichiers", "icone": "FolderOpen", "onglet": None},
    "gerer_execution_code:download_files": {"label": "Export de fichiers", "icone": "Download", "onglet": None},
    "gerer_execution_code:demander_acces_reseau": {"label": "Accès à un site", "icone": "Globe", "onglet": None},
    "gerer_execution_code:network": {"label": "Réseau autorisé", "icone": "Terminal", "onglet": None},
    "gerer_execution_code:close": {"label": "Fin de l'espace", "icone": "Power", "onglet": None},
    "generer_site_zip": {"label": "Génération d'un site (zip)", "icone": "Package", "onglet": "generer"},
    "generer_bundle": {"label": "Génération d'une archive", "icone": "Archive", "onglet": "generer"},
    "generer_image": {"label": "Génération d'une image", "icone": "Image", "onglet": "generer"},
    "generer_audio": {"label": "Génération audio", "icone": "AudioLines", "onglet": "generer"},
    "lancer_generation_video": {"label": "Génération d'une vidéo", "icone": "Video", "onglet": "generer"},
    "lancer_generation_3d": {"label": "Génération d'un modèle 3D", "icone": "Box", "onglet": "generer"},
    "envoyer_pour_signature": {"label": "Envoi pour signature", "icone": "FileSignature", "onglet": "generer"},
    "consulter_statut_generation": {"label": "Statut d'une génération", "icone": "RefreshCw", "onglet": "generer"},
    "deployer_site": {"label": "Déploiement d'un site", "icone": "Rocket", "onglet": "generer"},
    "exporter_donnees": {"label": "Export de données", "icone": "FileOutput", "onglet": "generer"},
    "calculer_symbolique": {"label": "Calcul symbolique", "icone": "Divide", "onglet": "generer"},
    # Ajouté 10/09/2026 (demande Bourama) : Wolfram n'avait aucune entrée
    # ici, donc aucun libellé français pour la recherche interne d'outils
    # (voir core/boucle_agent.py). "WolframLanguageEvaluator" est le nom
    # confirmé (mention explicite dans profils_agents.py + documentation
    # publique de Wolfram Cloud MCP, agenttools.wolfram.com/mcp) -- pas une
    # supposition. Ce serveur peut exposer d'autres outils non vérifiés ici
    # (WolframLanguageContext, TestReport...) : à ajouter au besoin si l'un
    # d'eux s'avère utilisé.
    "WolframLanguageEvaluator": {"label": "Calcul Wolfram", "icone": "Calculator", "onglet": "generer"},

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
    "rechercher_image": {"label": "Recherche d'image", "icone": "Images", "onglet": "rechercher"},
    # Ajouté 06/10 : recherche de vidéos YouTube (cartes de vidéos dans le chat).
    "rechercher_video": {"label": "Recherche de vidéo", "icone": "Video", "onglet": "rechercher"},
    # Ajouté 07/10 : lecture de ce qui est dit dans une vidéo YouTube (sous-titres).
    "lire_video": {"label": "Lecture d'une vidéo", "icone": "FileSearch", "onglet": "rechercher"},
    # Ajouté 09/10/2026 (demande Bourama, lot 1 du chantier Internet Archive) :
    # recherche d'un livre ou d'un PDF hors de Classinus, catégorie
    # documents_externes. Icône "Landmark" vérifiée dans lucide-react 0.383.0
    # (la version du frontend), et distincte de toutes les autres du registre.
    "rechercher_document_externe": {"label": "Recherche de document", "icone": "Landmark", "onglet": "rechercher"},
    # Ajouté 09/10 : lecture du texte d'un livre ou PDF Internet Archive (lot 2).
    "lire_document_internet_archive": {"label": "Lecture d'un document", "icone": "Glasses", "onglet": "rechercher"},
    # Ajouté 10/10 : lecteur unique d'un fichier externe à partir de son lien direct.
    "lire_document_externe": {"label": "Lecture d'un fichier externe", "icone": "ScanText", "onglet": "rechercher"},
    # gerer_document_bibliotheque (consolidé le 26/08, ex 12 outils
    # séparés -- consulter_bibliotheque, consulter_bibliotheque_publique,
    # lister/ajouter/supprimer/classer/déclasser/ranger/retirer/lire_entier,
    # voir serveur_mcp_generation.py) : une seule entrée d'affichage
    # désormais, même onglet "rechercher" que l'ancien consulter_bibliotheque
    # (seule action manuellement cliquable, les autres restent onglet=None
    # en pratique côté modèle -- pas besoin de doublon d'entrée pour ça).
    "gerer_document_bibliotheque": {"label": "Ma bibliothèque", "icone": "Library", "onglet": "rechercher"},
    # Ajouté 14/09/2026 (demande Bourama) : outil séparé pour les
    # pièces jointes de conversation (origine="chat"), pas cliquable
    # manuellement (onglet=None), même logique que les autres outils
    # consolidés par action.
    "gerer_fichier_conversation": {"label": "Fichiers du chat", "icone": "Paperclip", "onglet": None},
    # Ajouté 26/10/2026 : lecture, à la demande du modèle, d'une vidéo ou d'un audio joint.
    "lire_media_conversation": {"label": "Lecture d'une vidéo ou d'un audio joint", "icone": "FileSearch", "onglet": "rechercher"},
    # Ajouté 27/10/2026 : lecture, à la demande du modèle, d'un document joint.
    "lire_document_conversation": {"label": "Lecture d'un document joint", "icone": "FileSearch", "onglet": "rechercher"},
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
    "gerer_base_connaissance": {"label": "Aide Classinus", "icone": "BookMarked", "onglet": "rechercher"},

    # --- Action dans l'app : GitHub ---
    "gerer_depot_github": {"label": "Dépôt GitHub", "icone": "github-logo", "onglet": "action_app", "appli": "github"},

    # --- Action dans l'app : Notion ---
    "notion-search": {"label": "Recherche dans Notion", "icone": "notion-logo", "onglet": "action_app", "appli": "notion"},
    "notion-fetch": {"label": "Ouvrir une page Notion", "icone": "FileSearch", "onglet": "action_app", "appli": "notion"},
    "notion-query-data-sources": {"label": "Base Notion (SQL)", "icone": "Table2", "onglet": "action_app", "appli": "notion"},
    "notion-query-database-view": {"label": "Interrogation d'une vue Notion", "icone": "LayoutGrid", "onglet": "action_app", "appli": "notion"},
    "notion-query-meeting-notes": {"label": "Notes de réunion Notion", "icone": "StickyNote", "onglet": "action_app", "appli": "notion"},
    "notion-get-comments": {"label": "Commentaires Notion", "icone": "MessagesSquare", "onglet": "action_app", "appli": "notion"},
    "notion-get-async-task": {"label": "Tâche Notion en cours", "icone": "Clock", "onglet": "action_app", "appli": "notion"},
    "notion-get-teams": {"label": "Liste des équipes Notion", "icone": "Users", "onglet": "action_app", "appli": "notion"},
    "notion-get-users": {"label": "Liste des utilisateurs Notion", "icone": "UserCog", "onglet": "action_app", "appli": "notion"},
    "notion-download-attachment": {"label": "Pièce jointe Notion", "icone": "Download", "onglet": "action_app", "appli": "notion"},
    "notion-create-pages": {"label": "Création d'une page Notion", "icone": "FilePlus", "onglet": "action_app", "appli": "notion"},
    "notion-update-page": {"label": "Modification d'une page Notion", "icone": "Edit3", "onglet": "action_app", "appli": "notion"},
    "notion-move-pages": {"label": "Déplacement d'une page Notion", "icone": "Move", "onglet": "action_app", "appli": "notion"},
    "notion-duplicate-page": {"label": "Duplication d'une page Notion", "icone": "Copy", "onglet": "action_app", "appli": "notion"},
    "notion-create-database": {"label": "Création d'une base Notion", "icone": "Database", "onglet": "action_app", "appli": "notion"},
    "notion-update-data-source": {"label": "Schéma d'une base Notion", "icone": "Settings2", "onglet": "action_app", "appli": "notion"},
    "notion-create-comment": {"label": "Commentaire dans Notion", "icone": "MessageSquare", "onglet": "action_app", "appli": "notion"},
    "notion-create-attachment": {"label": "Joindre un fichier Notion", "icone": "Paperclip", "onglet": "action_app", "appli": "notion"},
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
    "notion-search-sessions": {"label": "Recherche de sessions Notion", "icone": "Search", "onglet": "action_app", "appli": "notion"},
    "notion-search-skills": {"label": "Recherche de skills Notion", "icone": "ScrollText", "onglet": "action_app", "appli": "notion"},
    "notion-query-multiple-data-sources": {"label": "Plusieurs bases Notion", "icone": "Layers", "onglet": "action_app", "appli": "notion"},
    "notion-query-sessions": {"label": "Sessions Notion", "icone": "ListChecks", "onglet": "action_app", "appli": "notion"},
    "notion-read-session-event": {"label": "Évènement de session Notion", "icone": "FileText", "onglet": "action_app", "appli": "notion"},
    "notion-list-favorite-pages": {"label": "Pages favorites Notion", "icone": "Star", "onglet": "action_app", "appli": "notion"},
    "notion-list-private-pages": {"label": "Liste des pages privées Notion", "icone": "Lock", "onglet": "action_app", "appli": "notion"},
    "notion-list-recent-pages": {"label": "Pages Notion récentes", "icone": "Clock", "onglet": "action_app", "appli": "notion"},
    "notion-list-session-events": {"label": "Historique de session Notion", "icone": "History", "onglet": "action_app", "appli": "notion"},
    "notion-list-shared-pages": {"label": "Pages partagées Notion", "icone": "Share2", "onglet": "action_app", "appli": "notion"},
    "notion-get-session-status": {"label": "Statut de session Notion", "icone": "Activity", "onglet": "action_app", "appli": "notion"},
    "notion-get-tool-access": {"label": "Droits d'accès Notion", "icone": "ShieldCheck", "onglet": "action_app", "appli": "notion"},
    "notion-check-mcp-next-steps": {"label": "Étapes suivantes Notion", "icone": "ArrowRight", "onglet": "action_app", "appli": "notion"},
    "notion-download-skill": {"label": "Télécharger un skill Notion", "icone": "Download", "onglet": "action_app", "appli": "notion"},
    "notion-show-advanced-analysis-next-steps": {"label": "Analyse avancée Notion", "icone": "ArrowRight", "onglet": "action_app", "appli": "notion"},
    # --- Écriture/action (marqués sensibles, voir OUTILS_SENSIBLES plus haut) ---
    "notion-create-folder": {"label": "Création d'un dossier Notion", "icone": "FolderPlus", "onglet": "action_app", "appli": "notion"},
    "notion-update-folder": {"label": "Modifier un dossier Notion", "icone": "FolderCog", "onglet": "action_app", "appli": "notion"},
    "notion-create-file-upload": {"label": "Envoi d'un fichier dans Notion", "icone": "UploadCloud", "onglet": "action_app", "appli": "notion"},
    "notion-convert-page-to-skill": {"label": "Page Notion en skill", "icone": "Wand2", "onglet": "action_app", "appli": "notion"},
    "notion-upload-skill": {"label": "Import d'un skill dans Notion", "icone": "Upload", "onglet": "action_app", "appli": "notion"},
    "notion-spawn-session": {"label": "Lancer une session Notion", "icone": "PlayCircle", "onglet": "action_app", "appli": "notion"},
    "notion-send-message-to-session": {"label": "Message à une session Notion", "icone": "MessageSquare", "onglet": "action_app", "appli": "notion"},
    "notion-stop-session": {"label": "Arrêt de session Notion", "icone": "StopCircle", "onglet": "action_app", "appli": "notion"},

    # --- Action dans l'app : Google Drive ---
    # Noms d'outils NON VÉRIFIÉS en conditions réelles, voir le
    # commentaire "outils_autorises" du serveur google_drive plus haut
    # dans ce fichier -- si un nom ne correspond pas, seul son libellé
    # reste invisible, rien d'autre ne casse.
    "search_files": {"label": "Recherche d'un fichier Drive", "icone": "FolderSearch", "onglet": "action_app", "appli": "google_drive"},
    "read_file_content": {"label": "Lecture d'un fichier Drive", "icone": "FileText", "onglet": "action_app", "appli": "google_drive"},
    "download_file_content": {"label": "Téléchargement Drive", "icone": "Download", "onglet": "action_app", "appli": "google_drive"},
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
    # Nouvelle mémoire élève (core/outils_memoire_eleve.py). Ces trois outils
    # n'avaient aucune entrée ici : le chat affichait leur nom technique et
    # l'icône générique. Même icône principale pour les trois, la petite
    # icône de verbe (VERBES_ACTIONS) distingue la lecture.
    "memoire_sommaire": {"label": "Aperçu de ta mémoire", "icone": "Brain", "onglet": None},
    "memoire_lire": {"label": "Lecture de ta mémoire", "icone": "Brain", "onglet": None},
    "memoire_ecrire": {"label": "Enregistrement dans ta mémoire", "icone": "Brain", "onglet": None},
    "memoire_completer": {"label": "Enregistrement dans ta mémoire", "icone": "Brain", "onglet": None},
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
    # Depuis le 18/08 (voir avertissement en tête de section), c'etaient
    # les 6 seules entrees affichees ici. 7e entree ajoutee le 26/09
    # (demande explicite Bourama) : ui_photo, fusion du bouton "Prendre
    # une photo" jusque-la code en dur cote frontend dans ce meme systeme
    # (lib/outils.ts + executerActionOutil, classinus-frontend). Necessite
    # aussi une ligne dans registre_outils_plateforme (categorie 4,
    # disponible=true) et dans agents_actions_locales (agent clovis) pour
    # etre reellement visible, comme les 6 autres.
    "ui_localisation": {"label": "Joindre ma position", "icone": "MapPin", "onglet": "utilitaires"},
    "ui_formule": {"label": "Formule ou réaction chimique", "icone": "Sigma", "onglet": "utilitaires"},
    "ui_editeur_maths": {"label": "Éditeur maths live", "icone": "Calculator", "onglet": "utilitaires"},
    "ui_recherche": {"label": "Forcer une recherche web", "icone": "Search", "onglet": "utilitaires"},
    "ui_dessin": {"label": "Dessin et croquis", "icone": "PenLine", "onglet": "utilitaires"},
    "ui_mode_vocal": {"label": "Mode vocal", "icone": "AudioLines", "onglet": "utilitaires"},
    "ui_photo": {"label": "Prendre une photo", "icone": "Camera", "onglet": "utilitaires"},

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
    "gerer_dossier_bibliotheque": {"label": "Mes dossiers", "icone": "FolderTree", "onglet": None},

    # --- Historique (porté le 17/08 depuis serveur_mcp_espace.py) ---
    # Même onglet=None : section "Historique" à part entière de "Mon
    # espace", pas un bouton du menu Outils du chat.
    "lister_conversations_historique": {"label": "Conversations passées", "icone": "History", "onglet": None},
    "lire_conversation_historique": {"label": "Lire une conversation", "icone": "MessageSquareText", "onglet": None},

    # --- Programme adaptatif (interne) ---
    # Bloc entier retiré le 29/08/2026 (demande Bourama) : ces outils
    # n'existent plus (fonctionnalité "Programme" désactivée et isolée,
    # voir _desactive_programme/LISEZ_MOI_NE_JAMAIS_REUTILISER.md). NE
    # JAMAIS réintroduire ces entrées sans reconstruire la fonctionnalité
    # à neuf.
    "consulter_matiere_active": {"label": "Matière active", "icone": "BookOpen", "onglet": None},
    "annuler_derniere_modification": {"label": "Annuler la modification", "icone": "Undo2", "onglet": None},
    "gerer_configuration": {"label": "Ma configuration", "icone": "Settings2", "onglet": None},
    "gerer_skill": {"label": "Mes skills", "icone": "ScrollText", "onglet": None},
    # Routage en deux niveaux (22/08/2026, demande Bourama) : jamais un
    # outil que le grand LLM appelle lui-même (pas de tool MCP réel), c'est
    # le petit routeur "à la skill" (core/main.py) qui déclenche ça en
    # coulisse -- mais on veut quand même que ça s'affiche comme un
    # résultat d'outil normal dans le fil de conversation (voir
    # OutilResultatBulle.tsx), d'où cette entrée dans ce registre bien qu'il
    # n'existe aucun outil MCP de ce nom.
    "consulter_skills_chapitres_matiere": {"label": "Skills des chapitres", "icone": "ScrollText", "onglet": None},

    # --- Confiance pédagogique : avancement des notions (Partie 3,
    # 06/09/2026) --- onglet=None, même logique que les blocs
    # "Programme adaptatif"/"Bibliothèque" plus haut : outils que le
    # modèle appelle lui-même en autonomie, jamais des boutons cliqués.
    "gerer_avancement_notions": {"label": "Programme", "icone": "ListChecks", "onglet": None},
    "consulter_avancement_notion": {"label": "Consultation de l'avancement", "icone": "BookOpen", "onglet": None},

    # --- Vérification "mode cours" (12/09/2026) --- outil unique qui
    # absorbe consulter_avancement_notion et consulter_signalements_pertinents
    # (les deux entrées ci-dessus/ci-dessous sont gardées pour l'affichage
    # correct des anciens messages déjà en base, jamais réutilisées pour
    # de nouveaux appels).
    "verifier_consignes_code_actif": {"label": "Vérification du code actif", "icone": "ShieldCheck", "onglet": None},
    # Changement de mode par Clovis lui-même (25/09/2026, demande Bourama)
    # -- onglet=None, même logique que verifier_consignes_code_actif :
    # jamais un bouton cliquable, l'élève ne choisit pas cet outil.
    "changer_mode_conversation": {"label": "Changement de mode", "icone": "SlidersHorizontal", "onglet": None},
    # Filet de secours (23/09/2026, demande Bourama) au-delà de la fenêtre
    # des 2 messages auto-injectés après un QCM -- voir
    # core/outils_reponses_qcm.py. onglet: None, même logique que
    # verifier_consignes_code_actif : jamais un bouton cliquable.
    "lire_reponses_qcm": {"label": "Lecture des réponses QCM", "icone": "ListChecks", "onglet": None},
    # Gestion de la taille de l'historique (28/09/2026, demande Bourama) :
    # outils que le modele appelle lui-meme en autonomie, jamais des boutons
    # cliquables (onglet None, meme logique que lire_reponses_qcm). Icones
    # deja utilisees ailleurs dans ce registre.
    "rappeler_resultat_outil": {"label": "Rappel d'un résultat précédent", "icone": "ScrollText", "onglet": None},
    "rappeler_echange_conversation": {"label": "Rappel d'un échange précédent", "icone": "BookOpen", "onglet": None},
    "marquer_sujet_clos": {"label": "Archivage d'un sujet terminé", "icone": "ListChecks", "onglet": None},

    # --- Actions sur le téléphone de l'étudiant (26/08/2026) ---
    # onglet=None, même logique que les blocs "Programme adaptatif"/
    # "Bibliothèque" plus haut : outils que le modèle appelle lui-même en
    # autonomie pendant la conversation, jamais des boutons cliqués.
    "gerer_dossier_telephone": {"label": "Mon téléphone", "icone": "FolderPen", "onglet": None},
    "explorer_dossier": {"label": "Dossier en direct", "icone": "FolderOpen", "onglet": None},

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
    # 20/09/2026 (demande Bourama) : minuteurs du chat, appeles par le modele, jamais cliquables a la main (onglet None).
    "gerer_minuteur": {"label": "Minuteur", "icone": "Timer", "onglet": None},
    # Chantier F : filet de securite generique, meme rappel de cache 24h.
    "executer_clic_generique": {"label": "Clic dans l'application", "icone": "MousePointer2", "onglet": None},
    # Chantier G : mode guidage, meme rappel de cache 24h.
    "montrer_element_application": {"label": "Pointer un élément", "icone": "Crosshair", "onglet": None},
    # Ecriture dans les champs (20/09/2026, demande Bourama), meme rappel de cache 24h.
    "ecrire_dans_champ": {"label": "Écriture dans un champ", "icone": "PenLine", "onglet": None},
    # Lot U (28/09/2026) : lecture du texte visible de la page, meme rappel de cache 24h.
    "lire_page": {"label": "Lecture de la page", "icone": "Eye", "onglet": None},
    # Lot S (canal en direct sur PC, 27/09/2026) : actions sur le systeme du PC via l'appli Electron,
    # appelees par le modele, jamais cliquables a la main (onglet None), meme rappel de cache 24h.
    "cliquer_ecran": {"label": "Clic à l'écran", "icone": "MousePointer2", "onglet": None},
    "pointer_ecran": {"label": "Pointage à l'écran", "icone": "Crosshair", "onglet": None},
    "marquer_ecran": {"label": "Marque à l'écran", "icone": "Highlighter", "onglet": None},
    "taper_clavier": {"label": "Saisie au clavier", "icone": "Keyboard", "onglet": None},
    "appuyer_touches": {"label": "Raccourci clavier", "icone": "Command", "onglet": None},
    "ouvrir_application": {"label": "Ouverture d'une application", "icone": "AppWindow", "onglet": None},
    "lire_ecran": {"label": "Lecture de l'écran", "icone": "Eye", "onglet": None},
    # Vision ecran Android lot 3 (11/10/2026) : lecture et marque sur le telephone, meme rappel de cache 24h.
    "lire_ecran_telephone": {"label": "Lecture de l'écran du téléphone", "icone": "Eye", "onglet": None},
    "marquer_ecran_telephone": {"label": "Marque sur l'écran du téléphone", "icone": "Highlighter", "onglet": None},
    # Editeur de code (28/09/2026, demande Bourama), meme rappel de cache 24h.
    "lire_editeur": {"label": "Lecture de l'éditeur de code", "icone": "FileCode", "onglet": None},
    "montrer_dans_editeur": {"label": "Montrer dans l'éditeur", "icone": "Crosshair", "onglet": None},
    "ecrire_dans_editeur": {"label": "Écrire dans l'éditeur", "icone": "PenLine", "onglet": None},
    # Chantier P (canal en direct, 19/09/2026) : commentaire libre pendant
    # une action, meme rappel de cache 24h.
    "dire_a_l_etudiant": {"label": "Message en direct à l'utilisateur", "icone": "MessageCircle", "onglet": None},
    # Demo (20/09/2026) : ouverture du canal en direct depuis le chat
    # normal, meme rappel de cache 24h.
    "ouvrir_canal_en_direct": {"label": "Ouverture du canal en direct", "icone": "Radio", "onglet": None},
    # 02/10/2026 (demande Bourama) : Clovis active et desactive le canal depuis le chat.
    "activer_canal_en_direct": {"label": "Activation du canal en direct", "icone": "Radio", "onglet": None},
    "desactiver_canal_en_direct": {"label": "Couper le canal en direct", "icone": "Radio", "onglet": None},

    # --- Outils sans entrée jusqu'au 24/09/2026 (audit de l'affichage des
    # outils, demande Bourama : repérer les icônes génériques) --- ces 10
    # outils existent bel et bien côté chat (voir core/outils_*.py) mais
    # n'avaient AUCUNE entrée ici, donc affichaient l'icône générique et
    # leur nom technique brut. onglet=None comme les autres outils que le
    # modèle appelle en autonomie. Chaque icône est nouvelle dans ce
    # registre (jamais une icône déjà utilisée ailleurs ici).
    "gerer_entree_catalogue_public": {"label": "Catalogue public", "icone": "LibraryBig", "onglet": None},
    "gerer_dossier_catalogue_public": {"label": "Dossiers publics", "icone": "FolderSymlink", "onglet": None},
    "gerer_comportement_public": {"label": "Skills publics", "icone": "Puzzle", "onglet": None},
    "basculer_etoile_catalogue_public": {"label": "Étoile du catalogue public", "icone": "Bookmark", "onglet": None},
    # 21/10/2026 (demande Bourama) : outils sans libellé repérés à l'audit. Le
    # logo de la plateforme joue le rôle du nom, donc aucun nom de plateforme
    # dans le texte. Higgsfield : les deux outils internes de l'API vidéo ; les
    # outils du serveur MCP personnel passent par libelle_outil_plateforme.
    # "appli": le chat affiche alors le vrai logo Higgsfield (nom d'appli
    # higgsfield_mcp, voir APPLIS_DISPONIBLES côté frontend) et la petite icône
    # d'action tirée du verbe du nom (lancer, consulter). L'icône lucide reste
    # le repli si le frontend ne connaît pas cette appli.
    "lancer_video_higgsfield": {"label": "Génération d'une vidéo", "icone": "Clapperboard", "onglet": None, "appli": "higgsfield_mcp"},
    "consulter_video_higgsfield": {"label": "Suivi d'une vidéo", "icone": "Film", "onglet": None, "appli": "higgsfield_mcp"},
    "generer_image_higgsfield": {"label": "Génération d'une image", "icone": "ImagePlus", "onglet": None, "appli": "higgsfield_mcp"},
    "consulter_image_higgsfield": {"label": "Suivi d'une image", "icone": "Image", "onglet": None, "appli": "higgsfield_mcp"},
    "estimer_cout_higgsfield": {"label": "Estimation du coût", "icone": "Coins", "onglet": None, "appli": "higgsfield_mcp"},
    "annuler_generation_higgsfield": {"label": "Annulation d'une génération", "icone": "Ban", "onglet": None, "appli": "higgsfield_mcp"},
    "gerer_programme_catalogue_public": {"label": "Programmes publics", "icone": "GraduationCap", "onglet": None},
    "ajouter_commentaire_catalogue_public": {"label": "Ajout d'un commentaire public", "icone": "MessageSquarePlus", "onglet": None},
    "supprimer_commentaire_catalogue_public": {"label": "Suppression d'un commentaire public", "icone": "MessageSquareX", "onglet": None},
    "gerer_session_concentration": {"label": "Concentration", "icone": "Focus", "onglet": None},
    "lire_temps_ecran": {"label": "Lecture du temps d'écran", "icone": "Smartphone", "onglet": None},
    "planifier_rappel": {"label": "Planification d'un rappel", "icone": "BellRing", "onglet": None},
    "consulter_signalement": {"label": "Consultation d'un signalement", "icone": "Flag", "onglet": None},
    "enregistrer_note_signalement": {"label": "Note sur un signalement", "icone": "NotebookPen", "onglet": None},
    "rattacher_signalement_notion": {"label": "Rattacher un signalement", "icone": "Link", "onglet": None},


    # Atelier vidéo contextuel : les outils sont pilotés par Clovis, jamais
    # sélectionnés manuellement dans le menu d'outils.
    "video_lister_outils": {"label": "Recherche des capacités vidéo", "icone": "Clapperboard", "onglet": None},
    "video_executer_outil": {"label": "Montage vidéo", "icone": "Film", "onglet": None},
    # 26/10/2026 : copie un fichier joint (vidéo, audio, image) dans l'espace de montage.
    "video_importer_fichier_conversation": {"label": "Import d'un fichier joint pour le montage", "icone": "Paperclip", "onglet": None},

    # 28/10/2026 : outils du serveur diagnostic Class-Tech (onglet None :
    # pas de bouton menu, affichés quand ils s'exécutent dans le fil).
    "ping_serveur": {"label": "Ping serveur", "icone": "Satellite", "onglet": None},
    "verifier_chaine": {"label": "Vérification", "icone": "Stethoscope", "onglet": None},
    "resumer_symptome": {"label": "Résumé du symptôme", "icone": "ClipboardList", "onglet": None},
    # 28/10/2026 : palier 80 % (pont ADB, batterie, stockage, applis,
    # système, réseau, capteurs).
    "detecter_telephone": {"label": "Détecter le phone", "icone": "Smartphone", "onglet": None},
    "lire_batterie": {"label": "Batterie", "icone": "BatteryMedium", "onglet": None},
    "lire_conso_batterie": {"label": "Conso batterie", "icone": "BatteryCharging", "onglet": None},
    "lire_stockage": {"label": "Stockage", "icone": "HardDrive", "onglet": None},
    "lister_gros_fichiers": {"label": "Gros fichiers", "icone": "Files", "onglet": None},
    "vider_cache_applis": {"label": "Vider les caches", "icone": "Trash2", "onglet": None},
    "lister_applis": {"label": "Applis installées", "icone": "LayoutGrid", "onglet": None},
    "lire_crashs_recents": {"label": "Plantages d'applis", "icone": "Bug", "onglet": None},
    "lister_applis_inutilisees": {"label": "Applis inutilisées", "icone": "Archive", "onglet": None},
    "lire_version_systeme": {"label": "Version Android", "icone": "Info", "onglet": None},
    "lire_erreurs_recentes": {"label": "Erreurs récentes", "icone": "ScrollText", "onglet": None},
    "lire_etat_reseau": {"label": "Réseau", "icone": "Wifi", "onglet": None},
    "lire_infos_wifi": {"label": "Détails wifi", "icone": "Signal", "onglet": None},
    "tester_capteurs": {"label": "Test capteurs", "icone": "Radar", "onglet": None},
    # 28/10/2026 : palier 100 % (tests matériel, perf, sécurité).
    "tester_ecran_tactile": {"label": "Test écran tactile", "icone": "Smartphone", "onglet": None},
    "tester_gps": {"label": "Test GPS", "icone": "MapPin", "onglet": None},
    "tester_micro": {"label": "Test micro", "icone": "Mic", "onglet": None},
    "tester_haut_parleur": {"label": "Test haut-parleur", "icone": "Volume2", "onglet": None},
    "tester_vibreur": {"label": "Test vibreur", "icone": "Vibrate", "onglet": None},
    "tester_camera": {"label": "Test caméra", "icone": "Camera", "onglet": None},
    "tester_boutons": {"label": "Test boutons", "icone": "Power", "onglet": None},
    "analyser_memoire_vive": {"label": "Mémoire vive", "icone": "MemoryStick", "onglet": None},
    "analyser_cpu": {"label": "Processeur (CPU)", "icone": "Cpu", "onglet": None},
    "analyser_applications_gourmandes": {"label": "Applis gourmandes", "icone": "Gauge", "onglet": None},
    "lister_permissions_risquees": {"label": "Permissions à risque", "icone": "KeyRound", "onglet": None},
    "revoquer_permission": {"label": "Retirer une permission", "icone": "ShieldOff", "onglet": None},
    "verifier_securite": {"label": "Sécurité du téléphone", "icone": "ShieldCheck", "onglet": None},
    "verifier_mises_a_jour": {"label": "Mises à jour", "icone": "RefreshCw", "onglet": None},
    # 28/10/2026 : palier root DESACTIVE (19 outils, voir sensibles).
    "root_verifier_acces": {"label": "Vérifier le root", "icone": "KeyRound", "onglet": None},
    "root_lire_infos_root": {"label": "Infos root", "icone": "Info", "onglet": None},
    "root_lister_fichiers_systeme": {"label": "Dossiers système", "icone": "FolderTree", "onglet": None},
    "root_lire_fichier_systeme": {"label": "Fichier système", "icone": "FileText", "onglet": None},
    "root_lire_erreurs_noyau": {"label": "Erreurs noyau", "icone": "Bug", "onglet": None},
    "root_lire_paniques_passees": {"label": "Paniques passées", "icone": "History", "onglet": None},
    "root_lire_partitions": {"label": "Partitions", "icone": "HardDrive", "onglet": None},
    "root_verifier_integrite": {"label": "Intégrité système", "icone": "ShieldCheck", "onglet": None},
    "root_lire_batterie_brute": {"label": "Batterie brute", "icone": "BatteryCharging", "onglet": None},
    "root_lire_temperatures": {"label": "Températures", "icone": "Thermometer", "onglet": None},
    "root_reinitialiser_stats_batterie": {"label": "RAZ stats batterie", "icone": "RotateCcw", "onglet": None},
    "root_lire_firmware": {"label": "Firmware", "icone": "Cpu", "onglet": None},
    "root_valider_slot_demarre": {"label": "Valider slot A/B", "icone": "Check", "onglet": None},
    "root_lister_processus": {"label": "Processus", "icone": "Activity", "onglet": None},
    "root_lire_wakelocks": {"label": "Wakelocks", "icone": "Zap", "onglet": None},
    "root_nettoyer_fichiers_crash": {"label": "Nettoyer crashs", "icone": "Trash2", "onglet": None},
    "root_vider_cache_dalvik": {"label": "Vider cache Dalvik", "icone": "Trash", "onglet": None},
    "root_forcer_trim": {"label": "Forcer TRIM", "icone": "Sparkles", "onglet": None},
    "root_redemarrer": {"label": "Redémarrer", "icone": "Power", "onglet": None},

}

# --- Verbes des actions (24/09/2026, demande Bourama : regroupement des
# outils qui s'enchaînent et petite icône d'action) ---
# Un même verbe = une même petite icône ("sous-icône") et un même
# libellé, PARTOUT : "supprimer" a la même corbeille pour la bibliothèque,
# les dossiers, les skills, le catalogue public, et "delete" pour un outil
# d'une appli connectée. Un futur outil qui utilise l'un de ces verbes est
# donc couvert sans rien toucher d'autre. Ajouter un verbe = une ligne ici.
#
# Clé = un mot d'une action ("chercher_par_contenu" -> "chercher", coupé
# sur "_") OU d'un nom d'outil connecté ("notion-search" -> "search", coupé
# sur "-" et "_"). Le premier mot reconnu l'emporte (voir
# verbe_de_action / core/profils_agents.py:_nom_lisible et le frontend,
# lib/outils.ts:sousIconePour).
# Valeur = (libellé français ou None, nom d'export lucide-react).
# libellé None : verbes anglais des outils d'applis connectées, dont le
# libellé complet existe déjà dans REGISTRE_AFFICHAGE_OUTILS (jamais recomposé).
VERBES_ACTIONS = {
    # Actions des outils Classinus (français)
    "chercher": ("Recherche", "Search"),
    "trouver": ("Recherche", "Search"),
    "lister": ("Liste", "List"),
    "consulter": ("Consultation", "Eye"),
    "lire": ("Lecture", "Eye"),
    # 28/10/2026 : verbes des outils diagnostic Class-Tech (80 et 100).
    "detecter": ("Détection", "Search"),
    "tester": ("Test", "FlaskConical"),
    "vider": ("Nettoyage", "Trash2"),
    "analyser": ("Analyse", "Activity"),
    "revoquer": ("Retrait", "ShieldOff"),
    "verifier": ("Vérification", "Check"),
    "root": ("Root", "ShieldAlert"),
    "ouvrir": ("Ouverture", "Eye"),
    "explorer": ("Exploration", "Eye"),
    "creer": ("Création", "Plus"),
    "ajouter": ("Ajout", "Plus"),
    "lancer": ("Lancement", "Play"),
    "demarrer": ("Démarrage", "Play"),
    "activer": ("Activation", "Power"),
    "executer": ("Exécution", "Zap"),
    "arreter": ("Arrêt", "Square"),
    "publier": ("Publication", "Upload"),
    "modifier": ("Modification", "Pencil"),
    "renommer": ("Renommage", "Pencil"),
    "mettre": ("Mise à jour", "Pencil"),
    "definir": ("Réglage", "Pencil"),
    "nommer": ("Nommage", "Pencil"),
    "supprimer": ("Suppression", "Trash2"),
    "effacer": ("Effacement", "Trash2"),
    "retirer": ("Retrait", "Minus"),
    "declasser": ("Déclassement", "Minus"),
    "ranger": ("Rangement", "FolderInput"),
    "classer": ("Classement", "FolderInput"),
    "deplacer": ("Déplacement", "Move"),
    "fusionner": ("Fusion", "Merge"),
    "copier": ("Copie", "Copy"),
    "donner": ("Envoi", "Download"),
    # Noms d'outils des applis connectées (anglais, libellé jamais recomposé)
    "search": (None, "Search"),
    "query": (None, "Search"),
    "fetch": (None, "Eye"),
    "get": (None, "Eye"),
    "read": (None, "Eye"),
    "show": (None, "Eye"),
    "list": (None, "List"),
    "create": (None, "Plus"),
    "update": (None, "Pencil"),
    "delete": (None, "Trash2"),
    "move": (None, "Move"),
    "duplicate": (None, "Copy"),
    "copy": (None, "Copy"),
    "download": (None, "Download"),
    "upload": (None, "Upload"),
    "send": (None, "Send"),
    "spawn": (None, "Play"),
    "stop": (None, "Square"),
    "convert": (None, "ArrowRightLeft"),
    "check": (None, "Check"),
}


def verbe_de_action(texte):
    """
    Premier mot reconnu (voir VERBES_ACTIONS) dans une action ou un nom
    d'outil, ou None. Coupe sur "_" et "-" : "dossier_creer_fichier" ->
    "creer", "notion-ai-search" -> "search".
    """
    if not texte:
        return None
    for mot in texte.replace("-", "_").split("_"):
        if mot in VERBES_ACTIONS:
            return mot
    return None


def libelle_outil_plateforme(nom_outil):
    """
    Libellé lisible d'un outil d'un serveur MCP personnel (Higgsfield, Vercel,
    Railway, Supabase) absent du registre (21/10/2026, demande Bourama). Leur
    catalogue compte des centaines d'outils qui changent souvent : le texte est
    donc composé à partir du nom réel, sans le préfixe de la plateforme puisque
    son logo joue ce rôle. Exemple : "vercel_list_projects" -> "List projects".
    Renvoie None si le nom n'a pas le préfixe d'une de ces plateformes ou s'il
    ne reste rien après le préfixe : l'appelant garde alors son comportement
    habituel.
    """
    if not isinstance(nom_outil, str):
        return None
    for prefixe in PREFIXES_SERVEURS_PERSONNELS:
        if nom_outil.startswith(prefixe):
            if prefixe == "custommcp_":
                # Serveurs ajoutés par l'élève : le nom contient un code interne, la carte de
                # confirmation affiche « Action sur <nom du serveur> » à la place.
                return None
            reste = nom_outil[len(prefixe):].replace("-", "_")
            mots = [mot for mot in reste.split("_") if mot]
            if not mots:
                return None
            texte = " ".join(mots)
            return texte[0].upper() + texte[1:]
    return None

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
    # Exécution de code (24/10/2026, demande Bourama) : catégorie à part, retiré
    # de generation_documents où il ne créait aucun document. Il lance du code
    # et des commandes et gère des fichiers dans un espace de travail.
    # generer_code (qui écrit du code sans l'exécuter) reste dans
    # generation_documents.
    "execution_code": ["gerer_execution_code"],
    # Montage vidéo (24/10/2026, demande Bourama) : disponible sans vidéo jointe, via
    # demander_outils comme les autres catégories. Distinct de recherche_web
    # (rechercher_video, lire_video = vidéos du web) et de higgsfield (génération IA).
    "montage_video": ["video_lister_outils", "video_executer_outil", "video_importer_fichier_conversation"],
    # rechercher_image range ici (avec Tavily), pas dans generation_documents :
    # onglet="rechercher" dans REGISTRE_AFFICHAGE_OUTILS ci-dessus, c'est une
    # recherche d'image EXISTANTE sur le web, pas une creation (voir
    # generer_image, qui lui reste dans generation_documents).
    "recherche_web": [
        "tavily_search", "tavily_extract", "tavily_crawl", "tavily_map",
        "tavily_research", "rechercher_image", "rechercher_video", "lire_video",
    ],
    "bibliotheque": [
        "gerer_document_bibliotheque", "gerer_dossier_bibliotheque",
        "gerer_fichier_conversation",
    ],
    # Vidéo ou audio joint par l'étudiant (26/10/2026) : catégorie à part, pour ne pas
    # tirer les trois gros outils de la bibliothèque quand on veut seulement lire un média.
    "media_joint": ["lire_media_conversation"],
    # Document joint par l'étudiant (27/10/2026) : catégorie à part, même raison que media_joint.
    "document_joint": ["lire_document_conversation"],
    "catalogue_public": [
        "gerer_entree_catalogue_public", "gerer_dossier_catalogue_public",
        "gerer_programme_catalogue_public",  # 22/09/2026
        "ajouter_commentaire_catalogue_public", "supprimer_commentaire_catalogue_public",  # 22/09/2026
    ],
    # Livres et PDF trouvés HORS de Classinus (Internet Archive), 09/10/2026,
    # demande Bourama. Catégorie à part : rangés dans recherche_web ou
    # catalogue_public, ces outils seraient confondus avec la recherche web ou
    # avec le catalogue interne (le modèle ouvrirait le catalogue public pour
    # un livre qui n'y est pas).
    "documents_externes": ["rechercher_document_externe", "lire_document_internet_archive", "lire_document_externe"],
    "base_connaissance": ["gerer_base_connaissance"],
    "pedagogie": [
        "gerer_avancement_notions", "consulter_avancement_notion",
        "verifier_consignes_code_actif", "consulter_signalement",
        "consulter_signalements_pertinents", "enregistrer_note_signalement",
        "rattacher_signalement_notion", "lire_reponses_qcm",
        "changer_mode_conversation",  # 25/09/2026
    ],
    # 25/10/2026 : configuration et skills séparés (gerer_comportement renommé gerer_configuration).
    "configuration": ["gerer_configuration"],
    "skills": ["gerer_skill", "gerer_comportement_public"],
    "memoire": [
        "memoire_sommaire", "memoire_lire", "memoire_ecrire", "memoire_completer",
    ],
    "telephone_etudiant": [
        "gerer_dossier_telephone", "explorer_dossier", "gerer_action_mobile",
        "lire_temps_ecran", "gerer_session_concentration",
    ],
    "historique": [
        "lister_conversations_historique", "lire_conversation_historique",
        "rappeler_resultat_outil", "rappeler_echange_conversation", "marquer_sujet_clos",  # 28/09/2026
    ],
    # Minuteurs du chat (20/09/2026, demande Bourama, chat seulement).
    "minuteur": ["gerer_minuteur"],
    # lister_actions_disponibles retire le 19/09/2026 (chantier "agent
    # applicatif continu", decision Bourama) : la liste des actions est
    # desormais injectee automatiquement dans le prompt systeme, plus
    # jamais demandee par un outil.
    "agent_applicatif": [
        "executer_action_application",
        "executer_clic_generique", "montrer_element_application", "ecrire_dans_champ",
        "lire_page",
        "pointer_ecran", "marquer_ecran", "cliquer_ecran", "taper_clavier", "appuyer_touches", "ouvrir_application", "lire_ecran",
        "lire_ecran_telephone", "marquer_ecran_telephone",
        "lire_editeur", "montrer_dans_editeur", "ecrire_dans_editeur",
        "desactiver_canal_en_direct",
    ],
    "github": ["gerer_depot_github"],
    # Higgsfield, version de Classinus (26/10/2026, demande de Bourama) : outils de notre propre
    # API (clé partagée), disponibles pour tout le monde sans connexion. Catégorie séparée de
    # "higgsfield" (plus bas, par préfixe) qui est le compte Higgsfield de l'utilisateur :
    # avant, les deux étaient mélangés et l'IA ne savait pas les distinguer.
    "higgsfield_classinus": [
        "lancer_video_higgsfield", "consulter_video_higgsfield",
        "generer_image_higgsfield", "consulter_image_higgsfield",
        "estimer_cout_higgsfield", "annuler_generation_higgsfield",
    ],
    "google_drive": [
        "search_files", "read_file_content", "download_file_content",
        "list_recent_files", "get_file_metadata", "create_file", "copy_file",
    ],
    # 28/10/2026 : outils du serveur diagnostic Class-Tech.
    # Elargie le 28/10/2026 : base + palier 80 % + palier 100 %. Un nom
    # pas encore exposé par le serveur reste sans effet (le filtre
    # outils_de_la_categorie croise avec les outils réels).
    "diagnostic_classtech": [
        "ping_serveur", "verifier_chaine", "resumer_symptome",
        "detecter_telephone", "lire_batterie", "lire_conso_batterie",
        "lire_stockage", "lister_gros_fichiers", "vider_cache_applis",
        "lister_applis", "lire_crashs_recents", "lister_applis_inutilisees",
        "lire_version_systeme", "lire_erreurs_recentes", "lire_etat_reseau",
        "lire_infos_wifi", "tester_capteurs",
        "tester_ecran_tactile", "tester_gps", "tester_micro",
        "tester_haut_parleur", "tester_vibreur", "tester_camera",
        "tester_boutons", "analyser_memoire_vive", "analyser_cpu",
        "analyser_applications_gourmandes", "lister_permissions_risquees",
        "revoquer_permission", "verifier_securite", "verifier_mises_a_jour",
    ],
}

# Categories reconnues par prefixe de nom d'outil plutot que par liste
# figee (voir commentaire au-dessus de CATEGORIES_OUTILS).
CATEGORIES_OUTILS_PAR_PREFIXE = {
    "google_gmail": "gmail_",
    "google_docs": "gdocs_",
    "google_sheets": "gsheets_",
    "google_slides": "gslides_",
    "google_calendar": "gcal_",
    "google_chat": "gchat_",
    "google_classroom": "gclass_",
    "google_people": "gpeople_",
    "microsoft_mcp": "ms365_",
    "render_mcp": "render_",
    "cloudflare_mcp": "cloudflare_",
    "netlify_mcp": "netlify_",
    "notion": "notion-",
    # Serveurs MCP personnels (20/10/2026) : le prefixe est AJOUTE par
    # mcp_tools.py au nom reel de chaque outil (voir "prefixe_outils" dans
    # SERVEURS_MCP), contrairement a "notion-" qui fait deja partie du nom.
    "vercel": "vercel_",
    "railway": "railway_",
    "supabase": "supabase_",
    "higgsfield": "higgsfield_",
    # Serveurs MCP ajoutés par l'utilisateur lui-même (Render, un CRM...) : leur nom d'outil
    # commence par custommcp_ puis un code interne, donc aucune des catégories ci-dessus ne les
    # contient. Sans celle-ci, l'IA cherchait « Render » dans la catégorie render_mcp, la
    # connexion officielle, la trouvait vide et répondait qu'elle ne voyait rien.
    "serveurs_personnalises": "custommcp_",
}

NOMS_CATEGORIES_OUTILS = list(dict.fromkeys([*CATEGORIES_OUTILS.keys(), *CATEGORIES_OUTILS_PAR_PREFIXE.keys()]))

# ---------------------------------------------------------------------------
# Services que l'utilisateur peut connecter lui-même (26/10/2026, demande de Bourama).
# Données pures, lues par core/etat_connexions.py : l'IA sait ainsi lesquels existent, lesquels
# sont connectés, et peut proposer ceux qui ne le sont pas encore.
#
# "service" : nom du service côté connexions (identique à APPLIS_DISPONIBLES, frontend).
# "categorie" : catégorie de demander_outils qui contient les outils de ce service.
# "mots_cles" : mots français qui permettent de retrouver le service depuis un besoin exprimé
#   en langage libre (les noms d'outils sont en anglais et ne recoupent jamais le besoin).
# "proposable" : False pour un service masqué dans l'écran Connexions du site (Google Workspace
#   en préversion, Google Drive, Microsoft, Netlify, Cloudflare). Le proposer ferait afficher une
#   carte vide : à passer à True seulement quand le site l'affiche, sur décision de Bourama.
#   Source de vérité côté site : tests/verifier-connexions.mjs (visibleDansEspaceConnexions).
#   Un service non proposable n'apparaît ni dans l'état des connexions, ni dans les catégories
#   offertes à l'IA par demander_outils (voir CATEGORIES_SERVICES_MASQUES plus bas).
# ---------------------------------------------------------------------------
SERVICES_CONNECTABLES = [
    {"service": "github", "label": "GitHub", "categorie": "github", "proposable": True,
     "mots_cles": "github depot dépôt code repository repo commit branche pull request fichier source"},
    {"service": "notion", "label": "Notion", "categorie": "notion", "proposable": True,
     "mots_cles": "notion page base de données notes wiki espace de travail document"},
    {"service": "microsoft_mcp", "label": "Microsoft Enterprise", "categorie": "microsoft_mcp", "proposable": False,
     "mots_cles": "microsoft entra graph entreprise annuaire utilisateurs locataire azure"},
    {"service": "netlify_mcp", "label": "Netlify", "categorie": "netlify_mcp", "proposable": False,
     "mots_cles": "netlify site déployer deploiement déploiement hébergement build site web"},
    {"service": "render_mcp", "label": "Render", "categorie": "render_mcp", "proposable": True,
     "mots_cles": "render service déploiement hébergement serveur journaux logs backend"},
    {"service": "cloudflare_mcp", "label": "Cloudflare", "categorie": "cloudflare_mcp", "proposable": False,
     "mots_cles": "cloudflare dns workers domaine cdn pages cache"},
    {"service": "higgsfield_mcp", "label": "Higgsfield", "categorie": "higgsfield", "proposable": True,
     "mots_cles": "higgsfield vidéo video image génération générer créer film clip animation"},
    {"service": "vercel_mcp", "label": "Vercel", "categorie": "vercel", "proposable": True,
     "mots_cles": "vercel site déployer deploiement déploiement projet hébergement frontend domaine build"},
    {"service": "railway_mcp", "label": "Railway", "categorie": "railway", "proposable": True,
     "mots_cles": "railway service déployer deploiement déploiement backend serveur logs journaux projet"},
    {"service": "supabase_mcp", "label": "Supabase", "categorie": "supabase", "proposable": True,
     "mots_cles": "supabase base de données sql table postgres migration données requête"},
    {"service": "google_drive", "label": "Google Drive", "categorie": "google_drive", "proposable": False,
     "mots_cles": "google drive fichiers documents stockage"},
    {"service": "google_gmail_mcp", "label": "Gmail", "categorie": "google_gmail", "proposable": False,
     "mots_cles": "gmail mail email courriel messagerie brouillon"},
    {"service": "google_docs_mcp", "label": "Google Docs", "categorie": "google_docs", "proposable": False,
     "mots_cles": "google docs document texte"},
    {"service": "google_sheets_mcp", "label": "Google Sheets", "categorie": "google_sheets", "proposable": False,
     "mots_cles": "google sheets tableur classeur cellules"},
    {"service": "google_slides_mcp", "label": "Google Slides", "categorie": "google_slides", "proposable": False,
     "mots_cles": "google slides présentation diapositives"},
    {"service": "google_calendar_mcp", "label": "Google Calendar", "categorie": "google_calendar", "proposable": False,
     "mots_cles": "google calendar agenda événement rendez-vous"},
    {"service": "google_chat_mcp", "label": "Google Chat", "categorie": "google_chat", "proposable": False,
     "mots_cles": "google chat messages espaces conversation"},
    {"service": "google_classroom_mcp", "label": "Google Classroom", "categorie": "google_classroom", "proposable": False,
     "mots_cles": "google classroom cours élèves devoirs"},
    {"service": "google_people_mcp", "label": "Google People", "categorie": "google_people", "proposable": False,
     "mots_cles": "google people contacts profils"},
]

# Catégories des services masqués dans l'écran Connexions (28/10/2026, demande de Bourama).
# Calculées depuis SERVICES_CONNECTABLES : passer "proposable" à True suffit à les rendre à l'IA,
# aucune autre liste à retoucher. NOMS_CATEGORIES_OUTILS reste la liste complète (elle sert à
# retrouver les outils d'une catégorie et aux tests) ; seule la liste montrée à l'IA est filtrée,
# sinon elle croit que ces services existent et ne les propose pas comme il faut.
CATEGORIES_SERVICES_MASQUES = frozenset(s["categorie"] for s in SERVICES_CONNECTABLES if not s["proposable"])
NOMS_CATEGORIES_PROPOSEES_A_L_IA = [n for n in NOMS_CATEGORIES_OUTILS if n not in CATEGORIES_SERVICES_MASQUES]


def _categories_services_pour_index(entrees):
    """Texte de l'index pour les catégories données (nom, texte), sans celles des services masqués."""
    return ", ".join(texte for nom, texte in entrees if nom not in CATEGORIES_SERVICES_MASQUES)


# Services qui existent en DEUX versions : celle de Classinus (notre API, clé partagée, sans
# connexion) et celle du compte de l'utilisateur. Décision de Bourama (26/10/2026) : quand les
# deux sont disponibles, celle de l'utilisateur passe en premier, sauf s'il demande l'autre.
VERSIONS_DOUBLES = [
    {
        "service": "higgsfield_mcp",
        "label": "Higgsfield",
        "categorie_utilisateur": "higgsfield",
        "categorie_classinus": "higgsfield_classinus",
    },
]

# Texte compact envoye dans la description de demander_outils (voir
# routage_outils._outil_demander_outils) : les categories evidentes sont
# nommees seules, les autres ont une parenthese pour lever l'ambiguite.


def _sources_documents_externes_pour_index():
    """
    Noms des sources de documents externes actives, lus dans leur registre
    (core/sources_documents_externes.py) au lieu d'etre ecrits ici : ajouter
    ou desactiver une source change l'index sans toucher ce fichier. Import
    fait ici et non en haut du fichier : ce module ne contient que des
    donnees, il ne doit pas tirer les modules de recherche tant qu'on n'en
    a pas besoin.
    """
    from core.sources_documents_externes import noms_sources

    return ", ".join(noms_sources())


INDEX_CATEGORIES_OUTILS = (
    "Catégories : "
    + _categories_services_pour_index([
        ("google_gmail", "google_gmail"),
        ("google_docs", "google_docs"),
        ("google_sheets", "google_sheets"),
        ("google_slides", "google_slides"),
        ("google_calendar", "google_calendar"),
        ("google_chat", "google_chat"),
        ("google_classroom", "google_classroom"),
        ("google_people", "google_people"),
        ("microsoft_mcp", "microsoft_mcp (Microsoft Graph Entra, lecture seule)"),
        ("render_mcp", "render_mcp"),
        ("cloudflare_mcp", "cloudflare_mcp"),
        ("netlify_mcp", "netlify_mcp"),
        ("notion", "notion"),
        ("google_drive", "google_drive"),
        ("github", "github"),
        ("vercel", "vercel (sites et déploiements)"),
    ])
    + ", "
    "railway (services et logs), supabase (base de données et SQL), "
    "higgsfield (compte Higgsfield de l'utilisateur : images, vidéos et tout le catalogue Higgsfield), "
    "higgsfield_classinus (génération de vidéo Higgsfield par l'API de Classinus, sans connexion), "
    "serveurs_personnalises (serveurs MCP ajoutés par l'utilisateur lui-même, quel que soit leur nom, "
    "par exemple Render ou un CRM ; le nom du serveur figure dans la description de chaque outil), "
    "generation_documents, "
    "execution_code (lancer du code et des commandes, gérer des fichiers dans un espace de travail), "
    "montage_video (créer ou modifier une vidéo : couper, assembler, sous-titrer, effets, animations ; "
    "pas pour chercher une vidéo sur le web), "
    "recherche_web (web, actualité, images et vidéos ; pas le premier réflexe "
    "pour trouver un livre ou un PDF), bibliotheque (documents/dossiers "
    "personnels), catalogue_public, documents_externes (TOUT livre, manuel, PDF, "
    "thèse ou article à trouver en ligne, hors de Classinus ; sources : "
    f"{_sources_documents_externes_pour_index()}), base_connaissance (Classinus lui même), "
    "pedagogie (avancement, signalements), configuration (règles, style, procédures, comportements), skills, memoire, "
    "telephone_etudiant (mobile, écran, concentration), historique "
    "(conversations passées), agent_applicatif (actions dans l'appli), minuteur (minuteurs dans le chat), diagnostic_classtech (diagnostic téléphone et PC)."
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



# ---------------------------------------------------------------------------
# Groupes et dependances d'outils pour demander_outils (21/10/2026, demande
# Bourama). Donnees pures, lues par core/completion_outils.py : ajouter une
# ligne ici suffit, aucun code a toucher.
#
# GROUPES_OUTILS : outils qui doivent toujours etre donnes ENSEMBLE. Si
# demander_outils en trouve un, il donne aussi tous les autres du groupe
# (dans les deux sens). Seuls les outils reellement presents dans le
# catalogue autorise du tour sont ajoutes : un nom absent est ignore sans
# erreur. Les outils de memoire ne sont pas ici : ils sont deja donnes a
# chaque tour (voir NOMS_OUTILS_MEMOIRE_TOUJOURS_DISPONIBLES, routage_outils.py).
# marquer_sujet_clos et rappeler_* ne sont volontairement dans aucun groupe :
# main.py les force lui-meme selon la taille de l'historique.
# ---------------------------------------------------------------------------
GROUPES_OUTILS = {
    "ecran_pc": [
        "lire_ecran", "pointer_ecran", "marquer_ecran", "cliquer_ecran",
        "taper_clavier", "appuyer_touches", "ouvrir_application",
    ],
    "ecran_telephone": ["lire_ecran_telephone", "marquer_ecran_telephone"],
    "editeur": ["lire_editeur", "montrer_dans_editeur", "ecrire_dans_editeur"],
    "actions_application": [
        "executer_action_application", "executer_clic_generique",
        "montrer_element_application", "ecrire_dans_champ",
    ],
    "documents_externes": [
        "rechercher_document_externe", "lire_document_externe", "lire_document_internet_archive",
    ],
    "video": ["rechercher_video", "lire_video"],
    "montage_video": ["video_lister_outils", "video_executer_outil", "video_importer_fichier_conversation"],
    "conversations_passees": ["lister_conversations_historique", "lire_conversation_historique"],
    "bibliotheque": [
        "gerer_document_bibliotheque", "gerer_dossier_bibliotheque", "gerer_fichier_conversation",
    ],
    "telephone": ["gerer_dossier_telephone", "explorer_dossier", "gerer_session_concentration"],
    "skills": ["gerer_skill", "gerer_comportement_public"],
    "site": ["generer_site_zip", "deployer_site"],
}

# DEPENDANCES_OUTILS : un outil qui exige qu'un autre soit appele AVANT lui
# (sens unique). {outil: [outils a donner avec lui]}. Pour les serveurs MCP
# dont le catalogue est trop grand pour une liste a la main, voir
# FOURNISSEURS_PARAMETRES_PAR_PREFIXE juste en dessous.
DEPENDANCES_OUTILS = {
    # Notion : la description de cet outil impose de lire d'abord la source
    # de donnees avec notion-fetch pour en obtenir le schema et l'adresse.
    "notion-query-multiple-data-sources": ["notion-fetch"],
}

# FOURNISSEURS_PARAMETRES_PAR_PREFIXE : pour les serveurs MCP personnels, un
# outil dont un parametre OBLIGATOIRE est un identifiant (projectId,
# serviceId...) a besoin de l'outil qui fournit cet identifiant. Regle par
# parametre et non par outil : elle couvre aussi les outils ajoutes plus tard
# par le serveur (schemas lus en direct, voir mcp_tools.py). Verifie le
# 21/10/2026 sur les schemas reels de Railway, Vercel et Supabase.
# {prefixe de nom: {parametre obligatoire: outil qui le fournit}}
FOURNISSEURS_PARAMETRES_PAR_PREFIXE = {
    "railway_": {
        "projectId": "railway_list-projects",
        "serviceId": "railway_list-services",
        "environmentId": "railway_list-services",
    },
    "vercel_": {
        "teamId": "vercel_list_teams",
        "projectId": "vercel_list_projects",
    },
    "supabase_": {
        "project_id": "supabase_list_projects",
    },
}

# ---------------------------------------------------------------------------
# Regle GENERALE des identifiants (27/10/2026, demande Bourama) : elle
# s'applique toute seule a TOUT serveur MCP, integre ou personnalise, y
# compris ceux qui seront ajoutes plus tard. Quand un outil exige un
# parametre obligatoire qui est un identifiant (workflowId, service_id,
# project-id, ou simplement id), le module core/completion_outils.py lit le
# schema reel de l'outil, cherche dans le MEME serveur l'outil de lecture qui
# fournit cet identifiant (list_workflows pour workflowId) et le donne avec.
# Les regles ecrites a la main plus haut (FOURNISSEURS_PARAMETRES_PAR_PREFIXE,
# DEPENDANCES_OUTILS) restent prioritaires : la regle generale ne fait que
# completer ce qu'elles ne couvrent pas. Donnees pures, rien a coder pour
# ajuster.
# ---------------------------------------------------------------------------

# Verbes (premier mot du vrai nom de l'outil, sans le prefixe de Classinus) des
# outils de lecture qui peuvent fournir un identifiant.
VERBES_FOURNISSEURS_IDENTIFIANTS = ("list", "search", "find", "query", "lookup", "browse")

# Mots interchangeables pour les identifiants : un serveur qui appelle
# « workspace » ce qu'un outil appelle « team » reste couvert. Utilise
# seulement quand aucun outil ne porte exactement le nom de l'identifiant.
SYNONYMES_IDENTIFIANTS = (
    {"team", "workspace", "organization", "org", "owner", "account"},
)

# Nombre maximal d'outils fournisseurs ajoutes pour un seul identifiant.
PLAFOND_FOURNISSEURS_PAR_IDENTIFIANT = 3
