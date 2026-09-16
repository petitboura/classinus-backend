"""Guide interactif actif par conversation (etape 2 du chantier "guide de
decouverte", voir specs-guide-decouverte.md dans clovis-frontend, demande
Bourama, 16/09/2026). Un utilisateur active ce mode explicitement (bouton
flottant ou entree du menu "+" du chat, etapes 4 et 5 -- frontend, pas
fait ici), jamais l'IA elle-meme en cours de conversation.

ATTENTION NOM (voir aussi la migration) : ce module est DISTINCT de
core/mode_actif_conversation.py (rattachement enseignant/code de classe)
et de core/persona_pedagogique_conversation.py (mode Socratique/
Professeur/Tuteur/Examinateur) -- deux concepts sans rapport. Ne jamais
fusionner ni faire ecrire ce module dans une de ces deux tables.

Table dediee conversation_guide_actif (migration 2026_09_16b), meme
schema de cache court que core/persona_pedagogique_conversation.py.

BRANCHE le 16/09/2026 (etape 3) : obtenir_guide_actif est appele dans
core/main.py et passe a _construire_system_prompt
(core/construction_system_prompt.py), qui injecte
construire_instruction_guide(obtenir_sections_guide()) (core/
profils_agents.py) quand ce mode est actif. Meme patron que
persona_pedagogique_conversation.py, branche le 14/09/2026 apres sa
creation le 12/09/2026.
"""
import logging
import time

from api.auth import supabase

# Cache court, meme principe et meme duree que
# core/persona_pedagogique_conversation.py (demande Bourama : pas de
# lecture base a chaque message si evitable). Invalide immediatement des
# qu'un changement est ecrit (voir definir_guide_actif), TTL de secours
# sinon. LIMITE CONNUE (meme limite que les autres caches courts de ce
# type) : cache en memoire par process -- si Railway fait tourner
# plusieurs instances, un changement fait via une instance n'invalide pas
# le cache des autres avant l'expiration du TTL.
_DUREE_CACHE_SECONDES = 5 * 60
_cache_guide = {}  # conversation_id -> {"valeur": bool, "expire_a": ts}

# Cache separe pour le referentiel des sections (table guide_sections,
# etape 1) : contenu global, pas par conversation, meme duree de cache
# que le reste de ce module.
_cache_sections_guide = {}  # "valeur" -> {"valeur": list[dict], "expire_a": ts}


def obtenir_sections_guide() -> list:
    """Referentiel des sections du guide (table guide_sections, etape 1),
    trie par ordre croissant. Utilise pour construire l'instruction du
    mode guide (construire_instruction_guide, core/profils_agents.py) --
    contenu quasi statique mais modifiable sans redeploiement (demande
    Bourama), donc jamais recopie en dur dans le code. Renvoie une liste
    vide en cas d'erreur, jamais une exception propagee (meme principe
    defensif qu'obtenir_guide_actif ci-dessous)."""
    maintenant = time.time()
    entree = _cache_sections_guide.get("valeur")
    if entree is not None and entree["expire_a"] > maintenant:
        return entree["valeur"]
    try:
        res = (
            supabase.table("guide_sections")
            .select("nom_article, libelle_utilisateur, accroche_courte, ordre")
            .order("ordre")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture guide_sections) : {e}")
        return []
    valeur = res.data or []
    _cache_sections_guide["valeur"] = {"valeur": valeur, "expire_a": maintenant + _DUREE_CACHE_SECONDES}
    return valeur


def obtenir_guide_actif(conversation_id: str, user_id: str) -> bool:
    """Le guide interactif est-il actif sur cette conversation ? False
    tant que l'utilisateur n'a rien active explicitement (pas de valeur
    par defaut implicite a true)."""
    maintenant = time.time()
    entree = _cache_guide.get(conversation_id)
    if entree is not None and entree["expire_a"] > maintenant:
        return entree["valeur"]
    try:
        res = (
            supabase.table("conversation_guide_actif")
            .select("actif")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture guide actif {conversation_id}) : {e}")
        return False
    valeur = bool(res.data["actif"]) if (res and res.data) else False
    _cache_guide[conversation_id] = {"valeur": valeur, "expire_a": maintenant + _DUREE_CACHE_SECONDES}
    return valeur


def definir_guide_actif(conversation_id: str, user_id: str, actif: bool) -> dict:
    """Active ou desactive le guide interactif sur cette conversation pour
    cet utilisateur. Upsert sur conversation_id seul (cle primaire) -- une
    conversation n'appartient qu'a un seul utilisateur, jamais recreee
    pour un autre."""
    ligne = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "actif": actif,
    }
    try:
        res = (
            supabase.table("conversation_guide_actif")
            .upsert(ligne, on_conflict="conversation_id")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (definition guide actif {conversation_id}) : {e}")
        raise
    # Cache invalide immediatement : le prochain message de cette
    # conversation doit voir le nouvel etat tout de suite, jamais attendre
    # l'expiration du cache court d'obtenir_guide_actif.
    _cache_guide.pop(conversation_id, None)
    return res.data[0] if res.data else ligne
