"""Limite quotidienne de générations Higgsfield par utilisateur.

La clé API est partagée : sans limite, un seul utilisateur peut vider les crédits.
Les plafonds se règlent sans toucher au code, avec des variables Railway :
HIGGSFIELD_LIMITE_VIDEOS_PAR_JOUR et HIGGSFIELD_LIMITE_MCP_PAR_JOUR.
Les images n'ont plus de limite par jour (décision du 09/11) : leur seul frein est le
solde de crédits d'images.
Le décompte est fait en base (table higgsfield_usage), par jour UTC.
"""
import logging
import os

from core.higgsfield_requetes import ErreurHiggsfield

_REGLAGES = {
    "video": ("HIGGSFIELD_LIMITE_VIDEOS_PAR_JOUR", 3, "vidéos"),
    # Fonctions MCP-only sur le compte partage : meme protection, plafond a
    # part (migration 2026_10_31_higgsfield_usage_mcp.sql).
    "mcp": ("HIGGSFIELD_LIMITE_MCP_PAR_JOUR", 10, "générations MCP partagées"),
}


def limite_du_jour(genre: str) -> int:
    variable, defaut, _ = _REGLAGES[genre]
    try:
        return max(0, int(os.environ.get(variable, defaut)))
    except ValueError:
        return defaut


def reserver_generation(client_base, user_id, genre: str) -> None:
    """Réserve une génération du jour, sinon lève une ErreurHiggsfield lisible.

    À appeler juste avant l'envoi à Higgsfield. Sans utilisateur identifié, on refuse
    plutôt que de laisser passer une génération que personne ne pourrait limiter.
    """
    if genre not in _REGLAGES:
        return  # genre sans limite par jour (les images)
    if not user_id:
        raise ErreurHiggsfield("Impossible d'identifier l'utilisateur, génération refusée.")
    limite = limite_du_jour(genre)
    try:
        reponse = client_base.rpc(
            "higgsfield_reserver_usage", {"p_user": user_id, "p_genre": genre, "p_limite": limite}
        ).execute()
    except Exception as e:
        logging.error("ERREUR SUPABASE (réservation Higgsfield pour %s) : %s", user_id, e)
        raise ErreurHiggsfield("Impossible de vérifier ta limite du jour, réessaie dans un instant.")
    if reponse.data is not True:
        nom = _REGLAGES[genre][2]
        raise ErreurHiggsfield(
            f"Limite du jour atteinte ({limite} {nom} par jour). Dis-le à l'utilisateur : "
            "il pourra en refaire demain."
        )
