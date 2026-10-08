"""
Canal en direct : detection de boucle sans progres (08/10/2026, chantier Jev,
lot 1, principe valide par Bourama).

Une boucle, c'est la meme action sur la meme cible, repetee depuis le meme
etat d'ecran. Deux formes sont detectees, a partir du journal de tache
(core/journal_tache_canal.py) et des empreintes d'ecran (core/empreinte_ecran.py) :

- repetition (periode 1) : A, A, A... chaque fois depuis le meme ecran ;
- cycle (periode 2) : A, B, A, B... ou l'ecran revient au meme etat un tour
  sur deux (ce qui couvre aussi un bouton bascule clique plusieurs fois).

Ce qui n'est PAS une boucle : repeter une action quand l'ecran a change entre
temps (cliquer "Suivant" dans un formulaire). La condition "meme ecran" evite
ces faux positifs. Une empreinte inconnue (None) ne prouve rien : elle coupe la
serie, jamais elle ne la prolonge.

Deux reactions, decidees mecaniquement par le backend :
- SANS_EFFET : premier signal. Il faut un tour d'escalade du grand modele,
  avec l'information "cette action vient d'etre tentee sans effet".
- BLOQUEE : le grand modele a lui-meme repete le motif apres l'escalade. Il faut
  arreter, et dire a l'etudiant que la tache est bloquee (niveau 3), puis Jev ne
  reprend pas la main avant sa reponse.

Le nombre de repetitions n'est pas fixe : valeur de depart reglable
(CLASSINUS_BOUCLE_REPETITIONS), a ajuster apres de vrais tests.

Complementaire de core/boucle_agent.py (_detecter_appel_repete), qui ne regarde
que des appels identiques consecutifs dans la boucle de chat normale, sans
etat d'ecran ni alternance. Cette detection-ci sert la boucle d'orchestration du
canal en direct.

Module pur : aucun etat, aucun branchement dans le reste de l'application.
"""

import os
from dataclasses import dataclass
from enum import Enum

from core.journal_tache_canal import AUTEUR_GRAND_MODELE, GENRE_ACTION, EntreeJournal

# Nombre de fois que le motif doit etre vu pour etre signale (A, A = 2 ; A, B, A, B = 2).
REPETITIONS_PAR_DEFAUT = int(os.environ.get("CLASSINUS_BOUCLE_REPETITIONS", "2"))

PERIODES_SURVEILLEES = (1, 2)


class Verdict(str, Enum):
    AUCUNE = "aucune"
    SANS_EFFET = "sans_effet"
    BLOQUEE = "bloquee"


MOTIF_REPETITION = "repetition"
MOTIF_CYCLE = "cycle"


@dataclass(frozen=True)
class ResultatBoucle:
    verdict: Verdict
    # "repetition", "cycle", ou "" quand il n'y a pas de boucle.
    motif: str = ""
    # Nombre d'actions consecutives qui forment la boucle (0 sans boucle).
    longueur: int = 0


def _cle_action(entree: EntreeJournal) -> tuple[str, str]:
    return (entree.outil, entree.cible)


def _longueur_serie(actions: list[EntreeJournal], periode: int) -> int:
    """
    Nombre d'actions en fin de liste qui reproduisent le motif de `periode`
    actions, depuis le meme etat d'ecran : chaque action a meme (outil, cible)
    et meme empreinte d'ecran avant que celle qui la precede de `periode` rangs.
    0 si la serie est trop courte pour contenir une repetition.
    """
    n = len(actions)
    if n <= periode:
        return 0
    repetees = 0
    for i in range(n - 1, periode - 1, -1):
        courante, precedente = actions[i], actions[i - periode]
        if courante.empreinte_avant is None or precedente.empreinte_avant is None:
            break
        if _cle_action(courante) != _cle_action(precedente):
            break
        if courante.empreinte_avant != precedente.empreinte_avant:
            break
        repetees += 1
    if repetees == 0:
        return 0
    return repetees + periode


def analyser(entrees: list[EntreeJournal], repetitions: int | None = None) -> ResultatBoucle:
    """
    Analyse la fin du journal. Renvoie AUCUNE, SANS_EFFET ou BLOQUEE.

    BLOQUEE seulement si le motif a ete prolonge APRES le seuil par une action
    decidee par le grand modele (il a vu l'alerte et a repete quand meme).
    Une serie qui depasse le seuil sans passage par le grand modele reste
    SANS_EFFET : l'escalade n'a pas encore eu lieu.
    """
    seuil_repetitions = max(REPETITIONS_PAR_DEFAUT if repetitions is None else repetitions, 2)
    actions = [e for e in entrees if e.genre == GENRE_ACTION and e.outil]

    meilleur: ResultatBoucle | None = None
    meilleure_serie: list[EntreeJournal] = []
    seuil_actions_retenu = 0
    for periode in PERIODES_SURVEILLEES:
        longueur = _longueur_serie(actions, periode)
        seuil_actions = periode * seuil_repetitions
        if longueur < seuil_actions:
            continue
        if meilleur is None or longueur > meilleur.longueur:
            motif = MOTIF_REPETITION if periode == 1 else MOTIF_CYCLE
            meilleur = ResultatBoucle(Verdict.SANS_EFFET, motif, longueur)
            meilleure_serie = actions[-longueur:]
            seuil_actions_retenu = seuil_actions

    if meilleur is None:
        return ResultatBoucle(Verdict.AUCUNE)

    prolongement = meilleure_serie[seuil_actions_retenu:]
    if any(e.auteur == AUTEUR_GRAND_MODELE for e in prolongement):
        return ResultatBoucle(Verdict.BLOQUEE, meilleur.motif, meilleur.longueur)
    return meilleur
