"""
Chantier agent applicatif, chantier C -- route WebSocket separee de
api/canal_temps_reel.py (decision 0.1 : canal dedie, pas d'extension de
l'existant).
"""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.auth import supabase
from core.canal_agent_applicatif import connecter, deconnecter, mettre_a_jour_etat_actions, recevoir_reponse

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
async def canal_agent_applicatif(
    websocket: WebSocket, token: str = Query(default=""), appareil_id: str = Query(default="")
):
    """
    CONTRAT FRONTEND : ouvrir cette connexion des que l'app est au
    premier plan (meme cycle de vie que le canal temps reel existant,
    voir lib/canalAgentApplicatif.ts). Trois formes de message recues :
    - {"id": ..., "action_id": ...} : demande d'execution (chantier C) ;
    - {"id": ..., "resultat": ...} : reponse de CE frontend a une
      demande d'execution ;
    - {"etat_actions": [...]} : poussee de l'etat courant des actions
      disponibles sur CETTE connexion (chantier D), envoyee a
      l'ouverture puis a chaque changement cote frontend.
    """
    utilisateur = _verifier_token(token)
    if utilisateur is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await connecter(utilisateur.id, appareil_id, websocket)

    try:
        while True:
            message = await websocket.receive_json()
            correlation_id = message.get("id")
            if correlation_id is not None and "resultat" in message:
                recevoir_reponse(correlation_id, message.get("resultat"))
            elif "etat_actions" in message and isinstance(message.get("etat_actions"), list):
                mettre_a_jour_etat_actions(utilisateur.id, appareil_id, message["etat_actions"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"ERREUR canal agent applicatif (user={utilisateur.id}, appareil={appareil_id}) : {e}")
    finally:
        await deconnecter(utilisateur.id, appareil_id, websocket)
