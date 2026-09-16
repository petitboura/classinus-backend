"""Mode source actif par conversation (chantier "mode source", voir
contexte-mode-source-clovis.md, demande Bourama, 16/09/2026) : Aucun,
Recherche ou Sur pieces, controle QUELLES SOURCES Clovis a le droit
d'utiliser pour repondre. Un eleve choisit ce mode explicitement (meme
bouton que le persona pedagogique, groupe separe), jamais l'IA elle-meme
en cours de conversation.

ATTENTION NOM (voir aussi la migration) : ce module est DISTINCT de
core/mode_actif_conversation.py (rattachement enseignant/code de classe)
et de core/persona_pedagogique_conversation.py (style d'enseignement de
Clovis). Trois concepts independants qui cohabitent sur la meme
conversation. Ne jamais fusionner ni faire ecrire ce module dans une de
ces deux tables.

Table dediee conversation_mode_source (migration 2026_09_16c), meme
schema de cache court que core/persona_pedagogique_conversation.py.

"Aucun" (comportement actuel, rien ne change) correspond a mode_source
valant None : aucune ligne en base, ou une ligne avec mode_source=None
si l'eleve revient explicitement sur "Aucun" apres avoir choisi un mode
(meme upsert que persona_pedagogique_conversation.py).
"""
import logging
import time

from api.auth import supabase

# Cache court, meme principe et meme duree que
# core/persona_pedagogique_conversation.py (demande Bourama : pas de
# lecture base a chaque message si evitable). Invalide immediatement des
# qu'un changement est ecrit (voir definir_mode_source), TTL de secours
# sinon. LIMITE CONNUE (meme limite que les autres caches courts de ce
# type) : cache en memoire par process. Si Railway fait tourner
# plusieurs instances, un changement fait via une instance n'invalide pas
# le cache des autres avant l'expiration du TTL.
_DUREE_CACHE_SECONDES = 5 * 60
_cache_mode_source = {}  # conversation_id -> {"valeur": str | None, "expire_a": ts}

MODES_SOURCE_VALIDES = ("recherche", "sur_pieces")


def obtenir_mode_source(conversation_id: str, user_id: str) -> str | None:
    """Mode source actuellement actif pour cette conversation, ou None si
    l'eleve n'a encore rien choisi (equivaut a "Aucun", comportement
    actuel inchange). Pas de valeur par defaut implicite : None reste
    None jusqu'au premier choix explicite de l'eleve."""
    maintenant = time.time()
    entree = _cache_mode_source.get(conversation_id)
    if entree is not None and entree["expire_a"] > maintenant:
        return entree["valeur"]
    try:
        res = (
            supabase.table("conversation_mode_source")
            .select("mode_source")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture mode source {conversation_id}) : {e}")
        return None
    valeur = res.data["mode_source"] if (res and res.data) else None
    _cache_mode_source[conversation_id] = {"valeur": valeur, "expire_a": maintenant + _DUREE_CACHE_SECONDES}
    return valeur


def definir_mode_source(conversation_id: str, user_id: str, mode_source: str | None) -> dict | None:
    """Fixe (ou efface, si mode_source est None, c'est-a-dire "Aucun") le
    mode source actif de cette conversation pour cet eleve. Upsert sur
    conversation_id seul (cle primaire). Une conversation n'appartient
    qu'a un seul utilisateur, jamais recreee pour un autre. None si
    mode_source est fourni mais ne fait pas partie de
    MODES_SOURCE_VALIDES (jamais d'ecriture d'une valeur invalide en
    base)."""
    if mode_source is not None and mode_source not in MODES_SOURCE_VALIDES:
        return None
    ligne = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "mode_source": mode_source,
    }
    try:
        res = (
            supabase.table("conversation_mode_source")
            .upsert(ligne, on_conflict="conversation_id")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (definition mode source {conversation_id}) : {e}")
        raise
    # Cache invalide immediatement : le prochain message de cette
    # conversation doit voir le nouveau mode tout de suite, jamais
    # attendre l'expiration du cache court d'obtenir_mode_source.
    _cache_mode_source.pop(conversation_id, None)
    return res.data[0] if res.data else ligne
