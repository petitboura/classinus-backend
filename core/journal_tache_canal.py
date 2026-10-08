"""
Canal en direct : journal de tache ecrit par le backend (08/10/2026, chantier
Jev, lot 1, decision de Bourama).

Principe : ce journal n'est JAMAIS ecrit par un modele. A chaque appel d'outil
du canal, qu'il vienne d'un choix de Jev ou du grand modele, le backend ajoute
une ligne : qui a decide, quel outil, sur quelle cible (decrite en mots, les
identifiants du scan ne sont pas stables), le resultat, et pour une parole ce
qui a ete dit. L'action prise pendant une escalade devient ainsi une action
"deja tentee" au tour suivant, sans que le grand modele ait a la resumer.

Ce que Jev recoit au tour suivant : les dernieres entrees en version compacte
(resume_compact), avec une marque pour ce qui a ete decide en escalade. Le
raisonnement du grand modele n'est jamais stocke : seules les actions et les
paroles adressees a l'etudiant comptent, sinon le budget de tokens de Jev se
remplit vite.

Si le grand modele pose une question a l'etudiant, le journal le note et Jev ne
relance aucune action tant que l'etudiant n'a pas repondu (question_en_attente).

Meme forme que core/lecture_ecran_continue.py : etat en memoire du processus,
par (utilisateur, conversation). Consequence assumee : un redeploiement en cours
de conversation efface le journal. Sans danger, la tache repart d'un journal
vide, rien n'est execute a l'aveugle.

Aucun branchement dans le reste de l'application pour l'instant.
"""

import dataclasses
import os
import threading
import time
from dataclasses import dataclass, field

AUTEUR_JEV = "jev"
AUTEUR_GRAND_MODELE = "grand_modele"
AUTEUR_BACKEND = "backend"
AUTEURS = (AUTEUR_JEV, AUTEUR_GRAND_MODELE, AUTEUR_BACKEND)

GENRE_ACTION = "action"
GENRE_PAROLE = "parole"
GENRE_QUESTION = "question"
GENRES = (GENRE_ACTION, GENRE_PAROLE, GENRE_QUESTION)

# Valeurs de depart, reglables sans toucher au code, a ajuster apres de vrais tests.
NB_MAX_ENTREES_PAR_JOURNAL = int(os.environ.get("CLASSINUS_JOURNAL_NB_MAX_ENTREES", "50"))
NB_ENTREES_RESUME_COMPACT = int(os.environ.get("CLASSINUS_JOURNAL_NB_ENTREES_RESUME", "8"))
LONGUEUR_MAX_CIBLE = int(os.environ.get("CLASSINUS_JOURNAL_LONGUEUR_MAX_CIBLE", "120"))
LONGUEUR_MAX_TEXTE = int(os.environ.get("CLASSINUS_JOURNAL_LONGUEUR_MAX_TEXTE", "200"))
DUREE_VIE_JOURNAL_SECONDES = int(os.environ.get("CLASSINUS_JOURNAL_DUREE_VIE_S", str(6 * 3600)))
NB_MAX_JOURNAUX_SUIVIS = int(os.environ.get("CLASSINUS_JOURNAL_NB_MAX_JOURNAUX", "5000"))


@dataclass(frozen=True)
class EntreeJournal:
    auteur: str
    genre: str
    outil: str = ""
    # Description de l'element vise, en mots (pas un identifiant instable).
    cible: str = ""
    # None : pas de notion de resultat (parole, question).
    reussi: bool | None = None
    # Parole dite a l'etudiant, ou question posee. Vide pour une action.
    texte: str = ""
    # Empreintes de l'ecran juste avant et juste apres l'action (voir
    # core/empreinte_ecran.py). None : inconnue, jamais "inchangee".
    empreinte_avant: str | None = None
    empreinte_apres: str | None = None
    horodatage: float = field(default_factory=time.time)


class _Journal:
    def __init__(self) -> None:
        self.entrees: list[EntreeJournal] = []
        self.question_en_attente = False
        self.derniere_activite = time.monotonic()


_journaux: dict[tuple[str, str], _Journal] = {}
_verrou = threading.Lock()


def _cle(user_id: str, conversation_id: str | None) -> tuple[str, str]:
    return (str(user_id), str(conversation_id or ""))


def _couper(texte: str, longueur_max: int) -> str:
    texte = texte or ""
    if len(texte) <= longueur_max:
        return texte
    return texte[: max(longueur_max - 1, 0)] + "…"


def _purger_si_besoin(maintenant: float) -> None:
    """Appelee sous verrou. Retire les journaux expires, puis les plus anciens si trop nombreux."""
    if len(_journaux) <= NB_MAX_JOURNAUX_SUIVIS:
        return
    for cle in [c for c, j in _journaux.items() if maintenant - j.derniere_activite > DUREE_VIE_JOURNAL_SECONDES]:
        del _journaux[cle]
    if len(_journaux) > NB_MAX_JOURNAUX_SUIVIS:
        plus_anciens = sorted(_journaux, key=lambda c: _journaux[c].derniere_activite)
        for cle in plus_anciens[: len(_journaux) - NB_MAX_JOURNAUX_SUIVIS]:
            del _journaux[cle]


def _journal_vivant(cle: tuple[str, str], maintenant: float) -> _Journal | None:
    """Appelee sous verrou. Renvoie le journal s'il existe et n'est pas expire."""
    journal = _journaux.get(cle)
    if journal is None:
        return None
    if maintenant - journal.derniere_activite > DUREE_VIE_JOURNAL_SECONDES:
        del _journaux[cle]
        return None
    return journal


def ajouter(user_id: str, conversation_id: str | None, entree: EntreeJournal) -> None:
    """
    Ajoute une entree au journal de la conversation. Une entree de genre
    "question" met le journal en attente de reponse de l'etudiant.
    Leve ValueError si l'auteur ou le genre est inconnu (erreur de programmation,
    pas une situation d'execution normale).
    """
    if entree.auteur not in AUTEURS:
        raise ValueError(f"Auteur de journal inconnu : {entree.auteur!r}")
    if entree.genre not in GENRES:
        raise ValueError(f"Genre de journal inconnu : {entree.genre!r}")
    entree = dataclasses.replace(
        entree,
        cible=_couper(entree.cible, LONGUEUR_MAX_CIBLE),
        texte=_couper(entree.texte, LONGUEUR_MAX_TEXTE),
    )
    cle = _cle(user_id, conversation_id)
    maintenant = time.monotonic()
    with _verrou:
        journal = _journal_vivant(cle, maintenant)
        if journal is None:
            journal = _Journal()
            _journaux[cle] = journal
        journal.entrees.append(entree)
        if len(journal.entrees) > NB_MAX_ENTREES_PAR_JOURNAL:
            del journal.entrees[: len(journal.entrees) - NB_MAX_ENTREES_PAR_JOURNAL]
        if entree.genre == GENRE_QUESTION:
            journal.question_en_attente = True
        journal.derniere_activite = maintenant
        _purger_si_besoin(maintenant)


def entrees(user_id: str, conversation_id: str | None, genre: str | None = None) -> list[EntreeJournal]:
    """Copie des entrees du journal (toutes, ou d'un seul genre), de la plus ancienne a la plus recente."""
    with _verrou:
        journal = _journal_vivant(_cle(user_id, conversation_id), time.monotonic())
        if journal is None:
            return []
        return [e for e in journal.entrees if genre is None or e.genre == genre]


def question_en_attente(user_id: str, conversation_id: str | None) -> bool:
    """Vrai si une question a ete posee a l'etudiant et qu'il n'a pas encore repondu."""
    with _verrou:
        journal = _journal_vivant(_cle(user_id, conversation_id), time.monotonic())
        return bool(journal and journal.question_en_attente)


def marquer_reponse_recue(user_id: str, conversation_id: str | None) -> None:
    """L'etudiant a repondu : Jev peut de nouveau agir."""
    with _verrou:
        journal = _journal_vivant(_cle(user_id, conversation_id), time.monotonic())
        if journal is not None:
            journal.question_en_attente = False


def effacer(user_id: str, conversation_id: str | None) -> None:
    """Vide le journal (nouvelle tache, ou fin de tache)."""
    with _verrou:
        _journaux.pop(_cle(user_id, conversation_id), None)


def _ligne_compacte(entree: EntreeJournal) -> str:
    if entree.genre == GENRE_ACTION:
        cible = f" sur « {entree.cible} »" if entree.cible else ""
        issue = {True: "réussi", False: "échoué"}.get(entree.reussi, "résultat inconnu")
        marque = " (décidé en escalade)" if entree.auteur == AUTEUR_GRAND_MODELE else ""
        return f"action : {entree.outil}{cible}, {issue}{marque}"
    if entree.genre == GENRE_PAROLE:
        return f"dit à l'étudiant : « {entree.texte} »"
    marque = " (décidé en escalade)" if entree.auteur == AUTEUR_GRAND_MODELE else ""
    return f"question posée à l'étudiant : « {entree.texte} »{marque}"


def resume_compact(user_id: str, conversation_id: str | None, nb_entrees: int | None = None) -> str:
    """
    Dernieres entrees du journal en texte court, pour le `state` de Jev. Chaine
    vide si le journal est vide. Si une question attend la reponse de l'etudiant,
    une derniere ligne le dit.
    """
    nb = NB_ENTREES_RESUME_COMPACT if nb_entrees is None else nb_entrees
    toutes = entrees(user_id, conversation_id)
    if not toutes:
        return ""
    lignes = [f"- {_ligne_compacte(e)}" for e in toutes[-nb:]] if nb > 0 else []
    if question_en_attente(user_id, conversation_id):
        lignes.append("- en attente de la réponse de l'étudiant : ne lance aucune action")
    return "\n".join(lignes)
