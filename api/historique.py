"""
Étape ajoutée le 2026-07-13 (Bourama : "conversation récente par membre de
la plateforme qui se conserve pour chaque agent utilisée, dans le tableau
de bord, à gauche comme toute IA en fait").

Lit `historique_conversations` (voir la migration du même nom) : une table
PERMANENTE, jamais purgée, distincte de `conversations` (mémoire de
travail de l'IA, résumée puis supprimée -- voir core/main.py). Ce fichier
ne fait qu'AFFICHER l'historique ; il n'écrit jamais dedans (l'écriture se
fait uniquement depuis core/main.py, au moment de chaque échange).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import utilisateur_courant, supabase
from core.erreurs import erreur_api

router = APIRouter(prefix="/api/historique", tags=["historique"])

# Corrigé le 2026-09-14 (Bourama : "les historiques ne s'affichent pas tout,
# y a-t-il un plafond") -- l'API Supabase (PostgREST) plafonne chaque
# requête à 1000 lignes par défaut (réglage "Max Rows" du projet, jamais
# modifié). Aucune des requêtes de ce fichier ne posait de .limit()
# explicite : au-delà de 1000 lignes pour un même utilisateur, les plus
# récentes (ou plus anciennes, selon le tri) étaient silencieusement
# coupées par Supabase, sans erreur -- l'historique semblait juste
# incomplet. TAILLE_PAGE_SUPABASE pagine nous-mêmes par blocs de 1000
# jusqu'à épuisement, pour ne plus jamais dépendre de ce plafond, quel que
# soit le volume de messages accumulés.
TAILLE_PAGE_SUPABASE = 1000


def _recuperer_toutes_les_lignes(construire_requete):
    """
    Exécute `construire_requete()` (une fonction qui RECONSTRUIT la requête
    à chaque appel -- un query builder Supabase déjà exécuté ne peut pas
    être réutilisé) en lui appliquant `.range()` par blocs de
    TAILLE_PAGE_SUPABASE, jusqu'à ce qu'un bloc renvoie moins de lignes que
    la taille de page (signe qu'on a atteint la fin). Renvoie la liste
    complète, sans jamais dépendre du plafond par défaut de l'API.
    """
    toutes_les_lignes: list = []
    debut = 0
    while True:
        page = (
            construire_requete()
            .range(debut, debut + TAILLE_PAGE_SUPABASE - 1)
            .execute()
        ).data or []
        toutes_les_lignes.extend(page)
        if len(page) < TAILLE_PAGE_SUPABASE:
            break
        debut += TAILLE_PAGE_SUPABASE
    return toutes_les_lignes


class ConversationResume(BaseModel):
    agent_id: str
    agent_nom: str
    agent_icone: str = "🤖"
    dernier_message: str
    dernier_message_role: str
    derniere_activite: str


@router.get("", response_model=List[ConversationResume])
def lister_conversations(utilisateur=Depends(utilisateur_courant)):
    """
    Liste des agents avec qui CET utilisateur a déjà échangé, le plus
    récemment actif en premier -- pour la barre latérale façon ChatGPT
    demandée par Bourama. Un agent = une "conversation" ; le détail
    message par message est sur GET /api/historique/{agent_id}.

    Paginé via _recuperer_toutes_les_lignes (voir plus haut) pour ne pas
    dépendre du plafond par défaut de l'API Supabase.
    """
    try:
        lignes = _recuperer_toutes_les_lignes(
            lambda: supabase.table("historique_conversations")
            .select("agent_id, role, content, created_at")
            .eq("user_id", utilisateur.id)
            .order("created_at", desc=True)
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lister_conversations, user_id={utilisateur.id}) : {e}")
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_L_HISTORIQUE")

    # Un seul aller-retour supabase pour tous les messages (déjà trié du
    # plus récent au plus ancien), puis on garde juste la PREMIÈRE ligne
    # rencontrée par agent_id -- c'est mécaniquement la plus récente,
    # grâce au tri ci-dessus. Évite une requête groupée par agent plus
    # coûteuse pour un gain minime ici.
    resume_par_agent = {}
    for ligne in lignes:
        aid = ligne["agent_id"]
        if aid not in resume_par_agent:
            resume_par_agent[aid] = ligne

    if not resume_par_agent:
        return []

    try:
        agents_res = (
            supabase.table("agents")
            .select("id, nom, ui_config")
            .in_("id", list(resume_par_agent.keys()))
            .execute()
        )
        agents_par_id = {a["id"]: a for a in (agents_res.data or [])}
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lister_conversations, jointure agents) : {e}")
        agents_par_id = {}

    resultat = []
    for agent_id, ligne in resume_par_agent.items():
        agent = agents_par_id.get(agent_id)
        # Agent supprimé depuis (actif=false n'est PAS filtré ici : voir
        # docstring — on veut quand même montrer l'historique d'un agent
        # désactivé, juste pas un agent qui n'existe plus du tout en base)
        # mais un id qui ne matche plus aucune ligne dans `agents` est
        # silencieusement ignoré plutôt que de planter toute la liste.
        if not agent:
            continue
        resultat.append(
            ConversationResume(
                agent_id=agent_id,
                agent_nom=agent["nom"],
                agent_icone=(agent.get("ui_config") or {}).get("icone_page", "🤖"),
                dernier_message=ligne["content"],
                dernier_message_role=ligne["role"],
                derniere_activite=ligne["created_at"],
            )
        )

    resultat.sort(key=lambda r: r.derniere_activite, reverse=True)
    return resultat


class MessageHistorique(BaseModel):
    role: str
    content: str
    created_at: str
    meta: Optional[dict] = None
    # Versions navigables (20/09/2026, demande Bourama) : id propre de
    # CETTE ligne et id du message precedent dans sa branche (None pour
    # le tout premier message d'une conversation), voir la migration
    # 2026_09_20c_versions_navigables_historique.sql. Plusieurs lignes
    # peuvent partager le meme parent_id : ce sont des versions
    # alternatives a ce point precis, reconstruit en arbre cote
    # frontend (ChatIA.tsx), cette route renvoie TOUJOURS TOUTES les
    # lignes de la conversation demandee, pas seulement le chemin actif.
    id: Optional[int] = None
    parent_id: Optional[int] = None


@router.get("/{agent_id}", response_model=List[MessageHistorique])
def obtenir_historique_agent(agent_id: str, utilisateur=Depends(utilisateur_courant)):
    """
    Historique complet (jamais purgé) des échanges entre CET utilisateur
    et CET agent, du plus ancien au plus récent -- pour rouvrir/afficher
    une conversation passée en entier depuis la barre latérale.

    Pas de vérification "cet agent existe/est actif" ici : filtrer par
    user_id suffit à garantir qu'on ne lit jamais l'historique de
    quelqu'un d'autre (aucune donnée du payload/de l'URL n'influence QUEL
    user_id est utilisé, uniquement le token vérifié par
    utilisateur_courant).
    """
    try:
        lignes = _recuperer_toutes_les_lignes(
            lambda: supabase.table("historique_conversations")
            .select("id, parent_id, role, content, created_at, meta")
            .eq("user_id", utilisateur.id)
            .eq("agent_id", agent_id)
            .order("created_at")
        )
    except Exception as e:
        logging.error(
            f"ERREUR SUPABASE (obtenir_historique_agent, user_id={utilisateur.id}, "
            f"agent_id={agent_id}) : {e}"
        )
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_L_HISTORIQUE")

    return [MessageHistorique(**ligne) for ligne in lignes]


# --- Fils de discussion (par conversation_id), ajouté le 2026-07-16 ------
# Bourama : reproduire dans le chat Next.js la sidebar "Historique" du chat
# Streamlit (l'ancienne interface Streamlit), qui liste les fils de discussion
# DISTINCTS avec un même agent (pas juste "un agent = une conversation",
# comme le fait lister_conversations ci-dessus pour le tableau de bord).
# Même logique de regroupement que _lister_conversations_passees côté
# Streamlit : titre = début du premier message utilisateur du fil (pas de
# titre généré par IA, décision de Bourama : trop coûteux pour ce que ça
# apporte), lignes sans conversation_id (NULL, d'avant cette fonctionnalité)
# regroupées sous un fil "legacy" plutôt qu'ignorées.
LONGUEUR_MAX_TITRE = 42


class FilConversation(BaseModel):
    conversation_id: Optional[str]
    titre: str
    derniere_activite: str


@router.get("/{agent_id}/conversations", response_model=List[FilConversation])
def lister_fils_conversation(agent_id: str, utilisateur=Depends(utilisateur_courant)):
    """
    Liste des fils de discussion distincts entre CET utilisateur et CET
    agent, le plus récemment actif en premier -- pour la section
    "Historique" de la sidebar du chat (un agent peut avoir plusieurs
    conversations séparées, contrairement à GET /api/historique qui n'en
    garde qu'une par agent pour le tableau de bord).
    """
    try:
        lignes = _recuperer_toutes_les_lignes(
            lambda: supabase.table("historique_conversations")
            .select("conversation_id, role, content, created_at")
            .eq("user_id", utilisateur.id)
            .eq("agent_id", agent_id)
            .order("created_at")
        )
    except Exception as e:
        logging.error(
            f"ERREUR SUPABASE (lister_fils_conversation, user_id={utilisateur.id}, "
            f"agent_id={agent_id}) : {e}"
        )
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_L_HISTORIQUE")

    fils: dict = {}
    for ligne in lignes:
        cle = ligne["conversation_id"] or "legacy"
        if cle not in fils:
            fils[cle] = {
                "conversation_id": ligne["conversation_id"],
                "premier_message_user": None,
                "derniere_activite": ligne["created_at"],
            }
        if ligne["role"] == "user" and fils[cle]["premier_message_user"] is None:
            fils[cle]["premier_message_user"] = ligne["content"]
        fils[cle]["derniere_activite"] = ligne["created_at"]

    resultat = []
    for cle, fil in fils.items():
        if cle == "legacy":
            titre = "Avant l'historique par conversation"
        else:
            titre = (fil["premier_message_user"] or "Conversation sans titre").strip()
            if len(titre) > LONGUEUR_MAX_TITRE:
                titre = titre[:LONGUEUR_MAX_TITRE].rstrip() + "…"
        resultat.append(
            FilConversation(
                conversation_id=fil["conversation_id"],
                titre=titre,
                derniere_activite=fil["derniere_activite"],
            )
        )

    resultat.sort(key=lambda f: f.derniere_activite, reverse=True)
    return resultat


@router.get("/{agent_id}/conversations/{conversation_id}", response_model=List[MessageHistorique])
def obtenir_fil_conversation(agent_id: str, conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    """
    Contenu complet d'UN fil précis (clic sur une entrée de la liste
    ci-dessus). `conversation_id` vaut littéralement "legacy" pour recharger
    le fil des lignes d'avant cette fonctionnalité (conversation_id NULL en
    base) -- convention interne à cette route, jamais stockée telle quelle.

    Versions navigables (20/09/2026) : renvoie TOUTES les lignes de ce
    fil, y compris toutes les versions alternatives (plusieurs lignes
    peuvent partager le même parent_id), pas seulement le chemin
    actuellement affiché. C'est ChatIA.tsx côté frontend qui reconstruit
    l'arbre à partir de id/parent_id et choisit quoi afficher par défaut.
    """
    def _construire_requete():
        requete = (
            supabase.table("historique_conversations")
            .select("id, parent_id, role, content, created_at, meta")
            .eq("user_id", utilisateur.id)
            .eq("agent_id", agent_id)
        )
        if conversation_id == "legacy":
            requete = requete.is_("conversation_id", "null")
        else:
            requete = requete.eq("conversation_id", conversation_id)
        return requete.order("created_at")

    try:
        lignes = _recuperer_toutes_les_lignes(_construire_requete)
    except Exception as e:
        logging.error(
            f"ERREUR SUPABASE (obtenir_fil_conversation, user_id={utilisateur.id}, "
            f"agent_id={agent_id}, conversation_id={conversation_id}) : {e}"
        )
        raise erreur_api(500, "IMPOSSIBLE_DE_CHARGER_CETTE_CONVERSATION")

    return [MessageHistorique(**ligne) for ligne in lignes]
