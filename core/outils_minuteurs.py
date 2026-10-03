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
    DUREE_MIN_SECONDES,
    ErreurMinuteur,
    ajuster_minuteur,
    arreter_minuteur,
    creer_minuteur,
    lister_minuteurs_actifs,
    serialiser,
)
from core.outils_generation_commun import mcp_generation, Context


def _duree_lisible(secondes: int) -> str:
    # Jusqu'aux jours (03/10/2026) : plus aucune limite de duree, un minuteur
    # peut durer des heures ou des jours.
    jours, reste = divmod(max(0, int(secondes)), 86400)
    heures, reste = divmod(reste, 3600)
    minutes, reste = divmod(reste, 60)
    morceaux = []
    if jours:
        morceaux.append(f"{jours} j")
    if heures:
        morceaux.append(f"{heures} h")
    if minutes:
        morceaux.append(f"{minutes} min")
    if reste or not morceaux:
        morceaux.append(f"{reste} s")
    return " ".join(morceaux)


def _decrire(minuteur: dict) -> str:
    titre = minuteur.get("titre") or "sans titre"
    ligne = f"id {minuteur['id']}, {titre}, reste {_duree_lisible(minuteur['secondes_restantes'])}"
    if minuteur.get("action_fin"):
        ligne += f", prévu à la fin : {minuteur['action_fin']}"
    return ligne


def _texte_erreur(e: ErreurMinuteur) -> str:
    if e.code == "MINUTEUR_DUREE_INVALIDE":
        return (
            f"Erreur : durée invalide. Le minuteur doit durer au moins {DUREE_MIN_SECONDES} seconde. "
            "Pour retirer du temps, ne retire pas plus que ce qu'il reste ; "
            "pour tout arrêter, utilise l'action \"arreter\"."
        )
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
    duree_secondes: int = 0,
    ajuster_secondes: int = 0,
) -> str:
    """
    Minuteur affiché sur tous les écrans de l'étudiant (pastille ou carte).
    Il ne bloque rien : il continue pendant que l'étudiant discute ou change
    de page. Lance-en un de ta propre initiative quand c'est pertinent
    (révision chronométrée, pause, exercice minuté), sans attendre qu'on te
    le demande. Aucune limite de durée ni de nombre de minuteurs.

    `action` :
    - "lancer" : durée obligatoire, en `duree_minutes` et/ou en
      `duree_secondes` (entiers, elles s'additionnent : 90 minutes = 90 en
      `duree_minutes` ; 30 secondes = 30 en `duree_secondes`), au moins 1
      seconde au total. `titre` court optionnel, `action_a_la_fin` = ce que
      tu feras quand il sonnera (ex : proposer un quiz de 5 questions).
      Déduis-le de la conversation ; si ce n'est pas clair, demande-le à
      l'étudiant avant de lancer.
    - "modifier" : `ajuster_minutes` et/ou `ajuster_secondes` (positif pour
      ajouter, négatif pour retirer) et/ou `titre`.
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
            if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (duree_minutes, duree_secondes)):
                return "Erreur : `duree_minutes` et `duree_secondes` doivent être des entiers positifs."
            total_secondes = duree_minutes * 60 + duree_secondes
            if total_secondes < DUREE_MIN_SECONDES:
                return "Erreur : indique la durée avec `duree_minutes` et/ou `duree_secondes` (au moins 1 seconde)."
            ligne = creer_minuteur(
                user_id,
                total_secondes,
                titre=titre,
                action_fin=action_a_la_fin,
                lance_par="clovis",
                conversation_id=conversation_id,
            )
            minuteur = serialiser(ligne)
            return (
                f"Minuteur lancé : {_decrire(minuteur)}. Il est affiché sur l'écran de l'étudiant et ne "
                "bloque rien. Ne dis pas qu'il est terminé : l'appli t'enverra un message automatique à la fin."
            )

        if action == "modifier":
            if any(not isinstance(v, int) or isinstance(v, bool) for v in (ajuster_minutes, ajuster_secondes)):
                return "Erreur : `ajuster_minutes` et `ajuster_secondes` doivent être des entiers."
            delta_secondes = ajuster_minutes * 60 + ajuster_secondes
            if not delta_secondes and not titre:
                return "Erreur : indique `ajuster_minutes` et/ou `ajuster_secondes` et/ou `titre`."
            id_cible, erreur = _resoudre_id(user_id, minuteur_id)
            if erreur:
                return erreur
            ligne = ajuster_minuteur(
                user_id, id_cible, ajuster_secondes=delta_secondes, titre=titre if titre else None
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
