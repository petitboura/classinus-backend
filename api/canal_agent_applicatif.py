import asyncio
"""
Chantier agent applicatif, chantier C -- route WebSocket separee de
api/canal_temps_reel.py (decision 0.1 : canal dedie, pas d'extension de
l'existant).
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import supabase
from core.canal_agent_applicatif import (
    accuser_message_etudiant,
    connecter,
    deconnecter,
    mettre_a_jour_etat_actions,
    recevoir_reponse,
)
from core.canal_temps_reel import fermer_websocket_sans_erreur

router = APIRouter(prefix="/api/canal-agent-applicatif", tags=["canal-agent-applicatif"])


def _verifier_token(token: str):
    if not token:
        return None
    try:
        reponse = supabase.auth.get_user(token)
    except Exception as e:
        logging.error(f"ERREUR verification token canal agent applicatif : {e}")
        return None
    if not reponse or not reponse.user:
        return None
    return reponse.user


@router.websocket("/ws")
async def canal_temps_reel(websocket: WebSocket):
    # Le token Supabase et l'identifiant d'appareil sont envoyés dans le
    # premier message après l'ouverture. Un token bearer ne doit pas être
    # placé dans l'URL : les URLs peuvent être journalisées par des proxies.
    await websocket.accept()
    try:
        message_auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await fermer_websocket_sans_erreur(websocket, 4401)
        return

    utilisateur = _verifier_token(str(message_auth.get("auth_token") or ""))
    if utilisateur is None:
        await fermer_websocket_sans_erreur(websocket, 4401)
        return
    appareil_id = str(message_auth.get("appareil_id") or "")
    await connecter(utilisateur.id, appareil_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()
            correlation_id = message.get("id")
            if correlation_id is not None and "resultat" in message:
                recevoir_reponse(correlation_id, message.get("resultat"))
            elif "etat_actions" in message and isinstance(message.get("etat_actions"), list):
                mettre_a_jour_etat_actions(utilisateur.id, appareil_id, message["etat_actions"])
            elif isinstance(message.get("message_etudiant"), str):
                await accuser_message_etudiant(
                    utilisateur.id, appareil_id, message.get("id_message"), message["message_etudiant"], websocket
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"ERREUR canal agent applicatif (user={utilisateur.id}, appareil={appareil_id}) : {e}")
    finally:
        await deconnecter(utilisateur.id, appareil_id, websocket)
