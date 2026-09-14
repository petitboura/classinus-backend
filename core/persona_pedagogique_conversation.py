"""Mode pédagogique actif par conversation (item 9 des specs indépendantes
ScholarFlow AI, volet étudiant, 12/09/2026, demande Bourama) : Socratique,
Professeur, Tuteur ou Examinateur (voir MODES_PEDAGOGIQUES dans
core/profils_agents.py, item 1). Un étudiant choisit ce mode explicitement
(bouton ou raccourci "/", item 8 -- frontend, pas fait ici), jamais l'IA
elle-même en cours de conversation.

ATTENTION NOM (voir aussi la migration) : ce module est DISTINCT de
core/mode_actif_conversation.py, qui gère le rattachement enseignant/code
de classe actif sur une conversation -- un concept sans rapport. Les deux
noms se ressemblent volontairement peu pour éviter toute confusion :
persona_pedagogique_conversation.py ici, mode_actif_conversation.py là-bas.
Ne jamais fusionner ni faire écrire ce module dans conversation_mode_actif.

Table dédiée conversation_persona_pedagogique (migration 2026_09_12),
même schéma de cache court que core/mode_actif_conversation.py.

PAS ENCORE BRANCHÉ (hors scope de cet item, voir specs-independantes.md) :
la lecture du mode actif n'est pas injectée dans _construire_system_prompt.
Ce module ne fait que stocker/lire le choix -- le branchement dans le
prompt réel est une jonction restante, à faire une fois ce module et le
texte des modes (item 1) réunis.
"""
import logging
import time

from api.auth import supabase

# Cache court, même principe et même durée que core/mode_actif_conversation.py
# (demande Bourama : pas de lecture base à chaque message si évitable).
# Invalidé immédiatement dès qu'un changement est écrit (voir
# definir_persona_pedagogique), TTL de secours sinon. LIMITE CONNUE (même
# limite que mode_actif_conversation.py) : cache en mémoire par process --
# si Railway fait tourner plusieurs instances, un changement fait via une
# instance n'invalide pas le cache des autres avant l'expiration du TTL.
_DUREE_CACHE_SECONDES = 5 * 60
_cache_persona = {}  # conversation_id -> {"valeur": str | None, "expire_a": ts}

PERSONAS_VALIDES = ("socratique", "professeur", "tuteur", "examinateur")


def obtenir_persona_pedagogique(conversation_id: str, user_id: str) -> str | None:
    """Mode pédagogique actuellement actif pour cette conversation, ou
    None si l'étudiant n'a encore rien choisi. Pas de valeur par défaut
    implicite ici -- décision volontairement pas prise dans ce module
    (voir commentaire "DÉCISION EN ATTENTE" dans core/profils_agents.py,
    item 1) : à trancher avec Bourama avant le branchement dans le
    prompt, pas à deviner ici."""
    maintenant = time.time()
    entree = _cache_persona.get(conversation_id)
    if entree is not None and entree["expire_a"] > maintenant:
        return entree["valeur"]
    try:
        res = (
            supabase.table("conversation_persona_pedagogique")
            .select("persona")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture persona pédagogique {conversation_id}) : {e}")
        return None
    valeur = res.data["persona"] if (res and res.data) else None
    _cache_persona[conversation_id] = {"valeur": valeur, "expire_a": maintenant + _DUREE_CACHE_SECONDES}
    return valeur


def definir_persona_pedagogique(conversation_id: str, user_id: str, persona: str | None) -> dict | None:
    """Fixe (ou efface, si persona est None) le mode pédagogique actif de
    cette conversation pour cet étudiant. Upsert sur conversation_id seul
    (clé primaire) -- une conversation n'appartient qu'à un seul
    utilisateur, jamais recréée pour un autre. None si persona est fourni
    mais ne fait pas partie de PERSONAS_VALIDES (jamais d'écriture d'une
    valeur invalide en base)."""
    if persona is not None and persona not in PERSONAS_VALIDES:
        return None
    ligne = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "persona": persona,
    }
    try:
        res = (
            supabase.table("conversation_persona_pedagogique")
            .upsert(ligne, on_conflict="conversation_id")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (définition persona pédagogique {conversation_id}) : {e}")
        raise
    # Cache invalidé immédiatement : le prochain message de cette
    # conversation doit voir le nouveau mode tout de suite, jamais
    # attendre l'expiration du cache court d'obtenir_persona_pedagogique.
    _cache_persona.pop(conversation_id, None)
    return res.data[0] if res.data else ligne
