"""Persistance en base des tours de chat detaches (31/10/2026, demande de Bourama).

core/tours_detaches.py garde les tours en memoire du processus : rapide, mais un
redemarrage (deploiement Render) perdait le tour en cours et son texte partiel.
Ce module est la couche durable derriere : il ecrit le tour et ses lignes SSE
par paquets (jamais une requete par evenement) dans tours_chat_persistes /
tours_chat_evenements_persistes (migration 2026_10_31_tours_chat_persistes.sql).

Principes :
- Aucune ecriture ne doit casser le chat : toute erreur de base est journalisee
  et avalee, la memoire reste la source rapide tant que le processus vit.
- L'ecriture se fait dans un thread dedie par tour, alimente par une file :
  le thread de travail n'attend jamais la base.
- A la cloture, le reste des lignes est ecrit puis le statut passe "termine".
- Au redemarrage, marquer_tours_orphelins() passe "interrompu" les tours
  "en_cours" sans signe de vie (maj_le) recent : le texte partiel reste
  rejouable via lire_tour_persiste() et l'interface propose Continuer.
"""
import json
import logging
import queue
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from constantes_agent import supabase
from core.plafonds_reglables import (
    AGE_TOUR_SANS_SIGNE_VIE,
    CONSERVATION_TOURS_PERSISTES,
    DELAI_ECRITURE_TOUR_SECONDES,
    TAILLE_PAQUET_TOUR,
)

TABLE_TOURS = "tours_chat_persistes"
TABLE_EVENEMENTS = "tours_chat_evenements_persistes"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistanceTour:
    """Ecrit un tour en base, par paquets, depuis un thread dedie.

    Interface consommee par core/tours_detaches.py : demarrer(), ajouter(),
    clore(). Chaque methode est sans exception pour l'appelant.
    """

    def __init__(self, tour_id: str, user_id: str, conversation_id: Optional[str], resume: Optional[dict]):
        self.tour_id = tour_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.resume = dict(resume or {})
        self._file: "queue.Queue" = queue.Queue()
        self._fil: Optional[threading.Thread] = None
        self._actif = False

    # -- cote thread de travail -------------------------------------------------
    def demarrer(self) -> None:
        self._actif = True
        self._fil = threading.Thread(
            target=self._boucle_ecriture, name=f"persistance-tour-{self.tour_id[:8]}", daemon=True
        )
        self._fil.start()

    def ajouter(self, ligne: str, ids: Optional[dict] = None) -> None:
        if self._actif:
            self._file.put(("ligne", ligne, ids))

    def clore(self, ids: Optional[dict] = None) -> None:
        if not self._actif:
            return
        self._actif = False
        self._file.put(("clore", None, ids))

    # -- thread d'ecriture --------------------------------------------------------
    def _boucle_ecriture(self) -> None:
        try:
            supabase.table(TABLE_TOURS).insert(
                {
                    "id": self.tour_id,
                    "user_id": self.user_id,
                    "conversation_id": self.conversation_id,
                    "statut": "en_cours",
                    "resume": self.resume,
                    "nb_evenements": 0,
                    "maj_le": _maintenant(),
                }
            ).execute()
        except Exception as e:
            logging.error("ERREUR persistance tour %s (creation) : %s", self.tour_id, e)
            # Sans ligne de tour, les paquets violeraient la cle etrangere : on continue
            # a vider la file sans rien ecrire, le tour vit en memoire comme avant.
            self._vider_sans_ecrire()
            return

        paquet: list[str] = []
        a_partir_de = 0
        ids_courants: Optional[dict] = None

        def ecrire_paquet(statut_final: Optional[str] = None) -> None:
            nonlocal a_partir_de
            try:
                if paquet:
                    supabase.table(TABLE_EVENEMENTS).insert(
                        {"tour_id": self.tour_id, "a_partir_de": a_partir_de, "lignes": list(paquet)}
                    ).execute()
                    a_partir_de += len(paquet)
                    paquet.clear()
                maj = {
                    "nb_evenements": a_partir_de,
                    "maj_le": _maintenant(),
                }
                if ids_courants is not None:
                    maj["ids_echange"] = ids_courants
                if statut_final is not None:
                    maj["statut"] = statut_final
                    maj["termine_le"] = _maintenant()
                supabase.table(TABLE_TOURS).update(maj).eq("id", self.tour_id).execute()
            except Exception as e:
                logging.error("ERREUR persistance tour %s (paquet) : %s", self.tour_id, e)

        while True:
            try:
                action, ligne, ids = self._file.get(timeout=DELAI_ECRITURE_TOUR_SECONDES)
            except queue.Empty:
                if paquet:
                    ecrire_paquet()
                continue
            if ids is not None:
                ids_courants = ids
            if action == "clore":
                ecrire_paquet(statut_final="termine")
                return
            paquet.append(ligne)
            if len(paquet) >= TAILLE_PAQUET_TOUR:
                ecrire_paquet()

    def _vider_sans_ecrire(self) -> None:
        while True:
            action, _ligne, _ids = self._file.get()
            if action == "clore":
                return


def _lignes_depuis_paquets(lignes_paquets: list[dict], depuis: int) -> list[str]:
    lignes: list[str] = []
    for paquet in sorted(lignes_paquets, key=lambda p: p.get("a_partir_de") or 0):
        brut = paquet.get("lignes") or []
        if isinstance(brut, str):
            try:
                brut = json.loads(brut)
            except ValueError:
                brut = []
        lignes.extend(str(l) for l in brut)
    return lignes[max(0, depuis):]


def lire_tour_persiste(tour_id: str, user_id: str) -> Optional[dict]:
    """Le tour persiste (statut, resume, ids, lignes), seulement pour son compte."""
    try:
        res = (
            supabase.table(TABLE_TOURS)
            .select("id, conversation_id, statut, resume, ids_echange, nb_evenements")
            .eq("id", tour_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        lignes_tour = res.data or []
        if not lignes_tour:
            return None
        tour = lignes_tour[0]
        ev = (
            supabase.table(TABLE_EVENEMENTS)
            .select("a_partir_de, lignes")
            .eq("tour_id", tour_id)
            .order("a_partir_de")
            .execute()
        )
        tour = dict(tour)
        tour["lignes"] = _lignes_depuis_paquets(ev.data or [], 0)
        return tour
    except Exception as e:
        logging.error("ERREUR lecture tour persiste %s : %s", tour_id, e)
        return None


def dernier_tour_persiste(user_id: str, conversation_id: str) -> Optional[dict]:
    """Le dernier tour persiste de cette conversation (sans ses lignes)."""
    marquer_tours_orphelins_une_fois()
    try:
        res = (
            supabase.table(TABLE_TOURS)
            .select("id, statut, resume, ids_echange, nb_evenements")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .order("cree_le", desc=True)
            .limit(1)
            .execute()
        )
        lignes = res.data or []
        return lignes[0] if lignes else None
    except Exception as e:
        logging.error("ERREUR lecture dernier tour persiste (conversation %s) : %s", conversation_id, e)
        return None


_marquage_fait = threading.Event()


def marquer_tours_orphelins_une_fois() -> int:
    """Premier appel du processus seulement : apres un redemarrage, c'est le premier
    rattachement qui declenche le marquage des orphelins (voir marquer_tours_orphelins)."""
    if _marquage_fait.is_set():
        return 0
    _marquage_fait.set()
    return marquer_tours_orphelins()


def marquer_tours_orphelins() -> int:
    """Au redemarrage : les tours restes "en_cours" sans signe de vie recent sont
    "interrompu" (processus mort en plein travail), et les vieux tours finis sont
    purges. Renvoie le nombre d'orphelins marques. Sans exception pour l'appelant."""
    try:
        seuil = (datetime.now(timezone.utc) - AGE_TOUR_SANS_SIGNE_VIE).isoformat()
        res = (
            supabase.table(TABLE_TOURS)
            .update({"statut": "interrompu", "termine_le": _maintenant()})
            .eq("statut", "en_cours")
            .lt("maj_le", seuil)
            .execute()
        )
        marques = len(res.data or [])
        if marques:
            logging.warning("Tours orphelins marques interrompus au demarrage : %d", marques)
        limite_purge = (datetime.now(timezone.utc) - CONSERVATION_TOURS_PERSISTES).isoformat()
        supabase.table(TABLE_TOURS).delete().neq("statut", "en_cours").lt("cree_le", limite_purge).execute()
        return marques
    except Exception as e:
        logging.error("ERREUR marquage tours orphelins : %s", e)
        return 0
