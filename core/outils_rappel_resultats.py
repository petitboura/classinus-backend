"""
Outil MCP "rappeler_resultat_outil" (27/09/2026, demande explicite Bourama :
reduire les couts sans jamais perdre de contexte).

Contexte : au-dela d'un certain volume, les resultats d'outils les plus
anciens ne sont plus renvoyes au modele a chaque message, seulement un
rappel (voir core/historique_outils.py). Le modele vient chercher le contenu
complet ici, UNIQUEMENT s'il en a besoin, au lieu de reexecuter l'outil
d'origine (ce qui refait un travail deja fait).

Recherche par DESCRIPTION et non par numero : le frontend n'envoie aucun
identifiant de message dans l'historique (voir api/chat.py:MessageHistorique).
conversation_id vient de ctx, comme dans core/outils_changement_mode.py, et
les resultats sont relus dans Supabase (historique_conversations.meta, voir
core/persistance_echanges.py). Aucune nouvelle table.

Expose cote CHAT SEULEMENT, jamais sur le serveur MCP public.
"""

import logging

from core.outils_generation_commun import mcp_generation, Context, _supabase_memoire as supabase
from core.texte_recherche_simple import mots_significatifs

# Les resultats d'outils sont volumineux : on ne relit que les messages les
# plus recents qui en portent, pour ne pas peser sur le quota Supabase.
_LIMITE_LIGNES_RELUES = 80

# Un rappel doit rester cible : quelques resultats au maximum.
_LIMITE_RESULTATS_RENVOYES = 3


def _score(mots_requete, o):
    """Nombre de mots significatifs communs entre la description donnee par le
    modele et un resultat d'outil archive. Le nom de l'outil compte double."""
    nom = mots_significatifs(f"{o.get('nomLisible') or ''} {o.get('nomOutil') or ''}".replace("_", " "))
    corps = mots_significatifs(o.get("resultat"))
    return 2 * len(mots_requete & nom) + len(mots_requete & corps)


def _rechercher(conversation_id, requete):
    lignes = (
        supabase.table("historique_conversations")
        .select("meta")
        .eq("conversation_id", str(conversation_id))
        .eq("role", "assistant")
        .not_.is_("meta", "null")
        .order("created_at", desc=True)
        .limit(_LIMITE_LIGNES_RELUES)
        .execute()
    ).data or []

    mots_requete = mots_significatifs(requete)
    if not mots_requete:
        return []
    candidats = []
    for ligne in lignes:
        for o in ((ligne.get("meta") or {}).get("outils") or []):
            s = _score(mots_requete, o)
            if s > 0:
                candidats.append((s, o))

    candidats.sort(key=lambda c: c[0], reverse=True)
    return [o for _, o in candidats[:_LIMITE_RESULTATS_RENVOYES]]


@mcp_generation.tool()
def rappeler_resultat_outil(requete: str, ctx: Context) -> str:
    """
    Rappelle le résultat COMPLET d'un outil déjà exécuté plus tôt dans cette
    même conversation, sans le réexécuter.

    À utiliser quand l'historique indique qu'un outil a déjà été exécuté sur
    un sujet ("[Outil déjà exécuté plus tôt dans cette conversation : ...]")
    et que tu as maintenant besoin de son contenu complet pour répondre.

    RÈGLE IMPORTANTE : si un résultat pertinent existe déjà plus tôt dans la
    conversation, appelle TOUJOURS cet outil en premier plutôt que de
    relancer l'outil d'origine (recherche, lecture de document, etc.).
    Relancer l'outil d'origine refait un travail déjà fait, pour un résultat
    qui ne changera pas. Ne réexécute l'outil d'origine que si ce rappel ne
    trouve rien d'utile, ou si tu as une bonne raison de penser que le
    résultat a changé depuis (par exemple une recherche web sur une
    actualité récente).

    `requete` : décris en quelques mots ce que tu cherches (le sujet, ou le
    nom de l'outil concerné), par exemple "résultat de la recherche sur les
    tarifs Ooredoo" ou "contenu du fichier lu plus tôt sur la photosynthèse".
    """
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")
    if not conversation_id:
        return "Erreur : impossible d'identifier la conversation, réexécute l'outil d'origine."
    if not (requete or "").strip():
        return "Erreur : décris ce que tu cherches (sujet ou nom de l'outil)."

    try:
        resultats = _rechercher(conversation_id, requete)
    except Exception as e:
        logging.error(f"ERREUR rappeler_resultat_outil : {e}")
        return "Erreur technique pour rappeler ce résultat, réexécute l'outil d'origine si besoin."

    if not resultats:
        return "Aucun résultat archivé ne correspond à cette description. Réexécute l'outil d'origine si besoin."

    blocs = []
    for o in resultats:
        nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
        blocs.append(f"[Résultat rappelé : {nom}]\n{o.get('resultat') or ''}")
    return "\n\n".join(blocs)
