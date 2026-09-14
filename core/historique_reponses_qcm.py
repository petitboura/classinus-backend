"""Historique des réponses QCM (item 2 des specs indépendantes ScholarFlow
AI, volet étudiant, 14/09/2026, demande Bourama). Stocke chaque réponse
donnée par un étudiant à un QCM généré (format ```qcm, voir item 5 dans
core/profils_agents.py et QCMInteractif.tsx, item 3), en vue d'un futur
écran de suivi (pas construit maintenant) -- pour l'instant affiché
seulement dans le fil de conversation et l'historique.

ATTENTION NOM (même point d'audit que conversation_persona_pedagogique) :
ne jamais utiliser "mode" dans ce module ou la table sous-jacente --
conversation_mode_actif désigne un concept totalement différent
(rattachement enseignant/code de classe).

Écriture seule ici (pas de lecture/agrégation -- hors scope tant que
l'écran de suivi n'existe pas). Pas de cache : un INSERT par réponse,
jamais de mise à jour, donc rien à invalider.
"""
import logging

from api.auth import supabase


def enregistrer_reponse_qcm(
    conversation_id: str,
    user_id: str,
    question: str,
    choix: list[str],
    reponse_choisie: int,
    reponse_correcte: int,
    explication: str | None,
) -> dict | None:
    """Enregistre une réponse d'étudiant à un QCM. reponse_choisie/
    reponse_correcte sont des index (0-based) dans `choix`, même
    convention que le format ```qcm et QCMInteractif.tsx. Ne lève jamais
    d'exception vers l'appelant : un échec d'écriture de l'historique ne
    doit jamais empêcher l'étudiant de voir sa correction (déjà affichée
    côté frontend avant même cet appel réseau, voir QCMInteractif.tsx) --
    seulement loggé."""
    ligne = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "question": question,
        "choix": choix,
        "reponse_choisie": reponse_choisie,
        "reponse_correcte": reponse_correcte,
        "explication": explication,
    }
    try:
        res = supabase.table("historique_reponses_qcm").insert(ligne).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (enregistrement réponse QCM, conversation {conversation_id}) : {e}")
        return None
    return res.data[0] if res.data else None
