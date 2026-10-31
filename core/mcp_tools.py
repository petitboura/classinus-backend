"""
Moteur MCP generique.

Ce fichier ne contient plus la liste des outils : elle vit dans
registre_outils.py (SERVEURS_MCP). Pour ajouter un nouvel outil, va
modifier ce fichier-la, pas celui-ci.

Comment ca marche : chaque serveur MCP sait decrire lui-meme les outils
qu'il expose (list_tools). Ce fichier se contente de demander cette liste
a chaque serveur configure dans le registre ET autorise pour l'agent
courant (agents_serveurs pour les categories 2/3, agents_outils_generation
pour la categorie 1 -- granularite fine), de la transformer au format que
Groq comprend, et de savoir rappeler le bon serveur (avec la bonne URL et
les bons headers) quand Groq demande a executer un outil.

Systeme de droits, 5 categories (voir migration_droits_agents.sql) :
1. generation (interne) -- allow-list PAR OUTIL, table agents_outils_generation
2. serveur externe global sans connexion (wolfram, github...) -- allow-list PAR SERVEUR, table agents_serveurs
3. compte utilisateur final (notion...) -- allow-list PAR SERVEUR + connexion user, table agents_serveurs
4. compte du createur, scope a un agent -- table agents_connexions_createur
5. compte plateforme, partage par tous -- table plateforme_connexions (invisible cote createur/user)

Dans tous les cas : intersection avec registre_outils_plateforme.disponible
a CHAQUE lecture, jamais une copie figee -- un outil retire cote
plateforme disparait automatiquement de tous les agents qui l'avaient
coche, sans rien modifier cote agent.
"""

import os
import time
import asyncio
import logging
import json
import re

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client
from supabase import create_client, ClientOptions
from client_http_supabase import nouveau_client_http_supabase

from registre_outils import SERVEURS_MCP
from libelles_activite_ia import PARAMETRE_LIBELLE_OUTIL, schema_avec_libelle


# 21/10/2026 (demande de Bourama) : la liste des outils de Higgsfield dépasse 1 Mo
# en un seul message. La bibliothèque coupe alors la réponse sans rien renvoyer
# (erreur "Server-sent event exceeded the 1048576 byte limit"), donc Classinus ne
# voyait aucun outil Higgsfield. On relève cette limite pour le lecteur de flux
# du client MCP. Valeur modifiable sans toucher au code via la variable
# d'environnement MCP_TAILLE_MAX_EVENEMENT_OCTETS.
TAILLE_MAX_EVENEMENT_MCP_OCTETS = int(os.getenv("MCP_TAILLE_MAX_EVENEMENT_OCTETS", str(32 * 1024 * 1024)))


def _relever_limite_evenement_mcp():
    import functools
    import mcp.client.streamable_http as flux_mcp

    lecteur_original = getattr(flux_mcp, "EventSource", None)
    if lecteur_original is None or getattr(lecteur_original, "_limite_relevee", False):
        return
    lecteur_releve = functools.partial(lecteur_original, max_event_size=TAILLE_MAX_EVENEMENT_MCP_OCTETS)
    lecteur_releve._limite_relevee = True
    flux_mcp.EventSource = lecteur_releve


_relever_limite_evenement_mcp()

logging.basicConfig(level=logging.INFO)


def _get_secret_local(key):
    return os.environ.get(key)


_supabase = create_client(_get_secret_local("SUPABASE_URL"), _get_secret_local("SUPABASE_SECRET"), options=ClientOptions(httpx_client=nouveau_client_http_supabase()))


# Clovis (12/08, demande Bourama) : une seule IA -- plus de systeme
# multi-agents/multi-createurs pour les outils (l'ancien filtrage par
# agents_serveurs/agents_outils_generation a ete retire le 14/08, ces
# tables n'ont plus d'usage ici). Tout ce qui est disponible cote
# plateforme (registre_outils_plateforme.disponible=True) est actif pour
# Clovis, sans notion d'agent_id.
#
# `agent_id` reste un parametre des fonctions plus bas (transmis a
# certains url_builder/headers_builder qui en ont besoin, ex:
# _url_generation pour planifier_rappel) -- il ne sert plus a filtrer quoi
# que ce soit ici, uniquement a construire l'URL/les headers.

_DUREE_CACHE_SECONDES = 24 * 60 * 60  # 24h (demande Bourama 14/08 : ne plus
# relire ca a chaque message, ca ralentit l'IA pour rien -- le catalogue
# d'outils ne change pas d'un message a l'autre)

_cache_serveurs_disponibles = {"valeur": None, "expire_a": 0}
_cache_outils_generation_disponibles = {"valeur": None, "expire_a": 0}
_cache_catalogue_outils = {}  # nom_serveur -> {"outils": [...], "expire_a": ts}

# 31/10/2026 (demande Bourama, diagnostic memoire Render) : cache NEGATIF.
# Avant, seul un listing REUSSI etait mis en cache : un serveur en panne ou
# endormi (ex. diagnostic_classtech, service Render gratuit en veille)
# etait retente a CHAQUE message, avec a chaque fois une session MCP neuve
# jamais liberee proprement cote OS -- une des montées memoire par paliers
# derriere les OOM des 29-30/10. Apres un echec, on ne retente donc pas
# avant ce delai. Reglable sans toucher au code (0 = retenter tout de suite).
try:
    _DUREE_CACHE_NEGATIF_SECONDES = int(os.getenv("MCP_CACHE_NEGATIF_SECONDES", "600"))
    if _DUREE_CACHE_NEGATIF_SECONDES < 0:
        _DUREE_CACHE_NEGATIF_SECONDES = 600
except (TypeError, ValueError):
    _DUREE_CACHE_NEGATIF_SECONDES = 600
_cache_echecs_catalogue = {}  # nom_serveur -> expire_a (ts)
_derniers_reveils = {}  # url_reveil -> ts du dernier reveil tente

# Delai laisse a un service endormi pour se reveiller avant le listing
# (reveil a la demande, seulement sur un cache vide ou expire : jamais a
# chaque message). Reglable sans toucher au code.
try:
    _DELAI_REVEIL_SECONDES = int(os.getenv("MCP_REVEIL_DELAI_SECONDES", "90"))
    if _DELAI_REVEIL_SECONDES <= 0:
        _DELAI_REVEIL_SECONDES = 90
except (TypeError, ValueError):
    _DELAI_REVEIL_SECONDES = 90


def forcer_rechargement_catalogue_outils():
    """
    Vide tout le cache (droits ET catalogue d'outils MCP), pour forcer un
    rechargement complet au prochain message. A appeler manuellement apres
    un changement cote registre_outils_plateforme (nouvel outil active/
    desactive) ou un ajout d'outil MCP, sans attendre les 24h.
    """
    _cache_serveurs_disponibles["valeur"] = None
    _cache_serveurs_disponibles["expire_a"] = 0
    _cache_outils_generation_disponibles["valeur"] = None
    _cache_outils_generation_disponibles["expire_a"] = 0
    _cache_catalogue_outils.clear()
    _cache_echecs_catalogue.clear()
    _derniers_reveils.clear()
    _cache_parametres_outils["valeur"] = None
    _cache_parametres_outils["expire_a"] = 0


def _serveurs_disponibles():
    """Noms des serveurs actives cote plateforme, cache 24h."""
    maintenant = time.time()
    if _cache_serveurs_disponibles["valeur"] is not None and _cache_serveurs_disponibles["expire_a"] > maintenant:
        return _cache_serveurs_disponibles["valeur"]
    try:
        res = _supabase.table("registre_outils_plateforme").select("nom_serveur").eq("disponible", True).execute()
        valeur = list({ligne["nom_serveur"] for ligne in (res.data or []) if ligne.get("nom_serveur")})
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture registre_outils_plateforme, serveurs) : {e}")
        valeur = _cache_serveurs_disponibles["valeur"] or []
    _cache_serveurs_disponibles["valeur"] = valeur
    _cache_serveurs_disponibles["expire_a"] = maintenant + _DUREE_CACHE_SECONDES
    return valeur


def _outils_generation_disponibles():
    """Noms des outils de generation actives cote plateforme, cache 24h."""
    maintenant = time.time()
    if _cache_outils_generation_disponibles["valeur"] is not None and _cache_outils_generation_disponibles["expire_a"] > maintenant:
        return _cache_outils_generation_disponibles["valeur"]
    try:
        res = _supabase.table("registre_outils_plateforme").select("nom_outil").eq("disponible", True).execute()
        valeur = [ligne["nom_outil"] for ligne in (res.data or []) if ligne.get("nom_outil")]
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture registre_outils_plateforme, outils génération) : {e}")
        valeur = _cache_outils_generation_disponibles["valeur"] or []
    _cache_outils_generation_disponibles["valeur"] = valeur
    _cache_outils_generation_disponibles["expire_a"] = maintenant + _DUREE_CACHE_SECONDES
    return valeur


# Valeurs de repli si parametres_outils est vide/injoignable ET qu'aucun
# cache precedent n'existe encore (tout premier appel au demarrage) --
# ce sont les memes valeurs que la ligne inseree en base a la creation
# de la table (migration creation_parametres_outils).
_REPLI_PARAMETRES_OUTILS = {
    "budget_depart": 5,
    "palier_extension": 5,
    "plafond_absolu": 20,
    "tolerance_repetition": 3,
}

_cache_parametres_outils = {"valeur": None, "expire_a": 0}


def parametres_outils():
    """
    Reglages du budget d'appels d'outils par tour (voir core/main.py,
    boucle _agent_groq) : budget_depart, palier_extension, plafond_absolu,
    tolerance_repetition. Cache 24h, repli sur la derniere valeur connue
    (ou sur _REPLI_PARAMETRES_OUTILS si aucun cache n'existe encore) si
    Supabase repond mal -- meme logique que _serveurs_disponibles.
    """
    maintenant = time.time()
    if _cache_parametres_outils["valeur"] is not None and _cache_parametres_outils["expire_a"] > maintenant:
        return _cache_parametres_outils["valeur"]
    try:
        res = _supabase.table("parametres_outils").select("cle, valeur").execute()
        lignes = {ligne["cle"]: ligne["valeur"] for ligne in (res.data or [])}
        valeur = {**_REPLI_PARAMETRES_OUTILS, **lignes}
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture parametres_outils) : {e}")
        valeur = _cache_parametres_outils["valeur"] or dict(_REPLI_PARAMETRES_OUTILS)
    _cache_parametres_outils["valeur"] = valeur
    _cache_parametres_outils["expire_a"] = maintenant + _DUREE_CACHE_SECONDES
    return valeur


def _reveiller_serveur(url_reveil):
    """
    Reveil a la demande d'un service endormi (31/10/2026) : un simple GET
    sur son URL de sante, qui laisse au service gratuit le temps de
    demarrer avant qu'on tente le vrai listing MCP. Ne leve JAMAIS : si le
    reveil echoue, le listing derriere dira la vraie erreur, une fois, puis
    le cache negatif prendra le relais.
    """
    import urllib.request

    try:
        requete = urllib.request.Request(url_reveil, headers={"User-Agent": "Classinus-Reveil/1.0"})
        with urllib.request.urlopen(requete, timeout=_DELAI_REVEIL_SECONDES) as reponse:
            logging.info(f"Reveil MCP via {url_reveil} -> HTTP {reponse.status}")
    except Exception as e:
        logging.warning(f"Reveil MCP via {url_reveil} sans reponse exploitable : {e}")
    finally:
        _derniers_reveils[url_reveil] = time.time()


def _url_reveil(serveur, url):
    """URL de reveil d'un serveur : celle declaree dans le registre, sinon,
    pour le diagnostic (service gratuit qui s'endort), le /health du meme
    hote que son URL MCP -- derive de l'URL, jamais une adresse en dur."""
    if serveur.get("reveil_url"):
        return serveur["reveil_url"]
    if serveur.get("nom") == "diagnostic_classtech" and url:
        from urllib.parse import urlparse
        morceaux = urlparse(url)
        if morceaux.scheme and morceaux.netloc:
            return f"{morceaux.scheme}://{morceaux.netloc}/health"
    return None


def _reveiller_si_recent_non_tente(url_reveil):
    """Reveil au plus une fois par fenetre de cache negatif et par URL.

    Sert avant un appel reel : le catalogue peut etre en cache 24h alors
    que le service gratuit s'est rendormi entre-temps. Au-dela de la
    fenetre, un GET /health suffit a le relancer sans ralentir chaque appel.
    """
    if not url_reveil:
        return
    if time.time() - _derniers_reveils.get(url_reveil, 0) < _DUREE_CACHE_NEGATIF_SECONDES:
        return
    _derniers_reveils[url_reveil] = time.time()
    _reveiller_serveur(url_reveil)


def _lister_outils_serveur_avec_cache(nom, url, headers, reveil_url=None):
    """
    Catalogue d'un serveur MCP (nom/description/schema de chaque outil,
    via list_tools()) mis en cache 24h, cle par nom de serveur seul (pas
    par utilisateur) -- ce catalogue est le SCHEMA des outils, identique
    pour tout le monde, contrairement aux headers d'authentification qui
    eux varient par utilisateur (ex: Notion). Seul l'appel reseau
    list_tools() est evite par ce cache ; l'appel reel de l'outil
    (appeler_outil, plus bas) n'est jamais mis en cache et repart a
    chaque fois avec les bons headers de l'utilisateur courant.

    Echec (31/10/2026) : cache negatif -- l'erreur remonte une fois (pour
    les journaux), puis les appels suivants renvoient une liste vide sans
    reseau pendant _DUREE_CACHE_NEGATIF_SECONDES, au lieu de retenter a
    chaque message. Si le serveur declare une URL de reveil, on le reveille
    d'abord (service gratuit endormi), seulement sur un cache vide/expire.
    """
    maintenant = time.time()
    entree = _cache_catalogue_outils.get(nom)
    if entree is not None and entree["expire_a"] > maintenant:
        return entree["outils"]
    echec_expire_a = _cache_echecs_catalogue.get(nom, 0)
    if echec_expire_a > maintenant:
        logging.info(
            f"MCP '{nom}' non retente : echec recent en cache negatif "
            f"encore {int(echec_expire_a - maintenant)}s."
        )
        return []
    if reveil_url:
        _reveiller_serveur(reveil_url)
    try:
        outils = asyncio.run(_lister_outils_async(url, headers))
    except Exception:
        _cache_echecs_catalogue[nom] = time.time() + _DUREE_CACHE_NEGATIF_SECONDES
        raise
    _cache_echecs_catalogue.pop(nom, None)
    _cache_catalogue_outils[nom] = {"outils": outils, "expire_a": maintenant + _DUREE_CACHE_SECONDES}
    return outils


def _details_erreur(erreur, profondeur=0):
    """
    Aplatit une erreur en liste de lignes lisibles. Un groupe d'erreurs
    (TaskGroup, ExceptionGroup) est déplié jusqu'aux vraies causes, avec le
    type de chaque erreur et sa cause d'origine si elle existe. Sert
    uniquement aux journaux : ne change jamais le comportement.
    """
    if profondeur > 5:
        return [repr(erreur)]
    sous_erreurs = getattr(erreur, "exceptions", None)
    if sous_erreurs:
        lignes = []
        for sous_erreur in sous_erreurs:
            lignes.extend(_details_erreur(sous_erreur, profondeur + 1))
        return lignes
    ligne = f"{type(erreur).__name__}: {erreur}"
    cause = erreur.__cause__ or erreur.__context__
    if cause is not None and cause is not erreur:
        ligne += f" (cause d'origine : {type(cause).__name__}: {cause})"
    return [ligne]


async def _lister_outils_async(url, headers=None):
    # CORRECTION (29/07) : mcp 2.0.0 a renomme streamablehttp_client en
    # streamable_http_client ET retire le parametre headers= direct -- les
    # headers (cle API, token...) passent desormais par un httpx2.AsyncClient
    # preconfigure via create_mcp_http_client (voir doc de la lib). La
    # fonction ne renvoie plus que 2 flux (read, write), plus 3.
    async with create_mcp_http_client(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                reponse = await session.list_tools()
                return reponse.tools


def _entier_env(nom, defaut):
    try:
        valeur = int(os.getenv(nom, defaut))
        return valeur if valeur > 0 else defaut
    except (TypeError, ValueError):
        return defaut


# 22/10/2026 (demande de Bourama : outils approuvés qui tournaient à l'infini) : délai
# normal appliqué à tout appel d'outil, que le modèle peut allonger lui-même avec le
# paramètre optionnel ci-dessous quand il sait l'action longue. 60 s est la valeur par
# défaut des clients MCP courants. Réglables sans toucher au code par variables
# d'environnement.
DELAI_OUTIL_DEFAUT_SECONDES = _entier_env("DELAI_OUTIL_DEFAUT_SECONDES", 60)
DELAI_OUTIL_MAX_SECONDES = max(DELAI_OUTIL_DEFAUT_SECONDES, _entier_env("DELAI_OUTIL_MAX_SECONDES", 600))
PARAMETRE_DELAI_OUTIL = "delai_max_secondes"


class _AppelAnnule(Exception):
    pass


def _delai_demande(valeur):
    """Délai choisi par le modèle, ramené entre le délai normal et le maximum."""
    try:
        demande = int(valeur)
    except (TypeError, ValueError):
        return DELAI_OUTIL_DEFAUT_SECONDES
    return max(DELAI_OUTIL_DEFAUT_SECONDES, min(demande, DELAI_OUTIL_MAX_SECONDES))


def _schema_avec_delai(schema, delai_defaut=None, delai_max=None):
    """Ajoute le paramètre optionnel de délai au schéma d'un outil (sans toucher à l'original)."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return schema
    proprietes = schema.get("properties") or {}
    if not isinstance(proprietes, dict) or PARAMETRE_DELAI_OUTIL in proprietes:
        return schema
    delai_defaut = DELAI_OUTIL_DEFAUT_SECONDES if delai_defaut is None else delai_defaut
    delai_max = DELAI_OUTIL_MAX_SECONDES if delai_max is None else delai_max
    return {
        **schema,
        "properties": {
            **proprietes,
            PARAMETRE_DELAI_OUTIL: {
                "type": "integer",
                "description": (
                    f"Optionnel. Attente maximale en secondes (défaut {delai_defaut}, "
                    f"maximum {delai_max}). À augmenter seulement pour une action connue pour être longue."
                ),
            },
        },
    }


async def _appeler_avec_delai_et_arret(coroutine, delai, arret):
    """
    Attend l'appel en regardant toutes les 0,25 s le bouton Arrêter et l'échéance. Dans les deux
    cas la tâche est annulée proprement (la connexion au service est fermée).
    """
    tache = asyncio.ensure_future(coroutine)
    echeance = time.monotonic() + delai
    try:
        while not tache.done():
            if arret is not None and arret.est_demande():
                raise _AppelAnnule()
            if time.monotonic() >= echeance:
                raise TimeoutError()
            await asyncio.wait({tache}, timeout=0.25)
        return tache.result()
    finally:
        if not tache.done():
            tache.cancel()
            try:
                await tache
            except BaseException as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise


_EXTENSIONS_IMAGES_RESULTAT = ("png", "jpg", "jpeg", "webp", "gif")
_EXTENSIONS_VIDEOS_RESULTAT = ("mp4", "webm", "mov")
_REGEX_URL_RESULTAT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _extension_url(url):
    fin = (url or "").split("?", 1)[0].rsplit(".", 1)
    if len(fin) != 2:
        return ""
    return fin[-1].strip().lower().rstrip(").,]!;:'\"")


def _medias_depuis_texte(texte):
    """Liens (images, vidéos) trouvés dans un texte de résultat d'outil."""
    images, videos, vues = [], [], set()
    for brut in _REGEX_URL_RESULTAT.findall(texte or ""):
        url = brut.rstrip(").,]!;:'\"")
        if not url or url in vues:
            continue
        vues.add(url)
        extension = _extension_url(url)
        if extension in _EXTENSIONS_IMAGES_RESULTAT:
            images.append({"titre": url, "url": url})
        elif extension in _EXTENSIONS_VIDEOS_RESULTAT:
            videos.append({"titre": url, "url": url})
    return images, videos


def _texte_depuis_blocs_mcp(blocs):
    """Texte assemblé depuis les blocs de contenu d'un résultat MCP.

    Avant (correctif Higgsfield affichage) : seul le premier bloc texte
    était gardé, tout le reste (autres textes, images, sons, ressources)
    était jeté. Maintenant : les textes sont joints, les images natives
    deviennent une galerie JSON {"images": [...]} comprise par
    l'affichage, les sons et ressources restent lisibles en texte.
    Ne lève jamais : en cas de forme inconnue, repli texte best-effort.
    """
    try:
        textes, images = [], []
        elements = []
        for bloc in blocs or []:
            elements.append(bloc)
            ressource = getattr(bloc, "resource", None)
            if ressource is not None:
                elements.append(ressource)
        for element in elements:
            texte = getattr(element, "text", None)
            if isinstance(texte, str) and texte.strip():
                textes.append(texte)
                continue
            donnees = getattr(element, "data", None) or getattr(element, "blob", None)
            mime = (
                getattr(element, "mimeType", "")
                or getattr(element, "mime_type", "")
                or ""
            ).lower()
            if isinstance(donnees, str) and donnees:
                if mime.startswith("image/"):
                    images.append({
                        "titre": "Image renvoyée par l'outil",
                        "url": "data:%s;base64,%s" % (mime, donnees),
                    })
                elif mime.startswith("audio/"):
                    textes.append("[Son renvoyé par l'outil : data:%s;base64,%s]" % (mime, donnees))
                continue
            uri = getattr(element, "uri", None)
            if isinstance(uri, str) and uri:
                textes.append("[Ressource : %s]" % uri)
        texte = "\n".join(textes)
        if not images:
            return texte
        enveloppe = {"images": images}
        if texte:
            enveloppe["text"] = texte
        return json.dumps(enveloppe, ensure_ascii=False)
    except Exception as e:
        logging.warning("Blocs MCP inattendus, repli texte vide : %s", e)
        return ""


def _enveloppe_medias_higgsfield(nom_outil, resultat):
    """Galerie et cartes pour les liens médias des outils Higgsfield (compte).

    Leurs réponses sont du texte (identifiant de travail, JSON avec
    rawUrl...). Quand ce texte contient des liens directs d'images ou de
    vidéos, on les expose en JSON {"images"/"videos"} pour l'affichage
    automatique, sans toucher au texte d'origine. Les autres serveurs
    sont renvoyés tels quels.
    """
    if not (nom_outil or "").startswith("higgsfield_"):
        return resultat
    if not isinstance(resultat, str) or not resultat:
        return resultat
    try:
        donnees = json.loads(resultat)
    except (json.JSONDecodeError, TypeError, ValueError):
        donnees = None
    if isinstance(donnees, dict) and (donnees.get("images") or donnees.get("videos")):
        return resultat
    images, videos = _medias_depuis_texte(resultat)
    if not images and not videos:
        return resultat
    enveloppe = {"text": resultat}
    if images:
        enveloppe["images"] = images
    if videos:
        enveloppe["videos"] = videos
    try:
        return json.dumps(enveloppe, ensure_ascii=False)
    except Exception:
        return resultat


async def _appeler_outil_async(url, nom_outil, arguments, headers=None):
    async with create_mcp_http_client(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resultat = await session.call_tool(nom_outil, arguments=arguments)
                texte = _texte_depuis_blocs_mcp(getattr(resultat, "content", None))
                return _enveloppe_medias_higgsfield(nom_outil, texte)


    return ""


def _raison_execution_code_masque(conversation_id):
    """Pourquoi le serveur d'exécution de code n'est pas proposé (None s'il l'est)."""
    if not os.environ.get("E2B_API_KEY"):
        return "la variable E2B_API_KEY est absente du serveur"
    if not conversation_id:
        return "aucune conversation identifiée pour cette demande"
    return None


def lister_outils_autorises_pour_agent(get_secret, user_id=None, agent_id=None, conversation_id=None, origine=None, contexte_video=False):
    """
    Se connecte a chaque serveur MCP du registre actif cote plateforme et
    retourne :
    - outils_pour_llm : la liste des outils au format attendu par l'API
      Groq (parametre tools=...)
    - table_routage : un dictionnaire {nom_outil: {"url":..., "headers":...}},
      pour pouvoir rappeler le bon serveur plus tard (avec la bonne
      authentification) sans aucun if/else en dur

    Catalogue BRUT, non filtre par outil_force -- c'est
    lister_tous_les_outils() (juste en dessous) qui applique ce filtre
    pour la reponse normale. Cette fonction existe separement depuis le
    28/07 pour que _router_outils() (core/main.py) puisse juger de la
    pertinence des outils reellement disponibles, sans dupliquer toute la
    logique de connexion aux serveurs MCP.

    Simplifie le 14/08 (demande Bourama) : Classinus est une seule IA, plus
    de systeme multi-agents/multi-createurs -- l'ancien filtrage par
    agents_serveurs/agents_outils_generation (par agent) a ete retire.
    Tous les serveurs et outils de generation disponibles cote plateforme
    (registre_outils_plateforme.disponible=True) sont proposes.

    `user_id` et `agent_id` sont transmis a chaque url_builder/
    headers_builder. La plupart les ignorent (cle API globale, ex:
    Tavily, Wolfram) ; certains outils "par utilisateur" (ex: Notion) en
    ont besoin pour aller chercher le bon token -- voir connexions/notion.py.
    `conversation_id` (08/09/2026, mode actif) est transmis en plus a
    url_builder SEULEMENT (jamais headers_builder, aucun besoin actuel) --
    voir registre_outils.py::_url_generation.
    Si un outil necessite un utilisateur et qu'aucun n'est connecte, il
    est ignore silencieusement : il n'apparait simplement pas dans la
    liste proposee au modele.

    Le catalogue d'outils (schema/description via list_tools()) est mis
    en cache 24h par serveur -- voir _lister_outils_serveur_avec_cache --
    au lieu d'un appel reseau a chaque message.
    """
    outils_pour_llm = []
    table_routage = {}

    noms_serveurs_actifs = _serveurs_disponibles()
    serveurs_actifs = [
        s for s in SERVEURS_MCP
        if s["nom"] == "generation"
        or (s["nom"] == "video" and (contexte_video or "video" in noms_serveurs_actifs))
        or (s["nom"] != "video" and s["nom"] in noms_serveurs_actifs)
    ]
    # L'exécution de code n'est proposée que si le serveur est configuré (clé E2B) et
    # rattachée à une conversation. Quand elle est masquée, le journal dit pourquoi.
    if "execution_code" in noms_serveurs_actifs:
        raison_masquage = _raison_execution_code_masque(conversation_id)
        if raison_masquage:
            logging.warning(f"Outil d'exécution de code non proposé : {raison_masquage}.")
            serveurs_actifs = [s for s in serveurs_actifs if s["nom"] != "execution_code"]

    # Montage vidéo sans vidéo jointe : le serveur rejoint le catalogue comme les autres
    # (le modèle le réclame via demander_outils, catégorie montage_video). Il a besoin
    # d'une conversation, qui porte son espace de travail ; avec une vidéo jointe
    # (contexte_video) le comportement historique reste inchangé.
    if not contexte_video and not conversation_id:
        serveurs_actifs = [s for s in serveurs_actifs if s["nom"] != "video"]

    logging.info(
        f"Serveurs MCP actifs : {noms_serveurs_actifs or '(aucun)'} "
        f"({len(serveurs_actifs)}/{len(SERVEURS_MCP)} du registre retenus)"
    )

    for serveur in serveurs_actifs:
        nom = serveur["nom"]
        try:
            if serveur.get("necessite_utilisateur") and not user_id:
                logging.info(f"MCP '{nom}' ignoré : nécessite un utilisateur connecté, aucun user_id fourni.")
                continue

            url = serveur["url_builder"](get_secret, user_id, agent_id, conversation_id)
            headers = serveur["headers_builder"](get_secret, user_id, agent_id) if "headers_builder" in serveur else None

            if serveur.get("necessite_utilisateur") and headers is None:
                logging.info(f"MCP '{nom}' ignoré : utilisateur {user_id} pas connecté à cet outil.")
                continue

            outils = _lister_outils_serveur_avec_cache(nom, url, headers, reveil_url=_url_reveil(serveur, url))

            outils_autorises = serveur.get("outils_autorises")
            if nom == "generation":
                outils_autorises = _outils_generation_disponibles()
                # gerer_document_bibliotheque (2026-08-01, étendu 20/08,
                # consolidé 26/08 -- ex consulter_bibliotheque +
                # consulter_bibliotheque_publique + 10 autres outils) :
                # bibliothèque PERSONNELLE et plugins publics de
                # l'utilisateur (voir "Mon espace"), scopés par user_id
                # côté core/bibliotheque_rag.py, pas par la liste
                # registre_outils_plateforme. Toujours proposé dès qu'un
                # utilisateur est connecté.
                if user_id and "gerer_document_bibliotheque" not in outils_autorises:
                    outils_autorises = [*outils_autorises, "gerer_document_bibliotheque"]
            if outils_autorises is not None:
                outils = [o for o in outils if o.name in outils_autorises]

            # Prefixe du serveur (vercel_, railway_, supabase_, higgsfield_) : le nom
            # expose au LLM est unique entre serveurs, le vrai nom est garde pour l'appel.
            prefixe = serveur.get("prefixe_outils") or ""

            noms_outils = [o.name for o in outils]
            logging.info(f"MCP '{nom}' -> {len(outils)} outil(s) listé(s) : {noms_outils}")
            for outil in outils:
                outils_pour_llm.append({
                    "type": "function",
                    "function": {
                        "name": f"{prefixe}{outil.name}",
                        "description": outil.description or "",
                        # CORRECTION (29/07) : mcp 2.0.0 a renomme inputSchema en
                        # input_schema sur l'objet Tool retourne par list_tools() --
                        # meme famille de bug que streamable_http_client (voir plus
                        # haut). Sans ce fix, chaque appel MCP plantait
                        # silencieusement (AttributeError attrape par le except plus
                        # bas) et la liste d'outils envoyee au LLM restait vide, quel
                        # que soit l'outil selectionne via le bouton Outils.
                        "parameters": schema_avec_libelle(_schema_avec_delai(
                            outil.input_schema,
                            delai_defaut=180 if nom == "execution_code" else None,
                            delai_max=180 if nom == "execution_code" else None,
                        )),
                    },
                })
                route = {"url": url, "headers": headers}
                url_reveil = _url_reveil(serveur, url)
                if url_reveil:
                    route["reveil_url"] = url_reveil
                if prefixe:
                    route["nom_reel"] = outil.name
                if _route_via_app_telephone(serveur, outil.name):
                    # 29/10/2026 : outils téléphone exécutés sur le PC de
                    # l'utilisateur via son appli (canal agent applicatif),
                    # jamais sur le cloud (voir _appeler_outil_telephone_via_app).
                    route["via_app_telephone"] = True
                    route["user_id"] = user_id
                table_routage[f"{prefixe}{outil.name}"] = route
        except Exception as e:
            logging.error(f"ERREUR MCP listing ({nom}): {e}")
            # 21/10/2026 (demande de Bourama) : le message ci-dessus reste vague quand
            # l'erreur vient d'un groupe d'erreurs (ex. "unhandled errors in a
            # TaskGroup"). On note ici la vraie cause de chaque sous-erreur.
            for detail in _details_erreur(e):
                logging.error(f"ERREUR MCP listing ({nom}) cause réelle : {detail}")

    # MCP personnalisés ajoutés par l'utilisateur connecté : le module gère
    # le catalogue par serveur, les jetons et un cache court séparé par compte.
    if user_id:
        try:
            from connexions.mcp_personnalises import lister_outils_pour_utilisateur
            for outil in lister_outils_pour_utilisateur(user_id):
                nom_expose = outil["nom"]
                if not nom_expose or nom_expose in table_routage:
                    continue
                outils_pour_llm.append({
                    "type": "function",
                    "function": {
                        "name": nom_expose,
                        "description": outil["description"],
                        "parameters": _schema_avec_delai(outil["parameters"]),
                    },
                })
                table_routage[nom_expose] = outil["route"]
        except Exception as e:
            logging.warning("Catalogue MCP personnalisé ignoré pour ce tour (%s).", type(e).__name__)

    # Origine de l'appareil (20/10/2026, demande de Bourama) : les outils d'écran qui n'existent pas
    # sur l'appareil utilisé ne sont jamais proposés. Origine inconnue : rien n'est retiré.
    from core.origine_appareil import filtrer_catalogue_par_origine
    return filtrer_catalogue_par_origine(outils_pour_llm, table_routage, origine)


def filtrer_catalogue_par_outil_force(outils_pour_llm, table_routage, outil_force=None):
    """
    Applique le filtre "bouton Outils" (voir plus bas) à un catalogue déjà
    récupéré, sans repasser par lister_outils_autorises_pour_agent().

    Extrait de lister_tous_les_outils() le 11/09/2026 (demande Bourama :
    "tout ce qui peut se faire une fois, pas à chaque message") -- avant
    ce fix, main.py appelait lister_tous_les_outils() PUIS
    _preparer_demander_outils(), qui rappelait chacun de son côté
    lister_outils_autorises_pour_agent() séparément pour le même message :
    le catalogue (déjà en cache 24h) était bien récupéré une seule fois au
    sens réseau, mais l'accès de l'utilisateur à chaque service externe
    nécessitant un compte connecté (Notion, Google Drive -- voir
    obtenir_token_valide) était revérifié EN BASE deux fois par message au
    lieu d'une. main.py appelle maintenant lister_outils_autorises_pour_agent()
    une seule fois et réutilise son résultat ici pour construire
    outils_mcp, au lieu de le redemander.

    Mode "bouton Outils" (2026-07-25, GLOBAL -- décision définitive de
    Bourama, initialement testé sur l'agent nucleos seul puis étendu à
    tous, puis passé à la MULTI-sélection le 26/07). Objectif : réduire
    la conso token (schéma de ~20 outils envoyé à chaque message,
    identifié comme le plus gros poste). AUCUN outil envoyé par défaut,
    sur AUCUN agent, sauf sélection explicite d'un ou plusieurs outils
    par le frontend (bouton Outils, voir BarreDeSaisie.tsx). Effet de
    bord assumé et voulu : l'IA perd son autonomie d'appel d'outil
    implicite partout (ex. gerer_fichier_conversation automatique quand on
    redemande un fichier envoyé, tavily_search automatique sur une
    question d'actualité) tant que rien n'est sélectionné.
    """
    outils_forces = set(outil_force or [])
    if outils_forces:
        outils_pour_llm = [o for o in outils_pour_llm if o["function"]["name"] in outils_forces]
        table_routage = {k: v for k, v in table_routage.items() if k in outils_forces}
    else:
        outils_pour_llm = []
        table_routage = {}

    logging.info(f"Outils envoyés au LLM ce tour-ci : {[o['function']['name'] for o in outils_pour_llm]}")
    return outils_pour_llm, table_routage


def lister_tous_les_outils(get_secret, user_id=None, agent_id=None, outil_force=None, conversation_id=None):
    """
    Reprend lister_outils_autorises_pour_agent() (catalogue brut pour cet
    agent) puis applique le filtre "bouton Outils" (voir
    filtrer_catalogue_par_outil_force ci-dessus). Signature et
    comportement inchangés pour tous les appelants existants (nouveau
    paramètre optionnel conversation_id, 08/09/2026, mode actif).

    A conserver pour les appelants qui n'ont pas déjà le catalogue brut
    sous la main (voir core/main.py, chemin routeur automatique) --
    quand il est déjà disponible, préférer appeler
    filtrer_catalogue_par_outil_force() directement pour éviter un
    second appel à lister_outils_autorises_pour_agent().
    """
    outils_pour_llm, table_routage = lister_outils_autorises_pour_agent(get_secret, user_id, agent_id, conversation_id)
    return filtrer_catalogue_par_outil_force(outils_pour_llm, table_routage, outil_force)


def _message_erreur_technique_outil(nom_outil: str) -> str:
    """
    Ajoute le 24/09/2026, Bourama : le message precedent ("Erreur lors de
    l'appel a l'outil X.") ne disait rien au modele, qui inventait alors
    une cause (souvent "le telephone n'est pas ouvert"). Dit clairement que
    la cause est inconnue et interdit de l'attribuer a l'app ou au telephone.
    """
    return (
        f"Erreur technique interne pendant l'appel à l'outil '{nom_outil}'. "
        "La cause est inconnue : ne l'attribue pas au téléphone, à l'app ou à "
        "l'utilisateur. Dis simplement qu'une erreur technique est survenue et "
        "propose de réessayer."
    )


# 29/10/2026 (Bourama : l'IA appelle, l'outil doit joindre le téléphone) :
# type d'action système exécuté par l'appli PC (voir lib/canalAgentApplicatif.ts
# et le plugin RelaisPc côté frontend). parametres = {"nom": nom de l'outil,
# "args": arguments}. L'appli répond {"texte": ...} ou {"erreur": ...}.
TYPE_ACTION_OUTIL_TELEPHONE = "outil_telephone"


def _route_via_app_telephone(serveur, nom_outil_reel):
    """Vrai si l'outil passe par l'appli PC (relais local).

    Serveur marqué via_app_telephone, SAUF les outils qui ne touchent pas
    au téléphone (outils_serveur_seul du registre : ping, sondes), qui
    restent exécutés sur le cloud même sans appli connectée.
    """
    if not serveur.get("via_app_telephone"):
        return False
    return nom_outil_reel not in (serveur.get("outils_serveur_seul") or [])

MESSAGE_TELEPHONE_SANS_APP = (
    "Téléphone injoignable : ouvre l'appli Classinus sur ton PC (connectée "
    "à ce compte) puis branche ton téléphone en USB avec le débogage USB "
    "activé, et réessaie."
)
MESSAGE_TELEPHONE_SANS_REPONSE = (
    "Téléphone injoignable : l'appli PC n'a pas répondu. Mets à jour "
    "Classinus PC vers la dernière version, ouvre-la, puis réessaie."
)


async def _appeler_telephone_via_app_async(nom_reel, arguments, user_id, delai):
    """Envoie un outil téléphone à l'appli PC et rend le texte du relais."""
    from canal_agent_applicatif import a_app_telephone_connectee, demander_action_systeme
    if not await a_app_telephone_connectee(user_id):
        return MESSAGE_TELEPHONE_SANS_APP
    reponse = await demander_action_systeme(
        user_id,
        TYPE_ACTION_OUTIL_TELEPHONE,
        {"nom": nom_reel, "args": arguments},
        delai_abandon_secondes=max(delai - 2, 5),
    )
    if reponse is None:
        return MESSAGE_TELEPHONE_SANS_REPONSE
    if isinstance(reponse, dict):
        erreur = reponse.get("erreur")
        if isinstance(erreur, str) and erreur:
            return f"Erreur : {erreur}"
        texte = reponse.get("texte")
        if isinstance(texte, str):
            return texte
    return str(reponse)


def _appeler_outil_telephone_via_app(nom_outil, arguments, route, delai, arret):
    """Exécute un outil téléphone via l'appli PC de l'utilisateur (relais local).

    Même contrat que appeler_outil (délai, bouton Arrêter, messages), mais
    l'exécution passe par le canal agent applicatif au lieu du cloud MCP :
    seul le relais local voit le téléphone branché en USB.
    """
    nom_reel = route.get("nom_reel", nom_outil)
    user_id = route.get("user_id") or ""
    if not user_id:
        logging.error(f"Outil téléphone '{nom_outil}' sans user_id dans sa route.")
        return "Erreur : impossible d'identifier l'utilisateur."
    try:
        appel = _appeler_telephone_via_app_async(nom_reel, arguments, user_id, delai)
        resultat = asyncio.run(_appeler_avec_delai_et_arret(appel, delai, arret))
        logging.info(f"Résultat outil '{nom_outil}' : {len(resultat or '')} caractères")
        return resultat
    except _AppelAnnule:
        logging.info(f"Appel à {nom_outil} interrompu par le bouton Arrêter")
        return "Action annulée par l'utilisateur : l'appel a été interrompu, le résultat est inconnu."
    except TimeoutError:
        logging.warning(f"Délai dépassé ({delai} s) pour l'outil {nom_outil}")
        return (
            f"Délai dépassé : {nom_outil} n'a pas répondu en {delai} s. L'action a peut-être quand même "
            f"abouti côté service : vérifie son état avant de la relancer. Si l'outil est connu pour être "
            f"long, tu peux le relancer avec {PARAMETRE_DELAI_OUTIL} plus grand (maximum {DELAI_OUTIL_MAX_SECONDES} s)."
        )
    except Exception as e:
        logging.error(f"ERREUR pont téléphone {nom_outil}: {e}", exc_info=True)
        return _message_erreur_technique_outil(nom_outil)


def appeler_outil(nom_outil, arguments, table_routage, arret=None):
    """
    Execute un outil par son nom, quel que soit le serveur MCP qui
    l'expose. Le routage (URL + headers) se fait automatiquement via
    table_routage, construite par lister_tous_les_outils().

    22/10/2026 : l'appel est borné par un délai (60 s par défaut, que le modèle peut
    allonger avec delai_max_secondes) et s'interrompt dès que le bouton Arrêter est
    pressé (`arret`). Avant, il pouvait attendre indéfiniment.
    """
    arguments = dict(arguments or {})
    delai_demande = arguments.pop(PARAMETRE_DELAI_OUTIL, None)
    # Phrase de la timeline (23/10/2026) : réservée à l'affichage, jamais transmise à l'outil.
    arguments.pop(PARAMETRE_LIBELLE_OUTIL, None)
    if nom_outil == "gerer_execution_code":
        # La création ou la reprise d'un sandbox peut dépasser 60 secondes.
        # Ce délai transporte l'appel MCP, sans élargir la durée d'une commande.
        delai = 180
    else:
        delai = _delai_demande(delai_demande)
    if nom_outil == "gerer_execution_code":
        # Le code source, les commandes et le contenu des fichiers des étudiants
        # ne doivent jamais se retrouver dans les journaux d'application.
        arguments_journal = {
            "action": arguments.get("action"),
            "language": arguments.get("language"),
        }
        for champ in ("code", "command", "content"):
            valeur = arguments.get(champ)
            if isinstance(valeur, str):
                arguments_journal[f"{champ}_chars"] = len(valeur)
    else:
        arguments_journal = arguments
    logging.info(f"Appel outil demandé par le LLM : {nom_outil}({arguments_journal})")
    route = table_routage.get(nom_outil)
    if not route:
        logging.error(f"Outil '{nom_outil}' demandé par le LLM mais absent de la table de routage.")
        return f"Erreur : outil '{nom_outil}' inconnu."
    if route.get("via_app_telephone"):
        # 29/10/2026 : outils téléphone exécutés sur le PC de
        # l'utilisateur (relais local, seul à voir le téléphone).
        return _appeler_outil_telephone_via_app(nom_outil, arguments, route, delai, arret)
    # 31/10/2026 : les outils executes cote serveur (sondes sans telephone)
    # reveillent d'abord un service gratuit endormi, au plus une fois par
    # fenetre -- jamais avant les outils telephone, executes sur le PC.
    _reveiller_si_recent_non_tente(route.get("reveil_url"))
    try:
        if route.get("custom_mcp"):
            # Serveur ajouté par l'utilisateur : adresse et jeton relus à l'instant de l'appel,
            # connexion sans redirection et sur une adresse publique vérifiée.
            from connexions.mcp_personnalises import preparer_appel_personnalise, appeler_outil_personnalise_async
            try:
                url_appel, headers_appel = preparer_appel_personnalise(route)
            except ValueError as e:
                return f"Erreur : {e}"
            appel = appeler_outil_personnalise_async(url_appel, route.get("nom_reel", nom_outil), arguments, headers_appel)
        else:
            appel = _appeler_outil_async(route["url"], route.get("nom_reel", nom_outil), arguments, route.get("headers"))
        resultat = asyncio.run(_appeler_avec_delai_et_arret(appel, delai, arret))
        logging.info(f"Résultat outil '{nom_outil}' : {len(resultat or '')} caractères")
        return resultat
    except _AppelAnnule:
        logging.info(f"Appel à {nom_outil} interrompu par le bouton Arrêter")
        return "Action annulée par l'utilisateur : l'appel a été interrompu, le résultat est inconnu."
    except TimeoutError:
        logging.warning(f"Délai dépassé ({delai} s) pour l'outil {nom_outil}")
        return (
            f"Délai dépassé : {nom_outil} n'a pas répondu en {delai} s. L'action a peut-être quand même "
            f"abouti côté service : vérifie son état avant de la relancer. Si l'outil est connu pour être "
            f"long, tu peux le relancer avec {PARAMETRE_DELAI_OUTIL} plus grand (maximum {DELAI_OUTIL_MAX_SECONDES} s)."
        )
    except BaseExceptionGroup as eg:
        # Correctif 13/09/2026, Bourama : "unhandled errors in a TaskGroup
        # (N sub-exception(s))" est le message par defaut d'un
        # ExceptionGroup/TaskGroup (anyio, utilise par le client MCP
        # streamable-http) -- str(eg) seul ne montre JAMAIS la vraie cause
        # nichee dedans, seulement ce resume vide. On deplie ici chaque
        # sous-exception (recursivement, une ExceptionGroup peut en
        # contenir d'autres) pour enfin voir le vrai type/message, avec
        # exc_info pour la trace complete de l'ExceptionGroup elle-meme.
        def _aplatir(exc):
            if isinstance(exc, BaseExceptionGroup):
                for sous in exc.exceptions:
                    yield from _aplatir(sous)
            else:
                yield exc
        detail = "; ".join(f"{type(sub).__name__}: {sub}" for sub in _aplatir(eg))
        if nom_outil == "gerer_execution_code":
            # Les exceptions de commande peuvent contenir des fragments de code ou de sortie.
            logging.error("ERREUR MCP exécution de code (TaskGroup) : %s", type(eg).__name__)
        else:
            logging.error(f"ERREUR MCP appel a {nom_outil} (TaskGroup) : {detail}", exc_info=True)
        return _message_erreur_technique_outil(nom_outil)
    except Exception as e:
        if nom_outil == "gerer_execution_code":
            logging.error("ERREUR MCP exécution de code : %s", type(e).__name__)
        else:
            logging.error(f"ERREUR MCP appel a {nom_outil}: {e}", exc_info=True)
        return _message_erreur_technique_outil(nom_outil)
