"""
Chantier agent applicatif (voir plan-agent-applicatif-clovis.md),
chantier C, partie canal.

Decision Bourama (0.1) : canal SEPARE de core/canal_temps_reel.py --
celui-ci reste dedie a l'exploration de dossier natif, aucune logique
commune au-dela du principe general (correlation par id, verrou d'envoi
par connexion).

Decision Bourama (suite a la question "faut-il cibler un appareil ?") :
contrairement au telephone (qui doit resoudre QUEL appareil physique
possede tel dossier designe), l'agent applicatif n'a qu'UNE seule cible
possible : l'app elle-meme. Quand un compte a l'app ouverte a plusieurs
endroits a la fois (telephone + PC + navigateur), on ne cible pas un
appareil precis -- on DIFFUSE la demande a TOUTES les connexions actives
de ce user_id (meme principe que notifier_utilisateur dans
core/canal_temps_reel.py), et la premiere connexion qui a reellement
l'action montee a l'ecran repond. Les autres l'ignorent silencieusement
cote frontend (voir lib/canalAgentApplicatif.ts).
"""

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

# Cle = (user_id, appareil_id), meme convention que canal_temps_reel.py
# ("" = session web / PC, sinon identifiant natif) -- gardee ici pour la
# poussee d'etat continue du chantier D (qui, elle, a besoin de savoir
# QUELLE connexion precise a declenche quel changement), meme si
# l'execution d'action (ce fichier) ne cible jamais un appareil precis.
_connexions: dict[tuple[str, str], WebSocket] = {}
_verrou_connexions = asyncio.Lock()
_verrous_envoi: dict[tuple[str, str], asyncio.Lock] = {}

_attentes: dict[str, "asyncio.Future[Any]"] = {}

# Chantier D : dernier etat des actions disponibles POUSSE par chaque
# connexion (jamais interroge activement -- purement passif, mis a jour
# uniquement quand le frontend envoie {"etat_actions": [...]}). Vide
# tant qu'aucune poussee n'est encore arrivee pour cette connexion :
# on ne devine jamais une liste, on attend la vraie donnee.
_etat_actions: dict[tuple[str, str], list[dict[str, Any]]] = {}

# Memes paliers que canal_temps_reel.py (coherence pour l'etudiant, qui
# peut voir les deux types de message dans la meme conversation).
DELAI_STATUT_1_SECONDES = 5
DELAI_STATUT_2_SECONDES = 15
DELAI_ABANDON_SECONDES = 30

TEXTE_STATUT_1 = "Clovis interagit avec l'application..."
TEXTE_STATUT_2 = "Ça prend un peu plus de temps que prévu..."


async def _verrou_envoi_pour(cle: tuple[str, str]) -> asyncio.Lock:
    async with _verrou_connexions:
        verrou = _verrous_envoi.get(cle)
        if verrou is None:
            verrou = asyncio.Lock()
            _verrous_envoi[cle] = verrou
        return verrou


async def connecter(user_id: str, appareil_id: str, websocket: WebSocket) -> None:
    cle = (user_id, appareil_id)
    async with _verrou_connexions:
        ancienne = _connexions.get(cle)
        _connexions[cle] = websocket
    if ancienne is not None and ancienne is not websocket:
        try:
            await ancienne.close()
        except Exception:
            pass


async def deconnecter(user_id: str, appareil_id: str, websocket: WebSocket) -> None:
    cle = (user_id, appareil_id)
    async with _verrou_connexions:
        if _connexions.get(cle) is websocket:
            del _connexions[cle]
            _verrous_envoi.pop(cle, None)
            # Chantier D : une connexion fermee n'a plus rien de monte a
            # l'ecran, son etat pousse serait perime -- le retirer plutot
            # que de risquer de le laisser trainer et d'etre lu comme
            # encore valable.
            _etat_actions.pop(cle, None)


def mettre_a_jour_etat_actions(user_id: str, appareil_id: str, actions: list[dict[str, Any]]) -> None:
    """
    Chantier D : appelee a chaque poussee {"etat_actions": [...]} recue
    d'une connexion (voir api/canal_agent_applicatif.py). Remplace
    integralement l'etat precedent de CETTE connexion -- jamais fusionne
    action par action, la liste recue est toujours l'etat complet et a
    jour de ce que cette connexion a de monte a cet instant.
    """
    _etat_actions[(user_id, appareil_id)] = actions


def obtenir_actions_disponibles(user_id: str) -> list[dict[str, Any]]:
    """
    Chantier D, cote lecture : fusionne les etats poussés par TOUTES les
    connexions actives de `user_id` (plusieurs onglets/appareils
    possibles, decision Bourama : aucune cible unique). Deduplique par
    id -- si le meme id est monte sur deux connexions a la fois (meme
    page ouverte deux fois), il n'apparait qu'une fois pour le modele.
    Renvoie une liste vide si aucune poussee n'est encore arrivee,
    jamais une liste inventee ou mise en cache au dela de la derniere
    poussee reelle.
    """
    fusion: dict[str, dict[str, Any]] = {}
    for (cle_user, _appareil), actions in _etat_actions.items():
        if cle_user != user_id:
            continue
        for action in actions:
            action_id = action.get("id")
            if isinstance(action_id, str):
                fusion[action_id] = action
    return list(fusion.values())


def recevoir_reponse(correlation_id: str, reponse: Any) -> None:
    """
    Appelee a chaque reponse recue d'UNE connexion. Comme la demande est
    diffusee a plusieurs connexions a la fois, seule la PREMIERE reponse
    valable (qui n'est pas {"ignore": true}, voir
    lib/canalAgentApplicatif.ts) resout la Future -- les reponses
    suivantes (des autres connexions du meme compte) arrivent apres coup
    et sont simplement ignorees (la Future n'existe plus).
    """
    future = _attentes.get(correlation_id)
    if future is None or future.done():
        return
    if isinstance(reponse, dict) and reponse.get("ignore"):
        return
    future.set_result(reponse)


async def _appeler_statut(on_statut, texte: str) -> None:
    if on_statut is None:
        return
    try:
        resultat = on_statut(texte)
        if asyncio.iscoroutine(resultat):
            await resultat
    except Exception as e:
        logging.error(f"ERREUR callback statut canal agent applicatif : {e}")


async def _diffuser_et_attendre(
    user_id: str, message: dict[str, Any], on_statut=None, on_timeout_log: str = ""
) -> Any | None:
    """
    Logique commune a demander_execution_action (chantier C) et
    demander_clic_generique (chantier F) : diffuse `message` (avec son
    "id" deja inclus) a TOUTES les connexions actives de `user_id`, et
    attend la premiere reponse valable, avec les memes paliers de statut
    que le reste de ce fichier. Extrait ici pour eviter de dupliquer
    cette logique (identique) entre les deux chantiers.
    """
    async with _verrou_connexions:
        connexions = [(cle, ws) for cle, ws in _connexions.items() if cle[0] == user_id]

    if not connexions:
        return None

    correlation_id = message["id"]
    future: "asyncio.Future[Any]" = asyncio.get_event_loop().create_future()
    _attentes[correlation_id] = future

    try:
        for cle, websocket in connexions:
            verrou_envoi = await _verrou_envoi_pour(cle)
            try:
                async with verrou_envoi:
                    await websocket.send_json(message)
            except Exception as e:
                logging.error(f"ERREUR diffusion message canal agent applicatif (user={user_id}, appareil={cle[1]}) : {e}")

        try:
            return await asyncio.wait_for(future, timeout=DELAI_STATUT_1_SECONDES)
        except asyncio.TimeoutError:
            pass

        await _appeler_statut(on_statut, TEXTE_STATUT_1)
        try:
            return await asyncio.wait_for(future, timeout=DELAI_STATUT_2_SECONDES - DELAI_STATUT_1_SECONDES)
        except asyncio.TimeoutError:
            pass

        await _appeler_statut(on_statut, TEXTE_STATUT_2)
        try:
            return await asyncio.wait_for(future, timeout=DELAI_ABANDON_SECONDES - DELAI_STATUT_2_SECONDES)
        except asyncio.TimeoutError:
            logging.warning(
                f"ABANDON canal agent applicatif (user={user_id}, id={correlation_id}) : "
                f"pas de reponse apres {DELAI_ABANDON_SECONDES}s. {on_timeout_log}"
            )
            return None
    finally:
        _attentes.pop(correlation_id, None)


async def demander_execution_action(user_id: str, action_id: str, on_statut=None) -> Any | None:
    """
    Diffuse une demande d'execution de l'action `action_id` (declaree
    cote frontend via lib/actionsApplicatives.ts, chantier A) a TOUTES
    les connexions actives de `user_id`, et attend la premiere reponse
    valable.

    Renvoie :
    - None IMMEDIATEMENT si aucune connexion active pour ce user_id
      (aucun onglet/app ouvert) ;
    - la reponse de la connexion qui a reellement execute l'action des
      qu'elle arrive (voir traiterDemandeAction cote frontend pour le
      format -- succes/erreur) ;
    - None apres 30 secondes si aucune connexion n'a jamais repondu
      valablement (action introuvable partout, ou app fermee entre
      temps).
    """
    correlation_id = str(uuid.uuid4())
    return await _diffuser_et_attendre(
        user_id,
        {"id": correlation_id, "action_id": action_id},
        on_statut,
        on_timeout_log=f"action={action_id}",
    )


async def demander_clic_generique(
    user_id: str, selecteur: str, description: str, on_statut=None
) -> Any | None:
    """
    Chantier F. Meme principe que demander_execution_action, mais pour
    le mode generique (DOM + selecteur) : diffuse {selecteur_generique,
    description} a toutes les connexions actives, la premiere connexion
    qui trouve un element correspondant, VISIBLE et ACTIF, gere la
    confirmation (toujours requise en mode generique, voir
    lib/canalAgentApplicatif.ts) puis le clic reel.
    """
    correlation_id = str(uuid.uuid4())
    return await _diffuser_et_attendre(
        user_id,
        {"id": correlation_id, "selecteur_generique": selecteur, "description": description},
        on_statut,
        on_timeout_log=f"selecteur={selecteur}",
    )
