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
import threading
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

TEXTE_STATUT_1 = "Classinus interagit avec l'application..."
TEXTE_STATUT_2 = "Ça prend un peu plus de temps que prévu..."


async def _verrou_envoi_pour(cle: tuple[str, str]) -> asyncio.Lock:
    async with _verrou_connexions:
        verrou = _verrous_envoi.get(cle)
        if verrou is None:
            verrou = asyncio.Lock()
            _verrous_envoi[cle] = verrou
        return verrou


async def connecter(user_id: str, appareil_id: str, websocket: WebSocket) -> None:
    global _boucle_evenements
    _boucle_evenements = asyncio.get_running_loop()
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


# Correctif du 19/09/2026 (Bourama : "dans beaucoup de cas Clovis n'arrive
# pas a cliquer") : l'ancien mecanisme d'injection par DIFFERENCE
# (ajouts/retraits depuis le dernier tour) est retire. Le prompt systeme
# est reconstruit de zero a CHAQUE tour et l'historique ne contient que
# les messages de la conversation, jamais les anciens prompts : apres le
# premier tour, le modele ne voyait donc plus que les changements, pas la
# liste de base, et ne connaissait plus les id de la plupart des elements.
# Le prompt recoit maintenant la liste COMPLETE et actuelle a chaque tour
# (voir core/construction_system_prompt.py), et le resultat de chaque clic
# decrit ce qui a change a l'ecran (voir observer_changement_ecran).

# Delai laisse a l'application pour reagir a un clic (ouverture d'un menu,
# animation) et repousser son nouvel etat : le frontend attend 200 ms de
# calme apres un changement du DOM avant de repousser (voir
# lib/canalAgentApplicatif.ts), plus le temps de l'animation.
DELAI_OBSERVATION_ECRAN_SECONDES = 0.9
NB_MAX_ELEMENTS_CITES_APRES_CLIC = 40


def photographier_ecran(user_id: str) -> dict[str, str]:
    """id -> description des elements cliquables actuellement a l'ecran."""
    return {
        a["id"]: str(a.get("description", ""))
        for a in obtenir_actions_disponibles(user_id)
        if isinstance(a.get("id"), str)
    }


async def observer_changement_ecran(user_id: str, avant: dict[str, str]) -> str:
    """
    Apres un clic reussi : attend que l'ecran se stabilise, puis decrit au
    modele ce qui est apparu ou disparu par rapport a `avant`
    (photographier_ecran pris juste avant le clic). C'est ce qui lui
    permet de continuer apres l'ouverture d'un menu ou d'un tiroir sans
    deviner : il voit les nouveaux elements avec leurs id.
    """
    await asyncio.sleep(DELAI_OBSERVATION_ECRAN_SECONDES)
    apres = photographier_ecran(user_id)
    apparus = [(aid, desc) for aid, desc in apres.items() if aid not in avant]
    disparus = [aid for aid in avant if aid not in apres]

    if not apparus and not disparus:
        return "L'écran n'a pas visiblement changé après ce clic."

    texte = ""
    if apparus:
        cites = apparus[:NB_MAX_ELEMENTS_CITES_APRES_CLIC]
        texte += "Éléments apparus à l'écran après ce clic :\n"
        texte += "\n".join(f"- {aid} : {desc}" for aid, desc in cites)
        if len(apparus) > len(cites):
            texte += f"\n(et {len(apparus) - len(cites)} autres)"
        texte += "\n"
    if disparus:
        texte += "Ids qui ne sont plus à l'écran (ne les réutilise pas) : " + ", ".join(disparus[:NB_MAX_ELEMENTS_CITES_APRES_CLIC]) + "\n"
    return texte.strip()


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
    qui trouve un element correspondant, VISIBLE et ACTIF, execute le
    clic reel directement (plus de confirmation, decision Bourama du
    19/09/2026, voir lib/canalAgentApplicatif.ts).
    """
    correlation_id = str(uuid.uuid4())
    return await _diffuser_et_attendre(
        user_id,
        {"id": correlation_id, "selecteur_generique": selecteur, "description": description},
        on_statut,
        on_timeout_log=f"selecteur={selecteur}",
    )


async def demander_pointage_action(user_id: str, action_id: str, on_statut=None) -> Any | None:
    """
    Chantier G (mode guidage). Diffuse {montrer_action_id} : demande
    UNIQUEMENT de deplacer le curseur virtuel vers l'element de
    `action_id`, sans jamais l'executer -- pour que Classinus puisse
    montrer une nouveaute a l'etudiant en l'expliquant dans le chat,
    sans agir a sa place. Jamais de confirmation cote frontend pour ce
    cas (voir lib/canalAgentApplicatif.ts) : un pointage visuel n'a
    aucun effet sur les donnees de l'etudiant.
    """
    correlation_id = str(uuid.uuid4())
    return await _diffuser_et_attendre(
        user_id,
        {"id": correlation_id, "montrer_action_id": action_id},
        on_statut,
        on_timeout_log=f"pointage action={action_id}",
    )


async def demander_ecriture_champ(user_id: str, action_id: str, texte: str, on_statut=None) -> Any | None:
    """
    Ajoute le 20/09/2026 (demande Bourama : donner a Classinus la
    possibilite d'ecrire dans les champs, pas seulement cliquer). Meme
    principe que demander_execution_action, mais pour remplir un champ
    de saisie : diffuse {action_id, texte_a_ecrire} a toutes les
    connexions actives de user_id, la premiere connexion qui trouve
    l'element correspondant, VISIBLE et ACTIF, tape le texte reellement
    (avec une frappe visible cote frontend, voir traiterDemandeEcriture
    dans lib/canalAgentApplicatif.ts). Aucune confirmation cote
    etudiant, meme regle que le reste de ce chantier depuis le
    19/09/2026.
    """
    correlation_id = str(uuid.uuid4())
    return await _diffuser_et_attendre(
        user_id,
        {"id": correlation_id, "action_id": action_id, "texte_a_ecrire": texte},
        on_statut,
        on_timeout_log=f"ecriture action={action_id}",
    )


async def pousser_texte_clovis(user_id: str, texte: str) -> int:
    """
    Chantier P (19/09/2026, decision Bourama) : commentaire libre de
    Clovis pendant qu'il agit. Contrairement aux demandes ci-dessus, rien
    n'est attendu en retour : le texte est simplement diffuse a TOUTES les
    connexions actives de `user_id` (meme principe, aucune cible unique),
    et chacune l'affiche dans la bulle de dialogue du canal en direct
    (voir lib/canalAgentApplicatif.ts cote frontend).

    Le texte vient du modele du tour de conversation en cours, via
    l'outil dire_a_l_etudiant (core/outils_action_agent.py) : c'est lui
    qui voit et sait ce qu'il fait, donc lui qui juge ce qui vaut la peine
    d'etre dit. Pas de nouvel appel LLM dedie.

    Renvoie le nombre de connexions atteintes (0 si l'application n'est
    ouverte nulle part pour ce compte).
    """
    async with _verrou_connexions:
        connexions = [(cle, ws) for cle, ws in _connexions.items() if cle[0] == user_id]

    atteintes = 0
    for cle, websocket in connexions:
        verrou_envoi = await _verrou_envoi_pour(cle)
        try:
            async with verrou_envoi:
                await websocket.send_json({"texte_clovis": texte})
            atteintes += 1
        except Exception as e:
            logging.error(f"ERREUR poussee texte Clovis canal agent applicatif (user={user_id}, appareil={cle[1]}) : {e}")
    return atteintes


async def demander_ouverture_canal(user_id: str, conversation_id: str | None, texte_suite: str) -> int:
    """
    Demo (20/09/2026) : demande au frontend d'ouvrir le canal en direct sur
    la conversation `conversation_id` (celle de la demo, pour que le mode
    demo continue), puis programme `texte_suite` comme message du chat a
    envoyer des que le tour en cours est termine (voir terminer_tour).

    Une SEULE connexion est visee (la meme que renvoyer_messages_non_lus :
    le canal ne doit s'ouvrir qu'a un seul endroit, et le message de suite
    doit partir de cet endroit-la). Renvoie 0 si l'application n'est
    ouverte nulle part pour ce compte (rien n'est alors programme).
    """
    async with _verrou_connexions:
        connexions = [(cle, ws) for cle, ws in _connexions.items() if cle[0] == user_id]
    if not connexions:
        return 0
    cle, websocket = connexions[0]
    verrou_envoi = await _verrou_envoi_pour(cle)
    try:
        async with verrou_envoi:
            await websocket.send_json({"ouvrir_canal_en_direct": {"conversation_id": conversation_id}})
    except Exception as e:
        logging.error(f"ERREUR ouverture canal en direct (user={user_id}, appareil={cle[1]}) : {e}")
        return 0
    with _verrou_messages_etudiant:
        _continuations_canal[user_id] = texte_suite
    return 1


# Message de l'etudiant PENDANT que Clovis travaille (canal en direct,
# 19/09/2026, decision Bourama : "il faut que ton message soit envoye").
# Le frontend l'envoie sur ce canal ; s'il existe un tour de conversation
# en cours pour ce compte, le message est mis en file et la boucle d'agent
# (core/boucle_agent.py) le lit au prochain aller-retour avec le modele.
# Sinon il n'est PAS garde ici : le frontend l'envoie alors comme un message
# normal dans le chat (accuse pris_en_compte=False).
# Structures sous verrou threading (et non asyncio) : la boucle d'agent est
# un generateur synchrone execute dans un thread, le canal WebSocket est
# asynchrone.
LONGUEUR_MAX_MESSAGE_ETUDIANT = 2000

_verrou_messages_etudiant = threading.Lock()
_messages_etudiant: dict[str, list[str]] = {}
_tours_en_cours: dict[str, int] = {}
# Demo (20/09/2026, decision Bourama : la demo tourne dans le chat normal
# et n'ouvre le canal en direct qu'au moment de le demontrer) : texte a
# renvoyer comme message du chat a la FIN du tour en cours, une fois le
# canal ouvert (voir demander_ouverture_canal). Pas avant : ce tour-ci a
# ete lance sans les outils de clic, seul un NOUVEAU tour les a.
_continuations_canal: dict[str, str] = {}
_boucle_evenements: "asyncio.AbstractEventLoop | None" = None


def debuter_tour(user_id: str) -> None:
    with _verrou_messages_etudiant:
        _tours_en_cours[user_id] = _tours_en_cours.get(user_id, 0) + 1


def terminer_tour(user_id: str) -> list[str]:
    """
    Fin d'un tour de conversation. Renvoie les messages de l'etudiant que
    la boucle n'a jamais eu l'occasion de lire (arrives pendant le tout
    dernier appel au modele, ou sur un chemin de reprise sans injection) :
    ils sont retires de la file et doivent etre renvoyes au frontend.
    """
    with _verrou_messages_etudiant:
        restant = _tours_en_cours.get(user_id, 0) - 1
        if restant > 0:
            _tours_en_cours[user_id] = restant
            return []
        _tours_en_cours.pop(user_id, None)
        non_lus = _messages_etudiant.pop(user_id, [])
        suite = _continuations_canal.pop(user_id, None)
        if suite:
            non_lus = non_lus + [suite]
        return non_lus


def deposer_message_etudiant(user_id: str, texte: str) -> bool:
    """True si un tour est en cours (message mis en file), False sinon."""
    with _verrou_messages_etudiant:
        if _tours_en_cours.get(user_id, 0) <= 0:
            return False
        _messages_etudiant.setdefault(user_id, []).append(texte)
        return True


def retirer_messages_etudiant(user_id: str) -> list[str]:
    if not user_id:
        return []
    with _verrou_messages_etudiant:
        return _messages_etudiant.pop(user_id, [])


async def accuser_message_etudiant(user_id: str, appareil_id: str, id_message: Any, texte: str, websocket: WebSocket) -> None:
    """Depose le message et renvoie a CETTE connexion l'accuse de reception."""
    propre = (texte or "").strip()[:LONGUEUR_MAX_MESSAGE_ETUDIANT]
    pris_en_compte = deposer_message_etudiant(user_id, propre) if propre else False
    verrou_envoi = await _verrou_envoi_pour((user_id, appareil_id))
    try:
        async with verrou_envoi:
            await websocket.send_json({"accuse_message_etudiant": id_message, "pris_en_compte": pris_en_compte})
    except Exception as e:
        logging.error(f"ERREUR accuse message etudiant canal agent applicatif (user={user_id}, appareil={appareil_id}) : {e}")


async def _renvoyer_messages_non_lus(user_id: str, textes: list[str]) -> None:
    async with _verrou_connexions:
        connexions = [(cle, ws) for cle, ws in _connexions.items() if cle[0] == user_id]
    if not connexions:
        return
    # Une seule connexion suffit : le message doit partir UNE fois dans le chat.
    cle, websocket = connexions[0]
    verrou_envoi = await _verrou_envoi_pour(cle)
    for texte in textes:
        try:
            async with verrou_envoi:
                await websocket.send_json({"message_etudiant_renvoye": texte})
        except Exception as e:
            logging.error(f"ERREUR renvoi message etudiant non lu (user={user_id}, appareil={cle[1]}) : {e}")


def renvoyer_messages_non_lus(user_id: str, textes: list[str]) -> None:
    """Appelable depuis un thread synchrone (fin du flux SSE du chat)."""
    if not textes or _boucle_evenements is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(_renvoyer_messages_non_lus(user_id, textes), _boucle_evenements)
    except Exception as e:
        logging.error(f"ERREUR planification renvoi message etudiant non lu (user={user_id}) : {e}")
