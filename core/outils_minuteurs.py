"""
Outil MCP des minuteurs du chat (20/09/2026, demande Bourama) : Clovis peut
lancer, modifier, arreter et lister des minuteurs, de sa propre initiative
quand c'est pertinent (l'etudiant ne sait pas que cette fonction existe).

Toute la logique est dans core/minuteurs.py (les boutons de l'etudiant,
api/minuteurs.py, utilisent les memes regles). Expose cote CHAT seulement
(decision Bourama, 20/09/2026) : rien sur le serveur MCP public
(core/serveur_mcp_espace.py), qui sert cote professeur, sans conversation
d'etudiant en cours.
"""

import logging

from core.erreurs import MESSAGES_FR
from core.minuteurs import (
    DUREE_MAX_SECONDES,
    DUREE_MIN_SECONDES,
    NB_MAX_MINUTEURS_ACTIFS,
    ErreurMinuteur,
    ajuster_minuteur,
    arreter_minuteur,
    creer_minuteur,
    lister_minuteurs_actifs,
    serialiser,
)
from core.outils_generation_commun import mcp_generation, Context


def _duree_lisible(secondes: int) -> str:
    minutes, reste = divmod(max(0, int(secondes)), 60)
    if minutes and reste:
        return f"{minutes} min {reste} s"
    if minutes:
        return f"{minutes} min"
    return f"{reste} s"


def _decrire(minuteur: dict) -> str:
    titre = minuteur.get("titre") or "sans titre"
    ligne = f"id {minuteur['id']}, {titre}, reste {_duree_lisible(minuteur['secondes_restantes'])}"
    if minuteur.get("action_fin"):
        ligne += f", prévu à la fin : {minuteur['action_fin']}"
    return ligne


def _texte_erreur(e: ErreurMinuteur) -> str:
    if e.code == "MINUTEUR_DUREE_INVALIDE":
        return (
            f"Erreur : durée invalide. Le minuteur doit durer entre {DUREE_MIN_SECONDES} secondes "
            f"et {DUREE_MAX_SECONDES // 60} minutes. Pour retirer du temps, ne retire pas plus que "
            "ce qu'il reste ; pour tout arrêter, utilise l'action \"arreter\"."
        )
    if e.code == "MINUTEUR_TROP_NOMBREUX":
        return f"Erreur : {NB_MAX_MINUTEURS_ACTIFS} minuteurs sont déjà en cours, arrête-en un avant d'en lancer un autre."
    return "Erreur : " + MESSAGES_FR.get(e.code, MESSAGES_FR["ERREUR_INCONNUE"])


def _resoudre_id(user_id: str, minuteur_id: str) -> tuple[str | None, str | None]:
    """(id, None) si trouve, (None, message d'erreur pour le modele) sinon.
    Sans id donne : accepte seulement s'il n'y a qu'UN minuteur en cours,
    jamais de choix au hasard entre plusieurs."""
    if minuteur_id:
        return minuteur_id, None
    actifs = lister_minuteurs_actifs(user_id)
    if not actifs:
        return None, "Aucun minuteur n'est en cours."
    if len(actifs) == 1:
        return actifs[0]["id"], None
    lignes = "\n".join("- " + _decrire(serialiser(m)) for m in actifs)
    return None, "Plusieurs minuteurs sont en cours, précise `minuteur_id` :\n" + lignes


@mcp_generation.tool()
def gerer_minuteur(
    action: str,
    ctx: Context,
    titre: str = "",
    duree_minutes: int = 0,
    ajuster_minutes: int = 0,
    minuteur_id: str = "",
    action_a_la_fin: str = "",
) -> str:
    """
    Minuteur affiché dans le chat de l'étudiant. Il ne bloque rien : il
    continue pendant que l'étudiant discute ou change de page. Lance-en un
    de ta propre initiative quand c'est pertinent (révision chronométrée,
    pause, exercice minuté), sans attendre qu'on te le demande.

    `action` :
    - "lancer" : `duree_minutes` obligatoire (entier, 1 à 720), `titre`
      court optionnel, `action_a_la_fin` = ce que tu feras quand il
      sonnera (ex : proposer un quiz de 5 questions). Déduis-le de la
      conversation ; si ce n'est pas clair, demande-le à l'étudiant avant
      de lancer.
    - "modifier" : `ajuster_minutes` (positif pour ajouter, négatif pour
      retirer) et/ou `titre`.
    - "arreter" : arrête le minuteur.
    - "lister" : liste les minuteurs en cours.

    Pour "modifier" et "arreter", `minuteur_id` vient de "lancer" ou
    "lister" ; facultatif s'il n'y a qu'un seul minuteur en cours.

    À la fin, l'appli t'envoie un message automatique : n'annonce JAMAIS
    qu'un minuteur est terminé avant de l'avoir reçu, et à ce moment-là
    applique ce qui était prévu.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")

    try:
        if action == "lancer":
            if not isinstance(duree_minutes, int) or isinstance(duree_minutes, bool) or duree_minutes < 1:
                return "Erreur : `duree_minutes` doit être un entier supérieur ou égal à 1."
            ligne = creer_minuteur(
                user_id,
                duree_minutes * 60,
                titre=titre,
                action_fin=action_a_la_fin,
                lance_par="clovis",
                conversation_id=conversation_id,
            )
            minuteur = serialiser(ligne)
            return (
                f"Minuteur lancé : {_decrire(minuteur)}. Il est affiché dans le chat de l'étudiant et ne "
                "bloque rien. Ne dis pas qu'il est terminé : l'appli t'enverra un message automatique à la fin."
            )

        if action == "modifier":
            if not ajuster_minutes and not titre:
                return "Erreur : indique `ajuster_minutes` et/ou `titre`."
            id_cible, erreur = _resoudre_id(user_id, minuteur_id)
            if erreur:
                return erreur
            ligne = ajuster_minuteur(
                user_id, id_cible, ajuster_secondes=ajuster_minutes * 60, titre=titre if titre else None
            )
            return f"Minuteur modifié : {_decrire(serialiser(ligne))}."

        if action == "arreter":
            id_cible, erreur = _resoudre_id(user_id, minuteur_id)
            if erreur:
                return erreur
            arreter_minuteur(user_id, id_cible)
            return "Minuteur arrêté."

        if action == "lister":
            actifs = lister_minuteurs_actifs(user_id)
            if not actifs:
                return "Aucun minuteur n'est en cours."
            return "Minuteurs en cours :\n" + "\n".join("- " + _decrire(serialiser(m)) for m in actifs)

    except ErreurMinuteur as e:
        return _texte_erreur(e)
    except Exception as e:
        logging.error(f"ERREUR gerer_minuteur ({action}) : {e}")
        return "Erreur : impossible de gérer ce minuteur, réessaie."

    return "Erreur : action inconnue. Actions valides : lancer, modifier, arreter, lister."
