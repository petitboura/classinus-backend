"""
Canal en direct : client HTTP de Jev (TypeSafe AI), chantier Jev, lot 2
(09/10/2026).

Jev ne genere pas de texte : on lui envoie un `state` et des questions typees
(Choice, Score, Noul), il renvoie des reponses contraintes avec des
probabilites. Contrat verifie dans la documentation officielle
(docs.typesafe.ai, page API reference) :

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <cle>
    {"state": <texte|objet|liste>, "model": "...", "questions": {id: question}}

- Choice : criteria = {option: description|null}, 1 a 255 options. Reponse :
  choice, probabilities, confidence.
- Score : criteria = liste ordonnee de 2 a 10 niveaux. Reponse : score (peut
  tomber entre deux niveaux), legend, probabilities, confidence.
- Noul : oui/non, criteria facultatif {"true": ..., "false": ...}. Reponse :
  noul entre 0 et 1, SANS confidence (voir confiance_noul).
- Toutes les questions d'une requete sont evaluees en parallele sur le meme
  state : une seule requete par tour de la boucle d'orchestration.
- Budget : environ 32k tokens pour le state plus la plus longue question.
- Erreurs : 401 cle absente ou invalide, 422 requete mal formee, 429 limite de
  debit et 529 surcharge (a reessayer avec attente croissante).

Choix de conception :
- httpx en asynchrone, pas le SDK Python officiel : httpx est deja une
  dependance du depot, le SDK en ajouterait une autre (httpx2) pour un seul
  appel, et le contrat est minuscule.
- Cle absente = pas de crash : creer_client_depuis_env() renvoie None, comme
  les autres clients de modeles du depot (etape sautee). Le canal en direct
  garde alors son fonctionnement actuel.
- Le state peut contenir ce qui est affiche a l'ecran de l'etudiant : il n'est
  jamais ecrit dans les logs ni dans les messages d'erreur. Seuls le statut
  HTTP et un court extrait de la reponse du serveur y figurent. La cle n'y
  figure jamais non plus.
- Le modele est fixe par defaut sur une version precise et non sur
  "jev-latest" : une decision d'action ne doit pas changer de comportement
  sans qu'on l'ait choisi. Reglable par TYPESAFE_MODEL.

Module sans etat global et sans branchement dans le reste de l'application
pour l'instant : la boucle d'orchestration arrive dans les modules suivants.
"""

import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

URL_PAR_DEFAUT = "https://api.typesafe.ai"
CHEMIN_SYSTEM_ONE = "/v1/systemone"
MODELE_PAR_DEFAUT = "jev-1.13.0"

# Valeurs de depart reglables sans toucher au code, a ajuster apres de vrais
# tests. Jev annonce 70 a 500 ms : un delai long n'a d'interet que pour les cas
# de surcharge, et la boucle du canal en direct ne doit pas rester bloquee.
DELAI_MAX_SECONDES = float(os.environ.get("TYPESAFE_DELAI_MAX_S", "8"))
NB_REESSAIS_MAX = int(os.environ.get("TYPESAFE_NB_REESSAIS", "2"))
ATTENTE_REESSAI_BASE_SECONDES = float(os.environ.get("TYPESAFE_ATTENTE_REESSAI_S", "0.3"))
ATTENTE_REESSAI_MAX_SECONDES = float(os.environ.get("TYPESAFE_ATTENTE_REESSAI_MAX_S", "2"))
# Garde-fou avant l'envoi : environ 150 000 caracteres d'anglais pour 32k tokens.
# Le texte francais et les structures JSON consomment davantage de tokens par
# caractere, donc la valeur de depart est prudente.
LONGUEUR_MAX_STATE_CARACTERES = int(os.environ.get("TYPESAFE_LONGUEUR_MAX_STATE", "100000"))

NB_MAX_OPTIONS_CHOICE = 255
NB_MIN_NIVEAUX_SCORE = 2
NB_MAX_NIVEAUX_SCORE = 10

# 429 et 529 sont documentes comme a reessayer. Les 5xx transitoires le sont
# aussi : la boucle d'orchestration vaut mieux avec un reessai silencieux
# qu'avec une escalade inutile vers le grand modele.
STATUTS_A_REESSAYER = frozenset({429, 500, 502, 503, 504, 529})

LONGUEUR_MAX_EXTRAIT_ERREUR = 300


class JevErreur(Exception):
    """Echec definitif : requete refusee, cle invalide, reponse inexploitable."""

    def __init__(self, message: str, statut: int | None = None):
        super().__init__(message)
        self.statut = statut


class JevIndisponible(JevErreur):
    """Echec apres les reessais : surcharge, limite de debit, reseau, delai depasse."""


class JevEtatTropLong(JevErreur):
    """Le state depasse le budget de Jev : l'appelant doit le reduire avant d'appeler."""


# ==========================================================================
# Questions
# ==========================================================================

@dataclass(frozen=True)
class Choice:
    instructions: Any
    # option -> description (texte, objet, liste ou None)
    criteria: dict[str, Any]

    def vers_json(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": dict(self.criteria)}


@dataclass(frozen=True)
class Score:
    instructions: Any
    # liste ordonnee, du niveau le plus bas au plus haut
    criteria: tuple

    def vers_json(self) -> dict:
        return {"type": "score", "instructions": self.instructions, "criteria": list(self.criteria)}


@dataclass(frozen=True)
class Noul:
    instructions: Any
    # {"true": ..., "false": ...} facultatif
    criteria: dict[str, Any] | None = None

    def vers_json(self) -> dict:
        corps: dict = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            corps["criteria"] = dict(self.criteria)
        return corps


def _valider_question(identifiant: str, question) -> None:
    if not isinstance(identifiant, str) or not identifiant.strip():
        raise JevErreur("Identifiant de question vide ou invalide.")
    if isinstance(question, Choice):
        options = question.criteria
        if not isinstance(options, dict) or not options:
            raise JevErreur(f"Question {identifiant!r} : un Choice demande au moins une option.")
        if len(options) > NB_MAX_OPTIONS_CHOICE:
            raise JevErreur(
                f"Question {identifiant!r} : {len(options)} options, le maximum de Jev est {NB_MAX_OPTIONS_CHOICE}. "
                "Prefiltrer les options avant l'appel."
            )
        if any(not isinstance(o, str) or not o for o in options):
            raise JevErreur(f"Question {identifiant!r} : chaque option doit etre un texte non vide.")
    elif isinstance(question, Score):
        niveaux = question.criteria
        if not isinstance(niveaux, (list, tuple)) or not (NB_MIN_NIVEAUX_SCORE <= len(niveaux) <= NB_MAX_NIVEAUX_SCORE):
            raise JevErreur(
                f"Question {identifiant!r} : un Score demande entre {NB_MIN_NIVEAUX_SCORE} et "
                f"{NB_MAX_NIVEAUX_SCORE} niveaux."
            )
    elif isinstance(question, Noul):
        if question.criteria is not None and (
            not isinstance(question.criteria, dict) or not set(question.criteria) <= {"true", "false"}
        ):
            raise JevErreur(f"Question {identifiant!r} : les criteres d'un Noul sont seulement 'true' et 'false'.")
    else:
        raise JevErreur(f"Question {identifiant!r} : type inconnu {type(question).__name__}.")
    if question.instructions is None or question.instructions == "":
        raise JevErreur(f"Question {identifiant!r} : les instructions sont obligatoires.")


# ==========================================================================
# Reponses
# ==========================================================================

@dataclass(frozen=True)
class ReponseChoice:
    choix: str
    confiance: float
    probabilites: dict[str, float]


@dataclass(frozen=True)
class ReponseScore:
    score: float
    confiance: float
    probabilites: dict[str, float]
    legende: dict[str, str]


@dataclass(frozen=True)
class ReponseNoul:
    # Probabilite que la reponse soit oui, entre 0 et 1.
    valeur: float


@dataclass(frozen=True)
class ReponseJev:
    modele: str
    reponses: dict[str, ReponseChoice | ReponseScore | ReponseNoul]
    tokens_entree: int = 0
    tokens_sortie: int = 0

    def choice(self, identifiant: str) -> ReponseChoice:
        return self._typee(identifiant, ReponseChoice)

    def score(self, identifiant: str) -> ReponseScore:
        return self._typee(identifiant, ReponseScore)

    def noul(self, identifiant: str) -> ReponseNoul:
        return self._typee(identifiant, ReponseNoul)

    def _typee(self, identifiant: str, type_attendu):
        reponse = self.reponses.get(identifiant)
        if not isinstance(reponse, type_attendu):
            raise JevErreur(f"Reponse {identifiant!r} absente ou d'un autre type que {type_attendu.__name__}.")
        return reponse


def confiance_noul(reponse: ReponseNoul) -> float:
    """
    Un Noul ne renvoie pas de confidence. La documentation propose la distance
    a 0,5 : 0 quand Jev hesite (0,5), 1 quand il est sur (0 ou 1). Meme echelle
    que la confidence d'un Choice a deux options.
    """
    return abs(2 * reponse.valeur - 1)


def _nombre(valeur, nom: str) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise JevErreur(f"Reponse de Jev invalide : {nom} n'est pas un nombre.")
    return float(valeur)


def _table_de_nombres(valeur, nom: str) -> dict[str, float]:
    if not isinstance(valeur, dict):
        raise JevErreur(f"Reponse de Jev invalide : {nom} n'est pas une table.")
    return {str(cle): _nombre(v, f"{nom}[{cle}]") for cle, v in valeur.items()}


def _lire_reponse(identifiant: str, question, brut) -> ReponseChoice | ReponseScore | ReponseNoul:
    if not isinstance(brut, dict):
        raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} n'est pas un objet.")
    if isinstance(question, Choice):
        if brut.get("type") != "choice":
            raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} devrait etre un choice.")
        choix = brut.get("choice")
        if choix not in question.criteria:
            # Jamais d'action executee sur une option que nous n'avons pas proposee.
            raise JevErreur(f"Reponse de Jev invalide : option inconnue pour {identifiant!r}.")
        return ReponseChoice(
            choix=choix,
            confiance=_nombre(brut.get("confidence"), f"{identifiant}.confidence"),
            probabilites=_table_de_nombres(brut.get("probabilities"), f"{identifiant}.probabilities"),
        )
    if isinstance(question, Score):
        if brut.get("type") != "score":
            raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} devrait etre un score.")
        legende = brut.get("legend")
        return ReponseScore(
            score=_nombre(brut.get("score"), f"{identifiant}.score"),
            confiance=_nombre(brut.get("confidence"), f"{identifiant}.confidence"),
            probabilites=_table_de_nombres(brut.get("probabilities"), f"{identifiant}.probabilities"),
            legende={str(k): str(v) for k, v in legende.items()} if isinstance(legende, dict) else {},
        )
    if brut.get("type") != "noul":
        raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} devrait etre un noul.")
    valeur = _nombre(brut.get("noul"), f"{identifiant}.noul")
    if not 0.0 <= valeur <= 1.0:
        raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} hors de l'intervalle 0 a 1.")
    return ReponseNoul(valeur=valeur)


# ==========================================================================
# Client
# ==========================================================================

def _extrait_serveur(reponse: httpx.Response) -> str:
    """Court extrait du corps d'erreur du serveur (il decrit le champ fautif en cas de 422)."""
    try:
        texte = reponse.text
    except Exception:
        return ""
    texte = " ".join(texte.split())
    return texte[:LONGUEUR_MAX_EXTRAIT_ERREUR]


def _longueur_state(state) -> int:
    if isinstance(state, str):
        return len(state)
    try:
        return len(json.dumps(state, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        raise JevErreur("Le state n'est pas serialisable en JSON.")


class JevClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = URL_PAR_DEFAUT,
        model: str = MODELE_PAR_DEFAUT,
        timeout: float = DELAI_MAX_SECONDES,
        max_reessais: int = NB_REESSAIS_MAX,
        transport: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        cle = (api_key or "").strip()
        if not cle:
            raise JevErreur("Cle API TypeSafe absente.")
        self._cle = cle
        self._model = model
        self._url = base_url.rstrip("/") + CHEMIN_SYSTEM_ONE
        self._max_reessais = max(0, max_reessais)
        self._dormir = dormir
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "JevClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    def _attente(self, tentative: int, reponse: httpx.Response | None) -> float:
        """Attente avant le reessai numero `tentative` (0 pour le premier), bornee."""
        exponentielle = ATTENTE_REESSAI_BASE_SECONDES * (2 ** tentative)
        if reponse is not None:
            try:
                exponentielle = max(exponentielle, float(reponse.headers.get("retry-after", "0")))
            except ValueError:
                pass
        borne = min(exponentielle, ATTENTE_REESSAI_MAX_SECONDES)
        # Un peu de hasard pour que plusieurs etudiants ne reessaient pas au meme instant.
        return borne * (0.75 + 0.25 * random.random())

    async def evaluer(self, state, questions: dict[str, Choice | Score | Noul]) -> ReponseJev:
        """
        Une requete : evalue le state contre toutes les questions en parallele.

        Leve JevEtatTropLong (a reduire avant d'appeler), JevErreur (refus ou
        reponse inexploitable, inutile de reessayer) ou JevIndisponible (apres
        les reessais : l'appelant escalade vers le grand modele).
        """
        if not isinstance(questions, dict) or not questions:
            raise JevErreur("Au moins une question est necessaire.")
        for identifiant, question in questions.items():
            _valider_question(identifiant, question)
        longueur = _longueur_state(state)
        if longueur > LONGUEUR_MAX_STATE_CARACTERES:
            raise JevEtatTropLong(
                f"State trop long ({longueur} caracteres, maximum {LONGUEUR_MAX_STATE_CARACTERES}) : "
                "a reduire avant l'appel."
            )

        corps = {
            "state": state,
            "model": self._model,
            "questions": {identifiant: q.vers_json() for identifiant, q in questions.items()},
        }
        entetes = {"Authorization": f"Bearer {self._cle}", "Content-Type": "application/json"}

        derniere_cause = "inconnue"
        dernier_statut: int | None = None
        for tentative in range(self._max_reessais + 1):
            reponse: httpx.Response | None = None
            try:
                reponse = await self._http.post(self._url, json=corps, headers=entetes)
            except httpx.TransportError as e:
                # Connexion, delai depasse, lecture : message limite au type d'erreur.
                derniere_cause = f"reseau ({type(e).__name__})"
                dernier_statut = None
            else:
                if reponse.status_code == 200:
                    return self._interpreter(reponse, questions)
                if reponse.status_code not in STATUTS_A_REESSAYER:
                    raise JevErreur(
                        f"Jev a refuse la requete (HTTP {reponse.status_code}) : {_extrait_serveur(reponse)}",
                        statut=reponse.status_code,
                    )
                derniere_cause = f"HTTP {reponse.status_code}"
                dernier_statut = reponse.status_code

            if tentative < self._max_reessais:
                await self._dormir(self._attente(tentative, reponse))

        logging.warning(f"Jev indisponible apres {self._max_reessais + 1} tentative(s) : {derniere_cause}")
        raise JevIndisponible(
            f"Jev indisponible apres {self._max_reessais + 1} tentative(s) : {derniere_cause}", statut=dernier_statut
        )

    def _interpreter(self, reponse: httpx.Response, questions: dict) -> ReponseJev:
        try:
            donnees = reponse.json()
        except ValueError:
            raise JevErreur("Reponse de Jev invalide : corps non JSON.", statut=reponse.status_code)
        if not isinstance(donnees, dict) or not isinstance(donnees.get("answers"), dict):
            raise JevErreur("Reponse de Jev invalide : champ answers absent.", statut=reponse.status_code)
        brutes = donnees["answers"]
        lues = {}
        for identifiant, question in questions.items():
            if identifiant not in brutes:
                raise JevErreur(f"Reponse de Jev invalide : {identifiant!r} manquante.", statut=reponse.status_code)
            lues[identifiant] = _lire_reponse(identifiant, question, brutes[identifiant])
        usage = donnees.get("usage") if isinstance(donnees.get("usage"), dict) else {}

        def _entier(cle: str) -> int:
            valeur = usage.get(cle)
            return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else 0

        return ReponseJev(
            modele=str(donnees.get("model") or self._model),
            reponses=lues,
            tokens_entree=_entier("input_tokens"),
            tokens_sortie=_entier("output_tokens"),
        )


def creer_client_depuis_env() -> JevClient | None:
    """
    Client configure par l'environnement, ou None si TYPESAFE_API_KEY est
    absente (meme convention que les autres fournisseurs : etape sautee sans
    erreur visible, le canal garde son fonctionnement actuel).

    Variables : TYPESAFE_API_KEY (obligatoire), TYPESAFE_BASE_URL, TYPESAFE_MODEL.
    """
    cle = (os.environ.get("TYPESAFE_API_KEY") or "").strip()
    if not cle:
        return None
    return JevClient(
        cle,
        base_url=os.environ.get("TYPESAFE_BASE_URL") or URL_PAR_DEFAUT,
        model=os.environ.get("TYPESAFE_MODEL") or MODELE_PAR_DEFAUT,
    )
