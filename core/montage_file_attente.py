"""File d'attente du montage vidéo (demande de Bourama, 03/11/2026).

Un montage est lourd (ffmpeg, rendu Remotion). Le serveur n'en traite que
quelques-uns à la fois, les autres attendent leur tour au lieu de faire
planter la machine quand plusieurs personnes montent en même temps.

Réglages par variables Railway :
  MONTAGE_SIMULTANES   nombre de montages en même temps (défaut 2)
  MONTAGE_ATTENTE_MAX_S  attente maximale d'une place, en secondes (défaut 600)
"""
import os
import threading


class AttenteTropLongue(Exception):
    pass


def _entier(nom: str, defaut: int) -> int:
    try:
        return max(1, int(os.environ.get(nom, defaut)))
    except (TypeError, ValueError):
        return defaut


SIMULTANES = _entier("MONTAGE_SIMULTANES", 2)
ATTENTE_MAX_S = _entier("MONTAGE_ATTENTE_MAX_S", 600)

_places = threading.BoundedSemaphore(SIMULTANES)


def prendre_place() -> None:
    """Attend une place libre. Lève AttenteTropLongue si l'attente dépasse le maximum."""
    if not _places.acquire(timeout=ATTENTE_MAX_S):
        raise AttenteTropLongue(
            "Beaucoup de montages vidéo sont en cours, la file est trop longue. Réessaie dans quelques minutes."
        )


def liberer_place() -> None:
    _places.release()
