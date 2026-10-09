"""
Canal en direct : actions et lecture de l'ecran PC pour la boucle de mission
(09/10/2026, chantier Jev, lot 2b).

Les outils du PC (core/outils_action_agent_pc.py) sont des outils MCP : ils ne
se servent du contexte MCP que pour savoir quel etudiant et quelle conversation,
et la vraie action est une demande au processus Electron
(core/canal_agent_applicatif.py, demander_action_systeme). Ce module appelle
directement cette demande, sans passer par un contexte MCP, et garde les memes
regles que les outils :

- une seule action PC a la fois par etudiant : le verrou est le MEME que celui
  des outils MCP (_verrous_actions_pc), donc une action de la mission et une
  action d'un tour de chat ne s'executent jamais en meme temps ;
- apres une action reussie, un court delai laisse la fenetre se stabiliser, puis
  une lecture de l'ecran est renvoyee avec le resultat (memes delais que les
  outils, reglables par les memes variables d'environnement) ;
- cliquer_ecran et appuyer_touches ne comptent comme reussis que si le
  processus Electron confirme "ok" ; taper_clavier et ouvrir_application
  comptent comme reussis sans erreur renvoyee (comportement des outils) ;
- une lecture reussie compte comme "premiere lecture" de la conversation
  (verrou de core/lecture_ecran_continue.py), pour que les outils MCP d'un
  tour de chat ne la redemandent pas.

Aucun contenu d'ecran ni message technique du processus Electron dans les logs.

La fabrique creer_actions_pc_reelles importe les modules du serveur a l'appel
seulement : la classe ActionsPCReelles, elle, se teste avec de fausses demandes.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core import lecture_ecran_continue

OUTILS_AUTORISES = ("cliquer_ecran", "appuyer_touches", "taper_clavier", "ouvrir_application")
# Outils dont le succes exige {"ok": true} dans la reponse du processus Electron.
OUTILS_AVEC_CONFIRMATION = frozenset({"cliquer_ecran", "appuyer_touches"})

Demander = Callable[[str, str, dict], Awaitable[Any]]


@dataclass(frozen=True)
class ResultatAction:
    reussi: bool
    # Lecture brute de l'ecran juste apres l'action (None : action echouee ou lecture impossible).
    lecture_apres: dict | None = None


class ActionsPCReelles:
    def __init__(
        self,
        user_id: str,
        conversation_id: str | None,
        *,
        demander: Demander,
        parametres_lecture: dict,
        delais: dict[str, float],
        verrous: dict[str, asyncio.Lock],
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._user_id = str(user_id)
        self._conversation_id = conversation_id
        self._demander = demander
        self._parametres_lecture = dict(parametres_lecture)
        self._delais = dict(delais)
        self._verrous = verrous
        self._dormir = dormir

    async def lire(self) -> dict | None:
        """Lecture brute de la fenetre au premier plan, ou None si elle n'a pas abouti."""
        resultat = await self._demander(
            self._user_id,
            "lire_ecran",
            {**self._parametres_lecture, "automatique": True, "zone": "fenetre"},
        )
        if not isinstance(resultat, dict) or resultat.get("erreur"):
            logging.warning("Mission : la lecture de l'ecran PC n'a pas abouti.")
            return None
        lecture_ecran_continue.marquer_lu(self._user_id, self._conversation_id)
        return resultat

    async def executer(self, outil: str, parametres: dict) -> ResultatAction:
        """
        Execute UNE action, sous le verrou de l'etudiant (attend son tour si une
        autre action PC est en cours), puis relit l'ecran.
        """
        if outil not in OUTILS_AUTORISES:
            raise ValueError(f"Outil PC inconnu pour une mission : {outil!r}")
        verrou = self._verrous.setdefault(self._user_id, asyncio.Lock())
        async with verrou:
            resultat = await self._demander(self._user_id, outil, parametres)
            if resultat is None:
                logging.warning(f"Mission : {outil} sans reponse du PC (application PC fermee ?).")
                return ResultatAction(False)
            if isinstance(resultat, dict) and resultat.get("erreur"):
                logging.warning(f"Mission : {outil} refuse par le PC.")
                return ResultatAction(False)
            if outil in OUTILS_AVEC_CONFIRMATION and not (isinstance(resultat, dict) and resultat.get("ok") is True):
                logging.warning(f"Mission : {outil} non confirme par le PC.")
                return ResultatAction(False)
            await self._dormir(self._delais.get(outil, 0.0))
            lecture = await self.lire()
        return ResultatAction(True, lecture)


def creer_actions_pc_reelles(user_id: str, conversation_id: str | None) -> ActionsPCReelles:
    """
    Actions branchees sur le vrai canal : reprend les limites de lecture, les
    delais et le verrou des outils PC pour qu'il n'y ait qu'une seule source de
    verite.
    """
    from core import outils_action_agent_pc as pc
    from core.canal_agent_applicatif import demander_action_systeme

    return ActionsPCReelles(
        user_id,
        conversation_id,
        demander=demander_action_systeme,
        parametres_lecture={
            "nb_max_elements": pc.NB_MAX_ELEMENTS_LECTURE_ECRAN,
            "nb_max_fenetres": pc.NB_MAX_FENETRES_LECTURE_ECRAN,
            "longueur_max_nom": pc.LONGUEUR_MAX_NOM_LECTURE_ECRAN,
            "longueur_max_valeur": pc.LONGUEUR_MAX_VALEUR_LECTURE_ECRAN,
            "profondeur_max": pc.PROFONDEUR_MAX_LECTURE_ECRAN,
            "delai_max_ms": pc.DELAI_MAX_LECTURE_ECRAN_MS,
        },
        delais={
            "cliquer_ecran": pc.DELAI_APRES_CLIC_SECONDES,
            "appuyer_touches": pc.DELAI_APRES_CLAVIER_SECONDES,
            "taper_clavier": pc.DELAI_APRES_CLAVIER_SECONDES,
            "ouvrir_application": pc.DELAI_APRES_OUVERTURE_SECONDES,
        },
        verrous=pc._verrous_actions_pc,
    )
