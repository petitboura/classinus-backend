"""
Suivi des rendus vidéo d'animations (07/10/2026, demande Bourama).

Une demande crée un travail. Les travaux attendent leur tour dans une file
(TRAVAUX_SIMULTANES rendus à la fois, le rendu occupe beaucoup le
processeur), puis chacun tourne dans un processus isolé
(core/rendu_animation_processus.py) que l'on peut tuer à tout moment :
annulation par l'utilisateur ou délai maximal dépassé.

L'état des travaux vit en mémoire de l'API. C'est volontaire et suffisant
tant que le service n'a qu'un seul processus (c'est le cas sur Railway :
une réplique, un seul uvicorn). Une vidéo prête est un fichier temporaire
gardé CONSERVATION_S secondes, jamais conservé au delà. Si l'API devait
tourner sur plusieurs répliques, il faudrait déplacer cet état et les
fichiers vers un stockage partagé (R2 par exemple).
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from core.erreurs import MESSAGES_FR
from core.rendu_animation_constantes import (
    ATTENTE_MAX,
    CONSERVATION_S,
    DELAI_CHARGEMENT_S,
    DELAI_TOTAL_S,
    DOSSIER_TRAVAIL,
    DUREE_MAX_S,
    FICHIER_THREE,
    FORMATS,
    IMAGES_PAR_SECONDE,
    MAINTIEN_FIN_S,
    SCRIPT_PROCESSUS,
    TAILLE_MAX_DOCUMENT_OCTETS,
    TRAVAUX_SIMULTANES,
)

CODE_SORTIE_INDISPONIBLE = 4  # voir core/rendu_animation_processus.py


class ErreurRendu(Exception):
    def __init__(self, statut_http: int, code: str):
        super().__init__(code)
        self.statut_http = statut_http
        self.code = code


@dataclass
class Travail:
    id: str
    utilisateur_id: str
    format: str
    statut: str = "attente"  # attente, en_cours, pret, echec, annule
    progression: float = 0.0
    code_erreur: str | None = None
    chemin_video: Path | None = None
    taille_octets: int = 0
    cree_a: float = field(default_factory=time.time)
    termine_a: float | None = None
    annule: threading.Event = field(default_factory=threading.Event)


_verrou = threading.Lock()
_travaux: dict[str, Travail] = {}
_executeur = ThreadPoolExecutor(max_workers=TRAVAUX_SIMULTANES, thread_name_prefix="rendu-animation")


def _dossier(travail_id: str) -> Path:
    return DOSSIER_TRAVAIL / travail_id


def _supprimer_fichiers(travail_id: str) -> None:
    shutil.rmtree(_dossier(travail_id), ignore_errors=True)


def nettoyer_anciens_fichiers() -> None:
    """Au démarrage : retire les restes d'un processus précédent."""
    if not DOSSIER_TRAVAIL.exists():
        return
    limite = time.time() - CONSERVATION_S
    for enfant in DOSSIER_TRAVAIL.iterdir():
        try:
            if enfant.stat().st_mtime < limite:
                shutil.rmtree(enfant, ignore_errors=True)
        except OSError:
            pass


def _purger_termines() -> None:
    """À appeler avec le verrou pris : oublie les travaux terminés trop anciens."""
    limite = time.time() - CONSERVATION_S
    for travail_id, t in list(_travaux.items()):
        if t.termine_a is not None and t.termine_a < limite:
            _travaux.pop(travail_id, None)
            _supprimer_fichiers(travail_id)


def _actif(t: Travail) -> bool:
    return t.statut in ("attente", "en_cours")


def creer_travail(utilisateur_id: str, format_video: str, document_html: str) -> Travail:
    if format_video not in FORMATS:
        raise ErreurRendu(400, "RENDU_VIDEO_FORMAT_INVALIDE")
    if len(document_html.encode("utf-8")) > TAILLE_MAX_DOCUMENT_OCTETS:
        raise ErreurRendu(413, "RENDU_VIDEO_DOCUMENT_TROP_LOURD")
    # Garde-fou simple : le document doit être celui du lecteur d'animation
    # de l'appli (il porte sa configuration), pas une page quelconque.
    if "window.__ANIM_CONF" not in document_html:
        raise ErreurRendu(400, "RENDU_VIDEO_DOCUMENT_INVALIDE")

    with _verrou:
        _purger_termines()
        if any(t.utilisateur_id == utilisateur_id and _actif(t) for t in _travaux.values()):
            raise ErreurRendu(409, "RENDU_VIDEO_DEJA_EN_COURS")
        if sum(1 for t in _travaux.values() if t.statut == "attente") >= ATTENTE_MAX:
            raise ErreurRendu(503, "RENDU_VIDEO_OCCUPE")
        travail = Travail(id=uuid.uuid4().hex, utilisateur_id=utilisateur_id, format=format_video)
        _travaux[travail.id] = travail

    try:
        dossier = _dossier(travail.id)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "document.html").write_text(document_html, encoding="utf-8")
        _executeur.submit(_executer, travail)
    except Exception:
        with _verrou:
            _travaux.pop(travail.id, None)
        _supprimer_fichiers(travail.id)
        logging.exception("Impossible de préparer le rendu vidéo (utilisateur %s)", utilisateur_id)
        raise ErreurRendu(500, "RENDU_VIDEO_ECHEC")
    return travail


def lire_travail(travail_id: str, utilisateur_id: str) -> Travail:
    with _verrou:
        _purger_termines()
        t = _travaux.get(travail_id)
    # Même réponse qu'un travail inexistant : on ne révèle pas qu'il existe
    # chez quelqu'un d'autre.
    if t is None or t.utilisateur_id != utilisateur_id:
        raise ErreurRendu(404, "RENDU_VIDEO_INTROUVABLE")
    return t


def annuler_travail(travail_id: str, utilisateur_id: str) -> None:
    t = lire_travail(travail_id, utilisateur_id)
    t.annule.set()
    if not _actif(t):
        with _verrou:
            _travaux.pop(travail_id, None)
        _supprimer_fichiers(travail_id)


def serialiser(t: Travail) -> dict:
    corps = {"id": t.id, "statut": t.statut, "progression": round(t.progression, 3), "format": t.format}
    if t.code_erreur:
        corps["code_erreur"] = t.code_erreur
        corps["message_erreur"] = MESSAGES_FR.get(t.code_erreur, MESSAGES_FR["ERREUR_INCONNUE"])
    if t.statut == "pret":
        corps["taille_octets"] = t.taille_octets
    return corps


def _environnement_minimal(dossier: Path) -> dict:
    """Le processus de rendu ne reçoit aucun secret de l'API."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(dossier),
        "LANG": "C.UTF-8",
    }
    for cle in ("PLAYWRIGHT_BROWSERS_PATH", "XDG_CACHE_HOME"):
        if os.environ.get(cle):
            env[cle] = os.environ[cle]
    return env


def _terminer(t: Travail, statut: str, code_erreur: str | None = None) -> None:
    t.statut = statut
    t.code_erreur = code_erreur
    t.termine_a = time.time()


def _surveiller(proc: subprocess.Popen, t: Travail, etat: dict) -> None:
    """Tue le processus (et le navigateur qu'il a lancé) si l'utilisateur
    annule ou si le délai maximal est dépassé."""
    limite = time.monotonic() + DELAI_TOTAL_S
    while proc.poll() is None:
        if t.annule.is_set() or time.monotonic() > limite:
            etat["delai"] = not t.annule.is_set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            return
        time.sleep(0.5)


def _executer(t: Travail) -> None:
    if t.annule.is_set():
        _terminer(t, "annule")
        _supprimer_fichiers(t.id)
        return

    t.statut = "en_cours"
    dossier = _dossier(t.id)
    sortie = dossier / "video.mp4"
    largeur, hauteur = FORMATS[t.format]
    commande = [
        sys.executable, str(SCRIPT_PROCESSUS),
        "--document", str(dossier / "document.html"),
        "--sortie", str(sortie),
        "--largeur", str(largeur),
        "--hauteur", str(hauteur),
        "--fps", str(IMAGES_PAR_SECONDE),
        "--duree-max", str(DUREE_MAX_S),
        "--maintien-fin", str(MAINTIEN_FIN_S),
        "--delai-chargement", str(DELAI_CHARGEMENT_S),
        "--three", str(FICHIER_THREE),
    ]
    etat = {"delai": False}
    code_connu: str | None = None
    try:
        with open(dossier / "erreurs.log", "wb") as journal:
            proc = subprocess.Popen(
                commande,
                stdout=subprocess.PIPE,
                stderr=journal,
                text=True,
                cwd=str(dossier),
                env=_environnement_minimal(dossier),
                start_new_session=True,  # groupe à part : on tue aussi le navigateur
            )
            threading.Thread(target=_surveiller, args=(proc, t, etat), daemon=True).start()
            for ligne in proc.stdout:
                try:
                    message = json.loads(ligne)
                except ValueError:
                    continue
                if isinstance(message.get("p"), (int, float)):
                    t.progression = max(0.0, min(0.99, float(message["p"])))
                if isinstance(message.get("erreur"), str):
                    code_connu = message["erreur"]
            code_sortie = proc.wait()
    except Exception:
        logging.exception("Rendu vidéo : le processus n'a pas pu démarrer (utilisateur %s)", t.utilisateur_id)
        _terminer(t, "echec", "RENDU_VIDEO_ECHEC")
        _supprimer_fichiers(t.id)
        return

    if t.annule.is_set():
        _terminer(t, "annule")
        _supprimer_fichiers(t.id)
    elif etat["delai"]:
        logging.error("Rendu vidéo : délai de %s s dépassé (utilisateur %s)", DELAI_TOTAL_S, t.utilisateur_id)
        _terminer(t, "echec", "RENDU_VIDEO_ECHEC")
        _supprimer_fichiers(t.id)
    elif code_sortie == 0 and sortie.exists() and sortie.stat().st_size > 0:
        t.chemin_video = sortie
        t.taille_octets = sortie.stat().st_size
        t.progression = 1.0
        _terminer(t, "pret")
        (dossier / "document.html").unlink(missing_ok=True)
    else:
        if code_sortie == CODE_SORTIE_INDISPONIBLE:
            code_connu = "RENDU_VIDEO_INDISPONIBLE"
        try:
            reste = (dossier / "erreurs.log").read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            reste = ""
        logging.error(
            "Rendu vidéo en échec (code %s, erreur %s, utilisateur %s) : %s",
            code_sortie, code_connu, t.utilisateur_id, reste,
        )
        _terminer(t, "echec", code_connu or "RENDU_VIDEO_ECHEC")
        _supprimer_fichiers(t.id)
