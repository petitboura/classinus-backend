"""
État des connexions de l'utilisateur, pour l'IA (26/10/2026, demande de Bourama).

Problème d'origine : l'IA ne savait pas quels services l'utilisateur avait connectés, ni quels
serveurs MCP personnels étaient actifs. Un service non connecté était écarté en silence, et l'IA
répondait que l'outil n'existait pas au lieu de proposer de le connecter.

Ce module ne fait QUE :
- dire, pour chaque service connectable, s'il est connecté, à reconnecter ou pas connecté ;
- retrouver, à partir d'un besoin en langage libre, les services pas encore connectés qui
  pourraient aider (l'IA ne voit jamais toute la liste : elle cherche, puis propose) ;
- écrire les textes que l'IA reçoit (bloc du prompt, réponse de demander_outils).

Les données (liste des services, mots clés, versions doubles) vivent dans registre_outils.py.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from recherche_outils import _tokeniser
from registre_outils import SERVICES_CONNECTABLES, VERSIONS_DOUBLES

CONNECTE = "connecte"
A_RECONNECTER = "a_reconnecter"
NON_CONNECTE = "non_connecte"
INCONNU = "inconnu"  # lecture impossible : on ne prétend jamais "pas connecté" dans ce cas

# Durée pendant laquelle l'état d'un utilisateur est réutilisé (un message enchaîne souvent
# plusieurs allers-retours). Vidé dès qu'une connexion change : voir invalider_etats().
DUREE_CACHE_SECONDES = 20
_CACHE = {}
_VERROU = threading.Lock()

# Mots trop généraux pour désigner un service à eux seuls (un seul de ces mots ne suffit pas).
_MOTS_GENERAUX = {"site", "service", "projet", "base", "donnees", "fichier", "document", "page", "image", "video", "creer", "generer"}

NOM_BLOC_CARTE = "connecteur"
# Carte de proposition d'un serveur MCP que Classinus ne connaît pas (27/10/2026, demande de Bourama).
NOM_BLOC_SERVEUR_MCP = "serveurmcp"


def etat_service(service, user_id):
    """
    État d'un service pour un utilisateur, au même format que la route
    GET /api/connexions/{service}/statut : {"connecte": bool, "a_reconnecter": bool (si connu)}.
    Renvoie None si le service est inconnu. Source unique : la route et l'IA lisent la même chose.
    """
    import connexions.notion as notion
    import connexions.higgsfield_mcp as higgsfield_mcp
    import connexions.netlify_mcp as netlify_mcp
    import connexions.render_mcp as render_mcp
    import connexions.platform_mcp_oauth as platform_mcp_oauth
    from connexions.oauth_generique import (
        SERVICES,
        est_connecte,
        a_reconnecter as a_reconnecter_oauth_generique,
        obtenir_token_valide as obtenir_token_valide_generique,
    )

    if service == "netlify_mcp":
        return {"connecte": netlify_mcp.est_connecte(user_id)}
    if service == "render_mcp":
        return {"connecte": render_mcp.est_connecte(user_id)}
    if service == "higgsfield_mcp":
        connecte = higgsfield_mcp.est_connecte(user_id)
        return {"connecte": connecte, "a_reconnecter": (not connecte) and higgsfield_mcp.a_reconnecter(user_id)}
    if service in platform_mcp_oauth.FOURNISSEURS:
        connecte = platform_mcp_oauth.est_connecte(service, user_id)
        return {"connecte": connecte, "a_reconnecter": (not connecte) and platform_mcp_oauth.a_reconnecter(service, user_id)}
    if service == "notion":
        return {"connecte": notion.est_connecte(user_id)}
    if service not in SERVICES:
        return None
    if service.endswith("_mcp"):
        connecte = obtenir_token_valide_generique(service, user_id) is not None
        return {"connecte": connecte, "a_reconnecter": (not connecte) and a_reconnecter_oauth_generique(service, user_id)}
    return {"connecte": est_connecte(service, user_id)}


def _etat_lisible(service, user_id):
    try:
        brut = etat_service(service, user_id)
    except Exception as exc:
        logging.warning("État de connexion illisible pour %s (%s).", service, type(exc).__name__)
        return INCONNU
    if brut is None:
        return INCONNU
    if brut.get("connecte"):
        return CONNECTE
    return A_RECONNECTER if brut.get("a_reconnecter") else NON_CONNECTE


def etats_connexions(user_id):
    """{service: connecte | a_reconnecter | non_connecte | inconnu} pour les services proposables."""
    if not user_id:
        return {}
    maintenant = time.time()
    with _VERROU:
        entree = _CACHE.get(user_id)
        if entree and entree[0] > maintenant:
            return dict(entree[1])
    services = [s["service"] for s in SERVICES_CONNECTABLES if s["proposable"]]
    # En parallèle : une lecture de base par service, jamais l'une après l'autre.
    with ThreadPoolExecutor(max_workers=min(8, len(services) or 1)) as pool:
        etats = dict(zip(services, pool.map(lambda nom: _etat_lisible(nom, user_id), services)))
    with _VERROU:
        _CACHE[user_id] = (time.time() + DUREE_CACHE_SECONDES, etats)
        if len(_CACHE) > 500:
            for cle in [c for c, (exp, _) in _CACHE.items() if exp <= maintenant]:
                _CACHE.pop(cle, None)
    return dict(etats)


def invalider_etats(user_id=None):
    """
    À appeler dès qu'une connexion est créée, retirée ou refaite, pour que l'IA le voie tout de suite.
    Sans utilisateur (retour OAuth, où la session n'est pas connue) : tout le cache est vidé.
    """
    with _VERROU:
        if user_id is None:
            _CACHE.clear()
        else:
            _CACHE.pop(user_id, None)


def _entree(service):
    return next((s for s in SERVICES_CONNECTABLES if s["service"] == service), None)


def entree_par_categorie(categorie):
    """Entrée du registre dont les outils sont dans cette catégorie de demander_outils (ou None)."""
    return next((s for s in SERVICES_CONNECTABLES if s["categorie"] == categorie), None)


# ---------------------------------------------------------------------------
# Retrouver un service pas encore connecté depuis un besoin en langage libre
# ---------------------------------------------------------------------------

def _racine(mot):
    # Cinq lettres : "déploie", "déployer" et "déploiement" se rejoignent sans vrai traitement linguistique.
    return mot[:5]


def services_a_proposer(besoin, etats, exclus=(), maximum=3):
    """
    Services proposables, pas connectés (ou à reconnecter), dont les mots clés recoupent le besoin.
    Il faut deux mots en commun, ou un mot du nom du service : un mot général seul (site, fichier)
    ne suffit pas, sinon l'IA proposerait des connexions à chaque recherche.
    """
    mots_besoin = {_racine(m) for m in _tokeniser(besoin or "")}
    if not mots_besoin:
        return []
    trouves = []
    for entree in SERVICES_CONNECTABLES:
        if not entree["proposable"] or entree["service"] in exclus:
            continue
        if etats.get(entree["service"]) not in (NON_CONNECTE, A_RECONNECTER):
            continue
        mots_nom = {_racine(m) for m in _tokeniser(entree["label"])}
        mots_cles = {_racine(m) for m in _tokeniser(entree["mots_cles"])}
        communs = mots_besoin & mots_cles
        precis = {m for m in communs if m not in _MOTS_GENERAUX}
        if (mots_besoin & mots_nom) or (len(communs) >= 2 and precis):
            trouves.append((len(communs) + 5 * len(mots_besoin & mots_nom), entree))
    trouves.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in trouves[:maximum]]


def texte_proposition(entree, etat):
    """Ce que l'IA reçoit quand un service utile existe mais n'est pas connecté."""
    bloc = f"```{NOM_BLOC_CARTE}\n" + json.dumps({"service": entree["service"]}) + "\n```"
    situation = (
        "L'utilisateur l'avait connecté, mais la connexion a expiré : elle est à refaire."
        if etat == A_RECONNECTER
        else "L'utilisateur ne l'a pas encore connecté."
    )
    return (
        f"Le service {entree['label']} existe dans Classinus. {situation} Ses outils ne sont donc "
        "pas disponibles pour l'instant. Ne dis jamais qu'il n'existe pas. Propose à l'utilisateur de le "
        f"connecter : écris ce bloc tel quel dans ta réponse, avec une phrase qui dit pourquoi ce service "
        f"répond à sa demande :\n{bloc}\n"
        "Il se connecte en un clic sur la carte, puis un bouton te redonne la main pour reprendre la tâche."
    )


def doit_proposer_serveur_mcp(besoins, des_outils_trouves, des_services_proposes):
    """
    Vrai quand l'IA doit chercher un serveur MCP externe : rien n'a été trouvé (ni outil, ni service
    de la liste à connecter), ou un besoin parle lui-même d'un serveur MCP (l'utilisateur veut en ajouter un).
    """
    if any("mcp" in (besoin or "").lower() for besoin in besoins):
        return True
    return not des_outils_trouves and not des_services_proposes


def texte_serveur_inconnu(aucun_outil=True):
    """
    Ce que l'IA reçoit quand aucun outil ni service connu ne répond à un besoin : au lieu de dire que
    c'est impossible, elle cherche le serveur MCP officiel de l'outil et le propose dans une carte.
    L'IA ne détermine ni le type d'accès ni le caractère officiel : Classinus les vérifie lui-même
    à l'affichage de la carte (route POST /api/mcp-personnalises/sonder), et c'est l'utilisateur qui
    clique pour ajouter. Le jeton ne passe jamais par le chat.
    """
    exemple = json.dumps({
        "nom": "Nom de l'outil",
        "url": "https://adresse-du-serveur-mcp-trouvee-sur-le-site-officiel",
        "site_officiel": "https://site-officiel-de-l-outil",
        "source": "https://page-du-site-officiel-qui-annonce-cette-adresse",
        "jeton": {"lien": "https://page-ou-l-utilisateur-cree-son-jeton", "etapes": ["Première étape", "Deuxième étape"]},
    }, ensure_ascii=False)
    debut = (
        "Aucun outil de Classinus ne répond à ce besoin, mais un serveur MCP externe pourrait le faire. "
        "Ne dis pas que c'est impossible. Voici la marche à suivre : "
        if aucun_outil
        else "Si l'utilisateur veut ajouter un serveur MCP externe, voici la marche à suivre : "
    )
    return (
        debut
        + "1) Cherche avec tes outils de recherche web (cherche-les avec demander_outils si tu ne les as pas) "
        "le site officiel de l'outil, puis la page de sa documentation qui annonce son serveur MCP. "
        "Ne retiens que ce qui est écrit sur le site officiel de l'éditeur, jamais un blog ni un annuaire. "
        f"2) Écris dans ta réponse un bloc ```{NOM_BLOC_SERVEUR_MCP}``` avec ce JSON, précédé d'une phrase qui dit "
        f"pourquoi ce serveur répond à la demande :\n```{NOM_BLOC_SERVEUR_MCP}\n{exemple}\n```\n"
        "Le champ jeton est facultatif : ne le remplis que si la documentation dit qu'un jeton ou une clé d'accès est "
        "nécessaire, avec les étapes exactes pour l'obtenir. Si tu n'as pas trouvé l'adresse sur le site officiel, "
        "mets seulement ce que tu as trouvé ailleurs (la carte préviendra l'utilisateur), et si tu n'as rien trouvé "
        "laisse url vide. N'invente jamais une adresse ni un lien. "
        "3) Classinus teste lui-même l'adresse, vérifie si elle vient du site officiel et dit à l'utilisateur si un "
        "jeton est nécessaire. C'est l'utilisateur qui clique pour ajouter le serveur : tu n'ajoutes jamais rien "
        "toi-même et tu ne demandes jamais de jeton dans le chat."
    )


# ---------------------------------------------------------------------------
# Versions doubles (Higgsfield) : celle de l'utilisateur d'abord
# ---------------------------------------------------------------------------

def note_versions_doubles(noms_outils_disponibles, etats):
    """
    Phrase à ajouter à la réponse de demander_outils quand une recherche donne accès aux DEUX
    versions d'un service (la nôtre et celle du compte de l'utilisateur). Chaîne vide sinon.
    """
    from registre_outils import outils_de_la_categorie

    candidats = [{"function": {"name": nom}} for nom in noms_outils_disponibles]
    notes = []
    for double in VERSIONS_DOUBLES:
        if etats.get(double["service"]) != CONNECTE:
            continue
        a_utilisateur = outils_de_la_categorie(double["categorie_utilisateur"], candidats)
        a_classinus = outils_de_la_categorie(double["categorie_classinus"], candidats)
        if a_utilisateur and a_classinus:
            notes.append(
                f"{double['label']} existe en deux versions ici : le compte de l'utilisateur "
                f"({', '.join(o['function']['name'] for o in a_utilisateur[:3])}...) et celle de Classinus "
                f"({', '.join(o['function']['name'] for o in a_classinus)}). Utilise d'abord celle du compte "
                "de l'utilisateur, sauf s'il demande explicitement celle de Classinus."
            )
    return " ".join(notes)


# ---------------------------------------------------------------------------
# Bloc du prompt : ce que l'IA doit savoir à chaque message
# ---------------------------------------------------------------------------

def texte_prompt_connexions(etats, serveurs_perso):
    """
    Bloc <connexions> du prompt. Court exprès : les services connectés sont nommés, ceux pas
    encore connectés ne sont PAS listés (l'IA les cherche avec demander_outils, puis les propose).
    """
    libelles = {s["service"]: s["label"] for s in SERVICES_CONNECTABLES}
    connectes = [libelles[s] for s, e in etats.items() if e == CONNECTE and s in libelles]
    a_refaire = [libelles[s] for s, e in etats.items() if e == A_RECONNECTER and s in libelles]

    lignes = [
        "<connexions>",
        "Quatre familles d'outils, à ne jamais confondre :",
        "1. Les outils de Classinus : toujours disponibles, rien à connecter.",
        "2. Les services que Classinus fournit lui-même par son API, avec sa clé partagée (par exemple la "
        "génération de vidéo Higgsfield par lancer_video_higgsfield) : disponibles pour tout le monde sans connexion.",
        "3. Les services que l'utilisateur connecte lui-même à son propre compte. "
        "Connectés en ce moment : " + (", ".join(connectes) if connectes else "aucun") + ".",
    ]
    if a_refaire:
        lignes.append("Connexion expirée, à refaire : " + ", ".join(a_refaire) + ".")
    lignes.append(
        "Les autres services existent mais ne sont pas connectés : leurs outils n'apparaissent pas tant "
        "que l'utilisateur ne les a pas connectés. Si sa demande relève d'un tel service, cherche avec "
        "demander_outils : si le service existe sans être connecté, la réponse te dit comment le proposer. "
        "Ne dis jamais qu'un outil n'existe pas sans avoir cherché."
    )
    if serveurs_perso:
        noms_etats = {"actif": "actif", "desactive": "désactivé par l'utilisateur", "injoignable": "injoignable pour l'instant (panne ou connexion à refaire)"}
        detail = "; ".join(f"{s['nom']} ({noms_etats.get(s['etat'], s['etat'])})" for s in serveurs_perso)
        lignes.append("4. Les serveurs MCP ajoutés par l'utilisateur lui-même : " + detail + ". Leurs outils sont dans la catégorie serveurs_personnalises ; ceux désactivés ou injoignables ne sont pas utilisables.")
    else:
        lignes.append("4. Les serveurs MCP ajoutés par l'utilisateur lui-même : aucun pour l'instant.")
    lignes.append(
        "Quand un même service existe en deux versions (la tienne par l'API de Classinus et celle du compte "
        "de l'utilisateur, comme Higgsfield), utilise celle du compte de l'utilisateur, sauf s'il demande "
        "explicitement l'autre."
    )
    lignes.append(
        f"Pour proposer un service, écris le bloc ```{NOM_BLOC_CARTE}``` exactement comme demander_outils te le donne "
        "(une carte avec un bouton Connecter s'affiche, jamais un lien à recopier). N'invente jamais un nom de service."
    )
    lignes.append(
        "Si demander_outils ne trouve rien du tout, il t'explique comment chercher et proposer le serveur MCP officiel "
        "de l'outil. Si l'utilisateur veut ajouter un serveur MCP, appelle demander_outils avec le besoin « ajouter un "
        "serveur MCP » : la réponse t'explique comment faire. Tu n'ajoutes jamais un serveur toi-même : c'est lui qui "
        "clique sur la carte."
    )
    lignes.append("</connexions>")
    return "\n".join(lignes)


def bloc_prompt_pour_utilisateur(user_id):
    """
    Bloc <connexions> complet pour un utilisateur (services connectés + serveurs MCP personnels),
    ou None pour un visiteur sans compte. Ne lève jamais d'exception : au pire, pas de bloc.
    """
    if not user_id:
        return None
    try:
        from connexions.mcp_personnalises import etats_serveurs_pour_llm

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_etats = pool.submit(etats_connexions, user_id)
            f_perso = pool.submit(etats_serveurs_pour_llm, user_id)
            return texte_prompt_connexions(f_etats.result(), f_perso.result())
    except Exception as exc:
        logging.warning("Bloc des connexions non construit (%s).", type(exc).__name__)
        return None
