"""
Plafond d'aller-retours "outil" propre a un tour, pour le parcours "Tout
d'un coup" du guide visuel (20/09/2026, demande Bourama : Clovis parcourt
toute l'application en une fois, sans s'arreter).

Le plafond normal (parametres_outils(), 20 par defaut, voir
core/boucle_agent.py) coupe un tour bien avant la fin d'un parcours
complet : chaque section demande plusieurs appels (lecture de l'article,
clics, bulles de dialogue). Ce module permet a chat() de relever le
plafond pour CET utilisateur, uniquement pendant un tour du guide visuel,
sans toucher au reglage global des autres conversations. La detection de
repetition (tolerance_repetition) reste active : seule la limite absolue
change.

Meme forme que les etats par utilisateur de core/canal_agent_applicatif.py
(verrou threading : la boucle d'agent est un generateur synchrone execute
dans un thread). Retire a la fin du flux du chat (voir api/chat.py).
"""

import threading

PLAFOND_OUTILS_GUIDE_VISUEL = 80

_verrou = threading.Lock()
_plafonds: dict[str, int] = {}


def definir_plafond_tour(user_id: str, plafond: int) -> None:
    if not user_id:
        return
    with _verrou:
        _plafonds[user_id] = plafond


def plafond_tour(user_id: str | None) -> int | None:
    if not user_id:
        return None
    with _verrou:
        return _plafonds.get(user_id)


def retirer_plafond_tour(user_id: str) -> None:
    if not user_id:
        return
    with _verrou:
        _plafonds.pop(user_id, None)
