# Créé le 12/10/2026, demande Bourama : « arrêter c'est arrêter ». Avant, le bouton
# Arrêter du chat coupait seulement la connexion du flux : les outils en cours et la
# boucle d'agent continuaient côté serveur. Ce module porte le signal d'arrêt d'un
# tour de conversation.
#
# Un jeton (ArretTour) est créé au début de chaque tour (api/chat.py) et suit le tour
# partout où il passe (chat(), _agent_groq, _traiter_appels). La route
# POST /api/chat/arreter lève le jeton de TOUS les tours en cours du compte. Un tour
# démarré après la demande d'arrêt reçoit un jeton neuf : il n'est jamais touché par
# un arrêt antérieur.
#
# Les contrôles se font par lecture (est_demande), jamais par exception : la cascade de
# modèles de chat() attrape les exceptions pour basculer sur un modèle de secours, un
# arrêt ne doit surtout pas relancer une réponse.
import threading


class ArretTour:
    def __init__(self, user_id):
        self.user_id = user_id
        self._evenement = threading.Event()

    def demander(self):
        self._evenement.set()

    def est_demande(self):
        return self._evenement.is_set()


_verrou = threading.Lock()
_tours_ouverts: dict = {}


def ouvrir_arret(user_id):
    """Jeton d'un nouveau tour. None pour un visiteur non connecté (rien à arrêter côté serveur)."""
    if not user_id:
        return None
    jeton = ArretTour(user_id)
    with _verrou:
        _tours_ouverts.setdefault(user_id, set()).add(jeton)
    return jeton


def fermer_arret(jeton):
    if jeton is None:
        return
    with _verrou:
        tours = _tours_ouverts.get(jeton.user_id)
        if tours is not None:
            tours.discard(jeton)
            if not tours:
                _tours_ouverts.pop(jeton.user_id, None)


def demander_arret_utilisateur(user_id):
    """Lève le jeton de tous les tours en cours de ce compte. Renvoie leur nombre."""
    if not user_id:
        return 0
    with _verrou:
        tours = list(_tours_ouverts.get(user_id, ()))
    for jeton in tours:
        jeton.demander()
    return len(tours)


def arret_demande(jeton):
    return jeton is not None and jeton.est_demande()
