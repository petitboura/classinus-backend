"""
Fournisseurs LLM premium (Claude, GPT, Gemini, Grok, DeepSeek) -- gardes-fous
"abonnement" par agent, distincts de la cascade Groq/Gemini-vision de
main.py qui reste le comportement PAR DEFAUT (voir GROQ_PRIMARY).

Contexte (voir page Notion "Pricing -- Agent Maths", 01/08/2026) : un agent
peut debloquer un `distributeur` (fournisseur) + un `palier` (qualite de
modele). La hierarchie des distributeurs est CUMULATIVE DESCENDANTE :

    claude > gpt > gemini > deepseek > grok

debloquer "claude" donne aussi acces a gpt/gemini/deepseek/grok. Le palier est
lui aussi cumulatif ascendant (pro >= avance >= essentiel) : un agent en
"pro" peut choisir un modele "essentiel" du meme distributeur si l'usager
veut une reponse plus rapide/moins chere.

IMPORTANT : ces identifiants de modele bougent vite (nouvelles versions
tous les 1-2 mois chez chaque fournisseur). Depuis le 15/10/2026 ils se
reglent dans Supabase (tables fournisseurs_llm, modeles_llm et
textes_modeles_llm), sans toucher au code ni redeployer : le backend relit
la configuration environ toutes les minutes. HIERARCHIE_MODELES ci-dessous
ne sert plus que de valeur de repli si Supabase ne repond pas.

LIMITE CONNUE (v1, 02/08/2026) : ces fournisseurs premium repondent en
TEXTE SEUL, sans les outils MCP (Wolfram, RAG, Notion, recherche web...).
Meme limitation que le chemin Gemini-vision existant dans main.py (voir
_construire_parts_gemini) -- brancher les outils sur les 3 nouveaux SDKs
(formats de tool-calling tous differents) est un chantier a part, pas
fait ici. A previlegier pour la v2 si Bourama le confirme.
"""

import os
import time
import logging

logging.basicConfig(level=logging.INFO)


def get_secret(key):
    return os.environ.get(key)


# Ordre = hierarchie cumulative descendante (voir docstring plus haut).
ORDRE_DISTRIBUTEURS = ["claude", "gpt", "gemini", "deepseek", "grok"]

# Ordre = hierarchie cumulative ascendante.
ORDRE_PALIERS = ["essentiel", "avance", "pro", "specialise"]
# "specialise" (16/10/2026) : niveau reserve aux modeles a usage precis qu'on
# affiche sans les proposer en discussion normale (aujourd'hui seulement
# grok-build-0.1, modele de code). Aucun agent n'a ce palier debloque, donc
# ces modeles ne sont jamais choisissables ; ils servent a l'affichage Bientot.

# palier "essentiel"/"avance"/"pro" (nom commercial, cote agents/pricing)
# -> mappe sur le palier de qualite "simple"/"parfait"/"pro" de la page
# Notion section 2 (nom technique, cote choix du modele). Meme hierarchie
# a 3 niveaux, deux vocabulaires differents selon le contexte (vente vs
# ingenierie) -- fusionnes ici pour eviter un 3e mapping inutile.
HIERARCHIE_MODELES = {
    "claude": {
        "essentiel": {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        "avance": {"id": "claude-sonnet-5", "label": "Claude Sonnet 5"},
        # "Claude Opus 5" (page Notion) n'existe pas encore cote Anthropic
        # au moment d'ecrire ceci -- Opus 4.8 est le dernier Opus reel,
        # a corriger ici des la sortie d'un vrai "Opus 5".
        "pro": {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"},
    },
    "gpt": {
        "essentiel": {"id": "gpt-5-nano", "label": "GPT-5 nano"},
        "avance": {"id": "gpt-5.4", "label": "GPT-5.4"},
        "pro": {"id": "gpt-5.5", "label": "GPT-5.5"},
    },
    "gemini": {
        "essentiel": {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite"},
        "avance": {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash"},
        "pro": {"id": "gemini-3.1-pro", "label": "Gemini 3.1 Pro"},
    },
    "grok": {
        # Grok (xAI), ajoute le 16/10/2026 sur demande de Bourama : seulement
        # grok-4.3 et grok-4.7 (ni grok-build-0.1, modele de code, ni
        # grok-4.20-multi-agent, modele de recherche approfondie en beta).
        # Comme DeepSeek, deux modeles pour trois paliers : essentiel et
        # avance partagent grok-4.3, pro passe sur grok-4.7. Prix xAI par
        # million de tokens (docs.x.ai/developers/pricing) : grok-4.3 a
        # 1,25 $ / 2,50 $, grok-4.7 a 2 $ / 6 $.
        "essentiel": {"id": "grok-4.3", "label": "Grok 4.3"},
        "avance": {"id": "grok-4.3", "label": "Grok 4.3"},
        "pro": {"id": "grok-4.7", "label": "Grok 4.7"},
        # Affichage seulement (Bientot), pas branche : grok-build-0.1 est un
        # modele de code (1 $ / 2 $ par million), pas un modele de discussion.
        "specialise": {"id": "grok-build-0.1", "label": "Grok Build 0.1"},
    },
    "deepseek": {
        # L'API DeepSeek n'expose que 2 modeles stables a la fois
        # (aujourd'hui deepseek-v4-flash / deepseek-v4-pro), pas de nom
        # par version -- contrairement aux 3 paliers distincts vendus par
        # les autres fournisseurs. essentiel+avance partagent donc le
        # meme modele (flash), pro passe sur le plus gros (pro).
        # MAJ 02/08/2026 : les anciens alias deepseek-chat/deepseek-
        # reasoner (utilises jusqu'ici) ont ete retires par DeepSeek le
        # 24/07/2026 (15:59 UTC) -- remplaces ici par les noms actuels.
        # Bug decouvert en verifiant les prix pour Bourama : nos appels
        # DeepSeek echouaient probablement en silence depuis le 24/07.
        "essentiel": {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash"},
        "avance": {"id": "deepseek-v4-flash", "label": "DeepSeek V4 Flash"},
        "pro": {"id": "deepseek-v4-pro", "label": "DeepSeek V4 Pro"},
    },
}

# Gating pattern (voir principe etabli sur les autres fonctionnalites de
# la plateforme) : un fournisseur sans cle API configuree disparait
# silencieusement de la liste, jamais d'erreur visible pour l'usager.
VARIABLES_CLE_PAR_DISTRIBUTEUR = {
    "claude": "ANTHROPIC_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",  # reprend la cle Gemini deja utilisee par main.py si presente
    "grok": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def cle_api_du_distributeur(distributeur):
    """
    Clé API d'un fournisseur : le nom de la variable se règle dans Supabase (colonne
    variable_cle_api de fournisseurs_llm), avec VARIABLES_CLE_PAR_DISTRIBUTEUR comme repli.
    None si la variable n'est pas définie sur le serveur.
    """
    fournisseur = _config_modeles()["fournisseurs"].get(distributeur) or {}
    variable = fournisseur.get("variable_cle_api") or VARIABLES_CLE_PAR_DISTRIBUTEUR.get(distributeur)
    return get_secret(variable) if variable else None


def _distributeur_disponible(distributeur, config=None):
    """
    Regle de cle API lue dans Supabase (table fournisseurs_llm) : si
    cle_api_requise vaut true, le fournisseur disparait quand sa cle est
    absente du serveur ; si elle vaut false, il reste visible sans verifier
    la cle.
    """
    config = config or _config_modeles()
    fournisseur = config["fournisseurs"].get(distributeur)
    if not fournisseur:
        return False
    if not fournisseur["cle_api_requise"]:
        return True
    variable = fournisseur["variable_cle_api"]
    return bool(variable and get_secret(variable))


# Valeur de repli (14/10/2026, demande de Bourama : DeepSeek est utilisable, les autres
# s'affichent grisés dans le sélecteur de modèle du chat mais ne se choisissent pas
# encore). Depuis le 15/10/2026 le statut Bientôt se règle dans Supabase, colonne
# bientot de la table fournisseurs_llm. Cette liste ne sert plus que si Supabase ne
# répond pas ou si les tables sont vides.
DISTRIBUTEURS_BIENTOT = ["claude", "gpt", "gemini", "grok"]

# Mot affiché sur les modèles Bientôt, par langue. Valeur de repli : le texte se règle
# dans la table textes_modeles_llm de Supabase (cle = bientot).
LIBELLE_BIENTOT_DE_REPLI = {"fr": "Bientôt"}

# Configuration des modèles (demande de Bourama du 15/10/2026 : tout doit se régler
# depuis Supabase, sans toucher au code). Trois tables : fournisseurs_llm (ordre de la
# hiérarchie, statut Bientôt, règle de clé API), modeles_llm (un modèle par ligne) et
# textes_modeles_llm (mot Bientôt par langue). Les constantes ci-dessus restent comme
# valeurs de repli. Un changement dans Supabase est vu en une minute environ.
DUREE_CACHE_CONFIG_MODELES_SECONDES = 60

_cache_config_modeles = {"valeur": None, "expire_a": 0}
_supabase_config_modeles = None


def _client_supabase_config_modeles():
    global _supabase_config_modeles
    if _supabase_config_modeles is None:
        from supabase import create_client, ClientOptions
        try:
            from core.client_http_supabase import nouveau_client_http_supabase
        except ImportError:
            from client_http_supabase import nouveau_client_http_supabase
        _supabase_config_modeles = create_client(
            get_secret("SUPABASE_URL"),
            get_secret("SUPABASE_SECRET"),
            options=ClientOptions(httpx_client=nouveau_client_http_supabase()),
        )
    return _supabase_config_modeles


def _config_modeles_de_repli():
    fournisseurs = {}
    for distributeur in ORDRE_DISTRIBUTEURS:
        fournisseurs[distributeur] = {
            "bientot": distributeur in DISTRIBUTEURS_BIENTOT,
            "cle_api_requise": True,
            "variable_cle_api": VARIABLES_CLE_PAR_DISTRIBUTEUR.get(distributeur),
            # None : core/identite_modele.py prend alors son nom de repli.
            "nom_affiche": None,
        }
    return {
        "distributeurs": list(ORDRE_DISTRIBUTEURS),
        "fournisseurs": fournisseurs,
        "paliers": list(ORDRE_PALIERS),
        "modeles": {distributeur: dict(paliers) for distributeur, paliers in HIERARCHIE_MODELES.items()},
        "textes": {"bientot": dict(LIBELLE_BIENTOT_DE_REPLI)},
    }


def _lire_config_modeles_supabase():
    """
    Lit les trois tables de configuration. Renvoie None si Supabase n'est pas
    configuré sur ce serveur ou si les tables sont vides (le repli prend alors le
    relais) ; laisse remonter l'exception si la lecture échoue.
    """
    if not (get_secret("SUPABASE_URL") and get_secret("SUPABASE_SECRET")):
        return None
    client = _client_supabase_config_modeles()
    lignes_fournisseurs = (
        client.table("fournisseurs_llm")
        .select("distributeur, ordre, bientot, cle_api_requise, variable_cle_api, nom_affiche")
        .order("ordre")
        .execute()
        .data
        or []
    )
    lignes_modeles = (
        client.table("modeles_llm")
        .select("distributeur, palier, niveau, modele_id, label, actif")
        .execute()
        .data
        or []
    )
    lignes_textes = client.table("textes_modeles_llm").select("cle, langue, texte").execute().data or []
    if not lignes_fournisseurs or not lignes_modeles:
        logging.warning("Tables fournisseurs_llm ou modeles_llm vides : valeurs de repli du code utilisees.")
        return None

    fournisseurs = {}
    for ligne in lignes_fournisseurs:
        fournisseurs[ligne["distributeur"]] = {
            "bientot": bool(ligne.get("bientot")),
            "cle_api_requise": bool(ligne.get("cle_api_requise", True)),
            "variable_cle_api": ligne.get("variable_cle_api"),
            "nom_affiche": ligne.get("nom_affiche"),
        }
    modeles = {}
    niveaux = {}
    for ligne in lignes_modeles:
        if not ligne.get("actif", True) or ligne["distributeur"] not in fournisseurs:
            continue
        modeles.setdefault(ligne["distributeur"], {})[ligne["palier"]] = {
            "id": ligne["modele_id"],
            "label": ligne["label"],
        }
        niveau = ligne["niveau"]
        niveaux[ligne["palier"]] = min(niveau, niveaux.get(ligne["palier"], niveau))
    textes = {}
    for ligne in lignes_textes:
        textes.setdefault(ligne["cle"], {})[ligne["langue"]] = ligne["texte"]
    return {
        "distributeurs": [ligne["distributeur"] for ligne in lignes_fournisseurs],
        "fournisseurs": fournisseurs,
        "paliers": sorted(niveaux, key=lambda palier: niveaux[palier]),
        "modeles": modeles,
        "textes": textes,
    }


def _config_modeles():
    """
    Configuration des modèles en vigueur : Supabase (cache d'une minute), sinon la
    dernière configuration connue si la lecture échoue, sinon les valeurs de repli.
    """
    maintenant = time.time()
    if _cache_config_modeles["valeur"] is not None and _cache_config_modeles["expire_a"] > maintenant:
        return _cache_config_modeles["valeur"]
    try:
        config = _lire_config_modeles_supabase() or _config_modeles_de_repli()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture configuration des modèles) : {e}")
        config = _cache_config_modeles["valeur"] or _config_modeles_de_repli()
    _cache_config_modeles["valeur"] = config
    _cache_config_modeles["expire_a"] = maintenant + DUREE_CACHE_CONFIG_MODELES_SECONDES
    return config


def reinitialiser_cache_config_modeles():
    """Force la relecture immédiate de la configuration (utile aux tests)."""
    _cache_config_modeles["valeur"] = None
    _cache_config_modeles["expire_a"] = 0


def libelles_bientot():
    """Mot affiché sur les modèles Bientôt, par langue (table textes_modeles_llm)."""
    return dict(_config_modeles()["textes"].get("bientot") or LIBELLE_BIENTOT_DE_REPLI)


def efforts_pour_modele(modele_id, distributeur):
    try:
        from efforts_modeles import efforts_pour_modele as _efforts
    except ImportError:
        from core.efforts_modeles import efforts_pour_modele as _efforts
    return _efforts(modele_id, distributeur)


def effort_defaut(efforts):
    try:
        from efforts_modeles import effort_defaut as _defaut
    except ImportError:
        from core.efforts_modeles import effort_defaut as _defaut
    return _defaut(efforts)


def modeles_disponibles_pour_agent(distributeur_debloque, palier_debloque):
    """
    Calcule la liste des modeles reellement choisissables pour un agent,
    a partir de son distributeur/palier debloques (colonnes `agents`,
    voir api/agents.py). Renvoie [] si distributeur_debloque est None/
    "aucun" : dans ce cas le frontend n'affiche AUCUN selecteur, l'agent
    tourne sur la cascade Groq habituelle comme avant cette feature.

    Chaque element : {"modele_id", "label", "distributeur", "palier"}.
    Cumulatif sur les deux axes (voir docstring du module) ET filtre par
    la regle de cle API (cle absente et cle_api_requise vrai : fournisseur
    invisible). Les fournisseurs marques Bientôt dans Supabase sont toujours
    exclus, cle API presente ou non. Tout vient de la configuration Supabase
    (voir _config_modeles), avec le code comme valeur de repli.
    """
    if not distributeur_debloque or distributeur_debloque == "aucun":
        return []
    config = _config_modeles()
    ordre_distributeurs = config["distributeurs"]
    ordre_paliers = config["paliers"]
    if distributeur_debloque not in ordre_distributeurs:
        logging.error(f"distributeur_debloque inconnu : {distributeur_debloque}")
        return []
    if not ordre_paliers:
        return []
    if palier_debloque not in ordre_paliers:
        palier_debloque = ordre_paliers[0]

    # Hierarchie cumulative descendante : le premier de la liste debloque tout
    # ce qui le suit, donc la tranche va de l'index du distributeur debloque
    # jusqu'a la fin de la liste.
    distributeurs_autorises = ordre_distributeurs[ordre_distributeurs.index(distributeur_debloque):]
    paliers_autorises = ordre_paliers[: ordre_paliers.index(palier_debloque) + 1]

    resultats = []
    ids_deja_vus = set()
    for distributeur in distributeurs_autorises:
        if config["fournisseurs"][distributeur]["bientot"]:
            continue
        if not _distributeur_disponible(distributeur, config):
            continue
        for palier in paliers_autorises:
            info = config["modeles"].get(distributeur, {}).get(palier)
            if not info:
                continue
            # Dedoublonnage par modele_id (cas DeepSeek, ou deux paliers
            # partagent le meme modele) : sans cela le meme modele apparaitrait
            # deux fois d'affilee dans la liste.
            if info["id"] in ids_deja_vus:
                continue
            ids_deja_vus.add(info["id"])
            # Efforts de réflexion possibles pour ce modèle (20/10/2026, voir
            # core/efforts_modeles.py) : le frontend n'affiche que ceux-là, et aucun réglage
            # d'effort si la liste est vide.
            efforts = efforts_pour_modele(info["id"], distributeur)
            resultats.append({
                "modele_id": info["id"],
                "label": info["label"],
                "distributeur": distributeur,
                "palier": palier,
                "efforts": efforts,
                "effort_defaut": effort_defaut(efforts),
            })
    return resultats


def modeles_bientot_pour_agent(distributeur_debloque, palier_debloque):
    """
    Modèles affichés grisés avec la mention "Bientôt" : tous les niveaux de
    chaque fournisseur marqué Bientôt dans Supabase (table fournisseurs_llm),
    dans l'ordre de la hiérarchie puis des niveaux. Même forme d'élément que
    modeles_disponibles_pour_agent, plus la clé libelles_bientot (le mot
    Bientôt par langue, réglé dans la table textes_modeles_llm).

    Vide quand l'agent n'a aucun modèle choisissable : le frontend n'affiche
    alors aucun sélecteur, comme avant. Un modèle déjà choisissable est exclu,
    pour qu'il ne figure jamais deux fois dans la liste.

    Ces modèles ne sont JAMAIS acceptés par modele_id_est_autorise (qui ne lit
    que modeles_disponibles_pour_agent) : le frontend ne peut pas les imposer.
    """
    disponibles = modeles_disponibles_pour_agent(distributeur_debloque, palier_debloque)
    if not disponibles:
        return []

    config = _config_modeles()
    libelles = libelles_bientot()
    ids_a_exclure = {m["modele_id"] for m in disponibles}
    resultats = []
    for distributeur in config["distributeurs"]:
        if not config["fournisseurs"][distributeur]["bientot"]:
            continue
        for palier in config["paliers"]:
            info = config["modeles"].get(distributeur, {}).get(palier)
            if not info or info["id"] in ids_a_exclure:
                continue
            ids_a_exclure.add(info["id"])
            resultats.append({
                "modele_id": info["id"],
                "label": info["label"],
                "distributeur": distributeur,
                "palier": palier,
                "libelles_bientot": dict(libelles),
            })
    return resultats


def modele_id_est_autorise(modele_id, distributeur_debloque, palier_debloque):
    """
    Verification cote backend AVANT d'honorer un choix de modele envoye
    par le frontend (jamais fait confiance a un id de modele venu du
    client sans le revalider contre ce que l'agent a reellement
    debloque) : voir api/chat.py et api/agents.py.
    """
    disponibles = modeles_disponibles_pour_agent(distributeur_debloque, palier_debloque)
    return any(m["modele_id"] == modele_id for m in disponibles)


def distributeur_pour_modele_id(modele_id):
    """Retrouve le nom du distributeur a partir d'un modele_id, pour
    savoir quel SDK appeler dans generer_reponse_premium ci-dessous."""
    for distributeur, paliers in _config_modeles()["modeles"].items():
        for info in paliers.values():
            if info["id"] == modele_id:
                return distributeur
    return None


def _stream_claude(modele_id, system_prompt, messages):
    from anthropic import Anthropic
    client = Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
    with client.messages.stream(
        model=modele_id,
        max_tokens=4096,
        system=system_prompt or "",
        messages=messages,
    ) as stream:
        for texte in stream.text_stream:
            yield texte


def _stream_gpt(modele_id, system_prompt, messages):
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    messages_openai = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
    flux = client.chat.completions.create(
        model=modele_id,
        messages=messages_openai,
        stream=True,
    )
    for morceau in flux:
        delta = morceau.choices[0].delta.content if morceau.choices else None
        if delta:
            yield delta


# Effort de reflexion de DeepSeek (04/10/2026, demande Bourama : le rendre
# rapide). Valeurs de l'API DeepSeek V4 : "none" (reflexion desactivee, donc
# plus rien a afficher), "low" (le minimum qui reflechit encore), "high"
# (defaut de l'API quand rien n'est envoye), "max". Source :
# api-docs.deepseek.com/api/create-chat-completion. Un seul endroit a
# modifier pour tout DeepSeek (chemin premium ET cascade, voir
# core/boucle_agent.py:_effort_reflexion).
DEEPSEEK_REASONING_EFFORT = "low"

# Valeurs que la personne peut choisir dans le reglage "Effort" (04/10/2026,
# demande Bourama). Toute autre valeur recue du frontend est ignoree et
# remplacee par DEEPSEEK_REASONING_EFFORT (jamais fait confiance au client).
EFFORTS_REFLEXION_DEEPSEEK = ("none", "low", "high", "max")


def normaliser_effort_reflexion(effort):
    """Effort valide pour DeepSeek, ou None si absent/invalide (l'appelant
    retombe alors sur DEEPSEEK_REASONING_EFFORT)."""
    return effort if effort in EFFORTS_REFLEXION_DEEPSEEK else None


# Consigne propre a DeepSeek (04/10/2026, demande Bourama) : sa reflexion
# est maintenant affichee a l'ecran, elle doit donc etre dans la langue de
# la personne. Pas de langue en dur : on lui dit de suivre la langue du
# dernier message de l'utilisateur. Ajoutee UNIQUEMENT pour DeepSeek (jamais
# au prompt commun, qui sert aussi a Groq/Claude/GPT/Gemini).
CONSIGNE_LANGUE_REFLEXION = (
    "Ton raisonnement interne (la reflexion avant ta reponse) doit etre ecrit "
    "dans la meme langue que le dernier message de l'utilisateur, "
    "pas dans une autre langue par defaut."
)


def ajouter_consigne_langue_reflexion(system_prompt):
    """Texte du prompt systeme + la consigne de langue de reflexion."""
    base = system_prompt or ""
    return (base + "\n\n" + CONSIGNE_LANGUE_REFLEXION) if base else CONSIGNE_LANGUE_REFLEXION


def _stream_deepseek(modele_id, system_prompt, messages, effort=None):
    # DeepSeek : API compatible OpenAI, seule la base_url change (voir
    # docstring du module -- deepseek-v4-flash / deepseek-v4-pro).
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    system_deepseek = ajouter_consigne_langue_reflexion(system_prompt)
    messages_openai = [{"role": "system", "content": system_deepseek}] + messages
    flux = client.chat.completions.create(
        model=modele_id,
        messages=messages_openai,
        stream=True,
        reasoning_effort=normaliser_effort_reflexion(effort) or DEEPSEEK_REASONING_EFFORT,
    )
    for morceau in flux:
        if not morceau.choices:
            continue
        delta = morceau.choices[0].delta
        # DeepSeek envoie sa reflexion dans delta.reasoning_content (champ
        # separe de delta.content, reflexion d'abord, voir
        # api-docs.deepseek.com/api/create-chat-completion). On la remonte
        # sous forme d'evenement (dict) pour que main.py l'affiche, au lieu
        # de la jeter : sans ca l'utilisateur ne voit rien pendant toute
        # la reflexion.
        reflexion = getattr(delta, "reasoning_content", None)
        if reflexion:
            yield {"type": "raisonnement", "texte": reflexion}
        if delta.content:
            yield delta.content


def _stream_grok(modele_id, system_prompt, messages):
    # Grok (xAI) : API compatible OpenAI, seule la base_url change
    # (https://api.x.ai/v1, docs.x.ai/developers/pricing). Texte seul, comme
    # Claude, GPT et Gemini : pas d'outils sur ce chemin. Aucun reglage
    # d'effort envoye : la page xAI ne le documente pas pour ces modeles.
    from openai import OpenAI
    client = OpenAI(api_key=get_secret("XAI_API_KEY"), base_url="https://api.x.ai/v1")
    messages_openai = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
    flux = client.chat.completions.create(
        model=modele_id,
        messages=messages_openai,
        stream=True,
    )
    for morceau in flux:
        delta = morceau.choices[0].delta.content if morceau.choices else None
        if delta:
            yield delta


def _stream_gemini(modele_id, system_prompt, messages):
    # Reutilise le client google-genai deja initialise ailleurs dans le
    # projet (voir core/main.py) -- instancie ici localement pour garder
    # ce module independant, cout negligeable (pas d'appel reseau a la
    # construction du client).
    from google import genai
    client = genai.Client(api_key=get_secret("GOOGLE_API_KEY"))
    contenu = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contenu.append({"role": role, "parts": [{"text": m["content"]}]})
    flux = client.models.generate_content_stream(
        model=modele_id,
        contents=contenu,
        config={"system_instruction": system_prompt} if system_prompt else None,
    )
    for morceau in flux:
        if morceau.text:
            yield morceau.text


_STREAMERS_PAR_DISTRIBUTEUR = {
    "claude": _stream_claude,
    "gpt": _stream_gpt,
    "deepseek": _stream_deepseek,
    "grok": _stream_grok,
    "gemini": _stream_gemini,
}


def generer_reponse_premium(modele_id, system_prompt, messages, effort=None):
    """
    Generateur de morceaux de reponse (str) pour un modele premium deja
    valide par modele_id_est_autorise(). `messages` : liste de
    {"role": "user"|"assistant", "content": "..."}, format deja utilise
    cote main.py pour l'historique. Leve l'exception du SDK sous-jacent
    telle quelle si l'appel echoue -- a l'appelant (main.py) de decider
    du repli (ex: retomber sur la cascade Groq).

    Depuis le correctif de la reflexion DeepSeek : un morceau peut aussi
    etre un dict {"type": "raisonnement", "texte": "..."} (reflexion du
    modele, pas la reponse). Aujourd'hui seul DeepSeek en emet. L'appelant
    doit le transmettre tel quel a l'ecran et NE PAS l'ajouter a la
    reponse sauvegardee. Pas d'autres evenements structures (voir LIMITE
    CONNUE en tete de fichier : pas d'outils).
    """
    distributeur = distributeur_pour_modele_id(modele_id)
    if distributeur is None:
        raise ValueError(f"modele_id inconnu : {modele_id}")
    streamer = _STREAMERS_PAR_DISTRIBUTEUR[distributeur]
    if distributeur == "deepseek":
        # Seul DeepSeek a un reglage d'effort aujourd'hui (les autres
        # fournisseurs n'en recoivent pas, leur flux ne change pas).
        yield from streamer(modele_id, system_prompt, messages, effort=effort)
        return
    yield from streamer(modele_id, system_prompt, messages)
