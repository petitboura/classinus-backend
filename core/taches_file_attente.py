"""Reservation atomique et reprise des taches d'arriere-plan persistantes."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from core.plafonds_reglables import AGE_TACHE_PERIMEE

_INTERVALLE_RECUPERATION_S = 60.0
_AGE_TACHE_PERIMEE = AGE_TACHE_PERIMEE
_derniere_recuperation: dict[str, float] = {}


def recycler_taches_perimees(client, table: str, colonne_statut: str, colonne_horodatage: str) -> int:
    """Reprend les traitements abandonnes sans toucher aux jobs actifs."""
    cle = f"{table}:{colonne_statut}:{colonne_horodatage}"
    maintenant_mono = time.monotonic()
    if maintenant_mono - _derniere_recuperation.get(cle, 0.0) < _INTERVALLE_RECUPERATION_S:
        return 0
    _derniere_recuperation[cle] = maintenant_mono
    seuil = (datetime.now(timezone.utc) - _AGE_TACHE_PERIMEE).isoformat()
    remis = 0
    for horodatage_null in (False, True):
        try:
            requete = client.table(table).update({colonne_statut: "en_attente"}).eq(colonne_statut, "en_cours")
            if horodatage_null:
                requete = requete.is_(colonne_horodatage, "null")
            else:
                requete = requete.lt(colonne_horodatage, seuil)
            res = requete.select("id").execute()
            remis += len(res.data or [])
        except Exception as e:
            logging.error("ERREUR reprise taches perimees (%s.%s): %s", table, colonne_statut, e)
    if remis:
        logging.warning("Reprise de %d tache(s) perimee(s) dans %s (%s).", remis, table, colonne_statut)
    return remis
