"""
Outil MCP "rappeler_resultat_outil" (27/09/2026, demande explicite
Bourama : reduire les couts sans jamais perdre de contexte).

Contexte : jusqu'ici (core/historique_outils.py), une fois qu'un certain
volume de resultats d'outils s'accumulait dans une conversation, les plus
anciens etaient soit renvoyes en entier au modele a CHAQUE message
suivant, soit condenses par un appel a un modele rapide (_resumer_outils_
anciens) -- dans les deux cas, on payait quelque chose a chaque tour, meme
quand ce vieux resultat ne servait plus jamais a rien.

Nouveau principe : au-dela d'un certain point, on ne renvoie plus qu'un
simple rappel ("tel outil, execute plus tot, resultat disponible") --
voir historique_outils.py:_pointeur_outil. Le modele va lui-meme chercher
le contenu complet UNIQUEMENT s'il en a reellement besoin, via cet outil,
plutot que de re-executer betement l'outil d'origine (ce qui recree la
recherche/lecture depuis zero, pour un resultat qu'on a deja).

Recherche par DESCRIPTION, pas par identifiant numerique : le frontend
n'envoie aujourd'hui aucun identifiant de message dans l'historique
transmis a chaque appel (voir api/chat.py:MessageHistorique), seulement
role/content/outils. Demander un numero aurait donc exige un changement
cote frontend en plus. A la place, ctx donne directement conversation_id
(meme mecanisme que core/outils_changement_mode.py) : on relit les
resultats d'outils deja sauvegardes pour CETTE conversation directement
dans Supabase (colonne meta, voir persistance_echanges.py) et on fait
correspondre la description donnee par le modele au nom/resultat de
chaque outil archive.

Expose cote CHAT SEULEMENT (meme principe que core/outils_minuteurs.py,
core/outils_changement_mode.py) : jamais sur le serveur MCP public.
"""

import logging

from constantes_agent import supabase
from core.outils_generation_commun import mcp_generation, Context

# Nombre max de lignes historique_conversations relues pour la recherche
# (au-dela, on considere que c'est trop vieux pour valoir la peine d'etre
# refouille automatiquement -- meme esprit que SEUIL_RESUME_MESSAGES).
_LIMITE_LIGNES_RELUES = 200

# Nombre max de resultats renvoyes au modele en une fois : rappeler_
# resultat_outil doit rester un rappel cible, pas une nouvelle facon de
# renvoyer un paquet volumineux d'un coup.
_LIMITE_RESULTATS_RENVOYES = 3


def _mots(texte):
    return set((texte or "").lower().split())


def _score(requete_mots, o):
    """Score de correspondance simple (nombre de mots communs) entre la
    description donnee par le modele et un resultat d'outil archive.
    Le nom de l'outil compte double : une correspondance sur "recherche_
    bibliotheque" est un signal plus fort qu'un mot qui apparait par
    hasard au milieu d'un long resultat."""
    nom = _mots(o.get("nomLisible")) | _mots(o.get("nomOutil"))
    corps = _mots(o.get("resultat"))
    return 2 * len(requete_mots & nom) + len(requete_mots & corps)


def _rechercher(conversation_id, requete):
    lignes = (
        supabase.table("historique_conversations")
        .select("meta, created_at")
        .eq("conversation_id", conversation_id)
        .eq("role", "assistant")
        .not_.is_("meta", "null")
        .order("created_at", desc=True)
        .limit(_LIMITE_LIGNES_RELUES)
        .execute()
    ).data or []

    requete_mots = _mots(requete)
    candidats = []
    for ligne in lignes:
        for o in ((ligne.get("meta") or {}).get("outils") or []):
            s = _score(requete_mots, o)
            if s > 0:
                candidats.append((s, o))

    candidats.sort(key=lambda c: c[0], reverse=True)
    return [o for _, o in candidats[:_LIMITE_RESULTATS_RENVOYES]]


@mcp_generation.tool()
def rappeler_resultat_outil(requete: str, ctx: Context) -> str:
    """
    Rappelle le résultat COMPLET d'un outil déjà exécuté plus tôt dans
    cette même conversation, sans le réexécuter.

    À utiliser quand l'historique mentionne qu'un outil a déjà été
    exécuté sur un sujet ("[Outil déjà exécuté plus tôt -- ...]") et que
    tu as maintenant besoin de son contenu complet pour répondre.

    RÈGLE IMPORTANTE : si un résultat pertinent existe déjà plus tôt dans
    la conversation, appelle TOUJOURS cet outil en premier plutôt que de
    relancer l'outil d'origine (recherche, lecture de document, etc.) --
    relancer l'outil d'origine refait un travail déjà fait, pour un
    résultat qui ne changera pas. Ne réexécute l'outil d'origine que si
    ce rappel ne trouve rien d'utile, ou si tu as une bonne raison de
    penser que le résultat a changé depuis (ex : une recherche web sur
    une actualité récente).

    `requete` : décris en quelques mots ce que tu cherches (le sujet, ou
    le nom de l'outil concerné) -- ex. "résultat de la recherche sur les
    tarifs Ooredoo", "contenu du fichier lu plus tôt sur la photosynthèse".
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
        return "Aucun résultat archivé ne correspond à cette description -- réexécute l'outil d'origine si besoin."

    blocs = []
    for o in resultats:
        nom = o.get("nomLisible") or o.get("nomOutil") or "Outil"
        blocs.append(f"[Résultat rappelé -- {nom}]\n{o.get('resultat') or ''}")
    return "\n\n".join(blocs)
