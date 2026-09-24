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

Écriture seule pendant longtemps (pas de lecture/agrégation -- hors
scope tant que l'écran de suivi n'existe pas). Pas de cache en écriture :
un INSERT par réponse, jamais de mise à jour, donc rien à invalider.

LECTURE AJOUTÉE (23/09/2026, demande Bourama) : l'IA ne savait jusqu'ici
jamais ce que l'étudiant avait répondu à un QCM (stocké mais jamais relu
nulle part) -- voir lister_reponses_qcm ci-dessous, utilisée à la fois
pour l'injection automatique (core/main.py, les 2 messages qui suivent un
QCM donné par le modèle) et par le filet de sécurité core/outils_reponses_qcm.py.
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


def lister_reponses_qcm(conversation_id: str, limite: int = 20) -> list[dict]:
    """Renvoie les réponses QCM de cette conversation, les plus récentes
    en dernier (ordre chronologique), au plus `limite`. Ne lève jamais
    d'exception vers l'appelant : une liste vide en cas d'erreur, jamais
    de crash de l'injection auto ni de l'outil pour ça (mêmes conventions
    que le reste du fichier)."""
    try:
        res = (
            supabase.table("historique_reponses_qcm")
            .select("question, choix, reponse_choisie, reponse_correcte, explication, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture réponses QCM, conversation {conversation_id}) : {e}")
        return []
    lignes = res.data or []
    return list(reversed(lignes))


def formater_reponses_qcm(reponses: list[dict]) -> str:
    """Met en forme une liste de réponses (voir lister_reponses_qcm) en
    texte lisible par le modèle. Partagé entre l'injection automatique
    (core/main.py) et l'outil de secours (core/outils_reponses_qcm.py)
    pour que le format soit identique dans les deux cas."""
    if not reponses:
        return ""
    blocs = []
    for r in reponses:
        choix = r.get("choix") or []
        i_choisi = r.get("reponse_choisie")
        i_correct = r.get("reponse_correcte")
        texte_choisi = choix[i_choisi] if isinstance(i_choisi, int) and 0 <= i_choisi < len(choix) else "?"
        texte_correct = choix[i_correct] if isinstance(i_correct, int) and 0 <= i_correct < len(choix) else "?"
        correct = i_choisi == i_correct
        bloc = (
            f"- Question : \"{r.get('question', '')}\"\n"
            f"  Réponse de l'étudiant : \"{texte_choisi}\" ({'correcte' if correct else 'incorrecte'})"
        )
        if not correct:
            bloc += f"\n  Bonne réponse : \"{texte_correct}\""
        blocs.append(bloc)
    return "\n".join(blocs)


def reponses_qcm_a_injecter(historique: list[dict], conversation_id: str | None) -> list[dict]:
    """Calcule dans main.py:chat(), avant _construire_system_prompt.
    Renvoie les réponses QCM à injecter automatiquement dans le prompt
    système -- uniquement quand le message en train d'être traité est l'un
    des 2 premiers messages de l'étudiant suivant un QCM donné par le
    modèle (bloc ```qcm) dans `historique`. Liste vide dans tous les
    autres cas (rien à injecter, comportement inchangé) -- voir alors
    l'outil de secours lire_reponses_qcm (core/outils_reponses_qcm.py)
    pour un QCM plus ancien.

    Aucune table de compteur dédiée : tout est recalculé à chaque message
    à partir de `historique`, déjà chargé pour cet appel (voir
    api/chat.py:MessageHistorique -- role/content seulement, pas
    d'horodatage). `historique` ne contient pas encore le message en
    cours de traitement, d'où le "+1" ci-dessous.

    LIMITE CONNUE : lister_reponses_qcm ne filtre pas précisément sur les
    réponses données APRÈS ce ```qcm (pas de lien direct message <->
    ligne de la table, seulement conversation_id) -- renvoie les
    dernières réponses de la conversation, au plus 20. Suffisant en
    pratique (fenêtre de 2 messages, cas d'usage = un ou quelques QCM
    donnés d'affilée), à revoir si ça pose problème un jour."""
    if not conversation_id:
        return []
    index_dernier_qcm = None
    for i in range(len(historique) - 1, -1, -1):
        m = historique[i]
        if m.get("role") == "assistant" and "```qcm" in (m.get("content") or ""):
            index_dernier_qcm = i
            break
    if index_dernier_qcm is None:
        return []
    nb_messages_etudiant_depuis = sum(
        1 for m in historique[index_dernier_qcm + 1:] if m.get("role") == "user"
    )
    if nb_messages_etudiant_depuis + 1 > 2:
        return []
    return lister_reponses_qcm(conversation_id)
