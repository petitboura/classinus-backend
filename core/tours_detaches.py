"""Tours de chat detaches de la connexion HTTP (28/10/2026, demande de Bourama).

Avant : le flux SSE de /api/chat etait lu directement par la connexion du navigateur. Des que
la connexion se fermait (rechargement de la page, changement de conversation, coupure de
reseau), le generateur etait ferme avec elle : la boucle d'agent et les outils s'arretaient net,
et comme l'echange n'est sauvegarde qu'a la toute fin du tour, rien n'etait enregistre.

Maintenant : le travail tourne dans un thread a lui, independant de la connexion. Chaque ligne
SSE produite est rangee dans le tour. La connexion HTTP ne fait que LIRE ce rangement :
- si elle se ferme, le travail continue et finit par sauvegarder l'echange comme d'habitude ;
- une nouvelle connexion peut se rattacher au meme tour et reprendre la lecture exactement la
  ou la precedente s'etait arretee (parametre `depuis`, nombre de lignes deja recues).

Le bouton Arreter n'est pas touche : il passe par POST /api/chat/arreter, qui leve le jeton
d'arret du tour (core/arret_tour.py), et ce jeton appartient au thread de travail.

Le rangement rapide est en memoire du processus, double par une persistance en base
(core/persistance_tours.py, 31/10/2026) : un redemarrage ne perd plus le texte partiel,
le tour orphelin passe "interrompu" et l'interface propose Continuer. Le processus web
reste l'executeur (decision de Bourama) : un redemarrage coupe toujours le travail en
cours, mais plus son contenu. Les visiteurs non connectes n'ont pas de tour detache :
rien n'est rattachable a un compte, le flux reste direct.
"""
import contextvars
import json
import logging
import threading
import time
import uuid
from typing import Callable, Iterable, Iterator, Optional

from core.plafonds_reglables import (
    CONSERVATION_TOUR_DETACHE, INTERVALLE_PURGE_TOURS_DETACHES,
    MAX_OCTETS_TOUR_DETACHE, MAX_OCTETS_TOURS_DETACHES_CONSERVES,
    MAX_TOURS_DETACHES_CONSERVES,
)

# Duree maximale d'une attente sans nouvelle ligne avant de reverifier l'etat du tour. Ne sert
# qu'a rester reveille : le signe de vie envoye au client a son propre delai (parametre).
_PAS_ATTENTE_SECONDES = 1.0

LIGNE_SIGNE_VIE = ": signe de vie\n\n"
LIGNE_FIN = "data: [DONE]\n\n"


def _ids_sauvegardes(ligne: str) -> Optional[dict]:
    """Identifiants de l'echange, lus dans l'evenement "meta" que le chat emet une fois l'echange
    sauvegarde (api/chat.py:_evenements_sse). None pour toute autre ligne."""
    if '"type": "meta"' not in ligne or not ligne.startswith("data:"):
        return None
    try:
        evenement = json.loads(ligne[len("data:"):].strip())
    except ValueError:
        return None
    if not isinstance(evenement, dict) or evenement.get("type") != "meta":
        return None
    return {
        "message_id_user": evenement.get("message_id_user"),
        "message_id_assistant": evenement.get("message_id_assistant"),
    }


class TourDetache:
    """Un tour de chat en cours ou termine : ses lignes SSE, dans l'ordre, et son etat."""

    def __init__(self, user_id: str, conversation_id: Optional[str], resume: Optional[dict] = None,
                 persistance=None, a_la_cloture: Optional[Callable] = None):
        self.id = uuid.uuid4().hex
        self.user_id = user_id
        self.conversation_id = conversation_id
        # Couche durable optionnelle (core/persistance_tours.py) : ecrit le tour en base par
        # paquets. None = memoire seule (visiteurs, tests). Ses erreurs ne remontent jamais ici.
        self._persistance = persistance
        # Appele une fois a la cloture si plus aucun lecteur n'est rattache (notification de fin).
        self._a_la_cloture = a_la_cloture
        # Ce dont une page qui se rouvre a besoin pour redessiner le debut du tour (le message de
        # l'utilisateur, par exemple) : le serveur ne l'a pas encore sauvegarde avant la fin.
        self.resume = dict(resume or {})
        # Identifiants de l'echange une fois sauvegarde (None tant qu'il ne l'est pas, ou s'il ne
        # l'a jamais ete : tour arrete ou en erreur). Une page qui se rouvre s'en sert pour ne pas
        # redessiner un echange qu'elle a deja recharge depuis l'historique.
        self.ids: Optional[dict] = None
        self.termine_a: Optional[float] = None
        self._lignes: list[str] = []
        self._taille_octets = 0
        self._stockage_plafonne = False
        self._condition = threading.Condition()
        self._termine = False
        self._lecteurs = 0

    @property
    def termine(self) -> bool:
        with self._condition:
            return self._termine

    def nombre_evenements(self) -> int:
        with self._condition:
            return len(self._lignes)

    @property
    def taille_octets(self) -> int:
        with self._condition:
            return self._taille_octets

    @property
    def stockage_plafonne(self) -> bool:
        with self._condition:
            return self._stockage_plafonne

    def texte_partiel(self) -> str:
        """Texte deja affiche (evenements "reponse") : ce qu'une sauvegarde partielle conserve."""
        morceaux = []
        with self._condition:
            lignes = list(self._lignes)
        for ligne in lignes:
            if not ligne.startswith("data:"):
                continue
            try:
                evenement = json.loads(ligne[len("data:"):].strip())
            except ValueError:
                continue
            if isinstance(evenement, dict) and evenement.get("type") == "reponse" and isinstance(evenement.get("texte"), str):
                morceaux.append(evenement["texte"])
        return "".join(morceaux)

    def ajouter(self, ligne: str) -> None:
        ids = _ids_sauvegardes(ligne)
        # La ligne de fin et l'evenement meta restent toujours stockes : ils portent la
        # terminaison et les identifiants de l'echange sauvegarde.
        toujours = ligne == LIGNE_FIN or ids is not None
        with self._condition:
            if not toujours and self._taille_octets + len(ligne.encode("utf-8")) > MAX_OCTETS_TOUR_DETACHE:
                if not self._stockage_plafonne:
                    self._stockage_plafonne = True
                    logging.warning("Tour detache %s : stockage des lignes plafonne a %s octets.", self.id, MAX_OCTETS_TOUR_DETACHE)
                return
            self._lignes.append(ligne)
            self._taille_octets += len(ligne.encode("utf-8"))
            if ids is not None:
                self.ids = ids
            self._condition.notify_all()
        if self._persistance is not None:
            try:
                self._persistance.ajouter(ligne, ids)
            except Exception as e:
                logging.error("ERREUR persistance tour %s (ajout) : %s", self.id, e)

    def clore(self) -> None:
        with self._condition:
            if self._termine:
                return
            self._termine = True
            self.termine_a = time.monotonic()
            sans_lecteur = self._lecteurs == 0
            self._condition.notify_all()
        if self._persistance is not None:
            try:
                self._persistance.clore(self.ids)
            except Exception as e:
                logging.error("ERREUR persistance tour %s (cloture) : %s", self.id, e)
        if sans_lecteur and self._a_la_cloture is not None:
            try:
                self._a_la_cloture(self)
            except Exception as e:
                logging.error("ERREUR cloture tour %s (notification) : %s", self.id, e)

    def lire(self, depuis: int = 0, signe_vie: Optional[float] = None) -> Iterator[str]:
        """Rend les lignes a partir de la position `depuis`, puis attend les suivantes jusqu'a la
        fin du tour. `signe_vie` : delai en secondes apres lequel une ligne de commentaire SSE est
        envoyee si rien d'autre ne l'a ete (None : jamais, comportement du flux d'origine).

        Fermer ce generateur (connexion perdue) ne touche pas au tour : seul son lecteur s'arrete.
        """
        with self._condition:
            self._lecteurs += 1
        try:
            yield from self._lire_interne(depuis, signe_vie)
        finally:
            with self._condition:
                self._lecteurs = max(0, self._lecteurs - 1)

    def _lire_interne(self, depuis: int = 0, signe_vie: Optional[float] = None) -> Iterator[str]:
        position = max(0, int(depuis))
        dernier_envoi = time.monotonic()
        while True:
            with self._condition:
                if position >= len(self._lignes) and not self._termine:
                    self._condition.wait(timeout=_PAS_ATTENTE_SECONDES)
                # Lues dans le meme verrou : `fini` vrai avec des lignes encore a rendre n'arrive
                # qu'une fois, la boucle repasse ensuite par ici et trouve la liste vide.
                nouvelles = self._lignes[position:]
                fini = self._termine
            if nouvelles:
                position += len(nouvelles)
                dernier_envoi = time.monotonic()
                yield from nouvelles
                continue
            if fini:
                return
            if signe_vie is not None and time.monotonic() - dernier_envoi >= signe_vie:
                dernier_envoi = time.monotonic()
                yield LIGNE_SIGNE_VIE


_verrou = threading.Lock()
_tours: dict[str, TourDetache] = {}
_dernier_par_conversation: dict[tuple[str, str], str] = {}


def _oublier_sous_verrou(tour_id: str) -> None:
    tour = _tours.pop(tour_id, None)
    if tour is None:
        return
    cle = (tour.user_id, tour.conversation_id)
    if _dernier_par_conversation.get(cle) == tour_id:
        del _dernier_par_conversation[cle]


def _purger_sous_verrou(maintenant: float) -> None:
    """Oublie les tours termines depuis trop longtemps, puis les plus anciens si trop restent."""
    duree = CONSERVATION_TOUR_DETACHE.total_seconds()
    termines = sorted(
        (t for t in _tours.values() if t.termine_a is not None),
        key=lambda t: t.termine_a,
    )
    a_oublier = {t.id for t in termines if maintenant - t.termine_a > duree}
    exces = len(termines) - MAX_TOURS_DETACHES_CONSERVES
    if exces > 0:
        a_oublier.update(t.id for t in termines[:exces])
    restants = [t for t in termines if t.id not in a_oublier]
    total = sum(t.taille_octets for t in restants)
    for t in restants:  # du plus ancien au plus recent
        if total <= MAX_OCTETS_TOURS_DETACHES_CONSERVES:
            break
        a_oublier.add(t.id)
        total -= t.taille_octets
    for tour_id in a_oublier:
        _oublier_sous_verrou(tour_id)


def purger_tours_termines() -> None:
    """Purge periodique : sans elle, la memoire des tours termines ne redescend que lorsqu'un
    nouveau tour demarre."""
    with _verrou:
        _purger_sous_verrou(time.monotonic())


_purge_demarree = False


def _demarrer_purge_periodique() -> None:
    global _purge_demarree
    with _verrou:
        if _purge_demarree:
            return
        _purge_demarree = True

    def boucle():
        while True:
            time.sleep(INTERVALLE_PURGE_TOURS_DETACHES.total_seconds())
            try:
                purger_tours_termines()
            except Exception as e:  # la purge ne doit jamais faire tomber le processus
                logging.error("ERREUR purge des tours detaches : %s", e)

    threading.Thread(target=boucle, name="purge-tours-detaches", daemon=True).start()


def _sauvegarder_partielle(tour: TourDetache, sauvegarder_partielle) -> None:
    """Sauvegarde la reponse partielle d'un tour casse avant sa purge, si l'echange n'a pas
    deja ete sauvegarde (aucun evenement meta recu). Un echec laisse le tour en memoire pour
    les purges suivantes : la conservation normale s'applique, rien n'est perdu aussitot."""
    if sauvegarder_partielle is None or tour.ids is not None:
        return
    texte = tour.texte_partiel().strip()
    if not texte:
        return
    try:
        ids = sauvegarder_partielle(texte)
    except Exception as e:
        logging.error("ERREUR sauvegarde partielle tour %s : %s", tour.id, e)
        return
    if ids:
        tour.ids = ids
        tour.ajouter(f"data: {json.dumps({'type': 'meta', **ids})}\n\n")


def _executer(tour: TourDetache, fabrique: Callable[[], Iterable[str]], message_erreur: str, sauvegarder_partielle=None) -> None:
    try:
        for ligne in fabrique():
            tour.ajouter(ligne)
    except Exception as e:
        # Le generateur du chat attrape deja ses propres erreurs : on n'arrive ici que si
        # quelque chose a casse avant sa premiere ligne ou autour de lui.
        logging.error("ERREUR tour detache %s (compte %s) : %s", tour.id, tour.user_id, e)
        _sauvegarder_partielle(tour, sauvegarder_partielle)
        tour.ajouter(f"data: {json.dumps({'type': 'reponse', 'texte': message_erreur})}\n\n")
        tour.ajouter(LIGNE_FIN)
    finally:
        tour.clore()


def demarrer(
    user_id: str,
    conversation_id: Optional[str],
    fabrique: Callable[[], Iterable[str]],
    resume: Optional[dict] = None,
    message_erreur: str = "Une erreur est survenue, réessaie dans un instant.",
    fabrique_persistance: Optional[Callable] = None,
    a_la_cloture: Optional[Callable] = None,
    sauvegarder_partielle=None,
) -> TourDetache:
    """Lance le travail dans son propre thread et renvoie le tour, deja lisible.

    `fabrique` rend l'iterable de lignes SSE (api/chat.py:_evenements_sse). Le contexte de la
    requete est copie dans le thread : sans lui, ce que le travail lisait par variable de
    contexte dans le thread de la requete disparaitrait.
    `fabrique_persistance(tour)` (optionnel) rend la couche durable du tour
    (core/persistance_tours.py) : elle recoit chaque ligne et la cloture.
    `a_la_cloture(tour)` est appele si le tour se termine sans aucun lecteur rattache.
    """
    _demarrer_purge_periodique()
    tour = TourDetache(user_id, conversation_id, resume, a_la_cloture=a_la_cloture)
    if fabrique_persistance is not None:
        try:
            tour._persistance = fabrique_persistance(tour)
            if tour._persistance is not None:
                tour._persistance.demarrer()
        except Exception as e:
            logging.error("ERREUR demarrage persistance tour %s : %s", tour.id, e)
            tour._persistance = None
    with _verrou:
        _purger_sous_verrou(time.monotonic())
        _tours[tour.id] = tour
        if conversation_id:
            _dernier_par_conversation[(user_id, conversation_id)] = tour.id
    contexte = contextvars.copy_context()
    fil = threading.Thread(
        target=contexte.run,
        args=(_executer, tour, fabrique, message_erreur, sauvegarder_partielle),
        name=f"tour-detache-{tour.id[:8]}",
        daemon=True,
    )
    fil.start()
    return tour


def trouver(tour_id: str, user_id: str) -> Optional[TourDetache]:
    """Le tour `tour_id`, seulement s'il appartient bien a `user_id`."""
    with _verrou:
        tour = _tours.get(tour_id)
    return tour if tour is not None and tour.user_id == user_id else None


def dernier_de_conversation(user_id: str, conversation_id: str) -> Optional[TourDetache]:
    """Le tour le plus recent de cette conversation pour ce compte, en cours ou termine."""
    with _verrou:
        tour_id = _dernier_par_conversation.get((user_id, conversation_id))
        tour = _tours.get(tour_id) if tour_id else None
    return tour if tour is not None and tour.user_id == user_id else None


def oublier_utilisateur(user_id: str) -> int:
    """Retire tous les tours d'un compte du registre (suppression du compte). Un travail encore
    en cours finit tout seul, mais plus personne ne peut s'y rattacher. Renvoie leur nombre."""
    with _verrou:
        ids = [t.id for t in _tours.values() if t.user_id == user_id]
        for tour_id in ids:
            _oublier_sous_verrou(tour_id)
    return len(ids)
