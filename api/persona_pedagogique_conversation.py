"""Item 9 des specs indépendantes ScholarFlow AI (volet étudiant),
12/09/2026, demande Bourama -- voir core/persona_pedagogique_conversation.py.
Léger : deux routes, lire et définir le mode pédagogique actif d'une
conversation. Même forme que api/mode_actif_conversation.py, mais SANS la
règle de verrouillage mineur de ce dernier -- cette règle est spécifique
au rattachement enseignant (implications légales de la "confiance
pédagogique"), rien ne l'a demandée ici pour un simple choix de persona
pédagogique. À ajouter seulement si Bourama le demande explicitement.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.persona_pedagogique_conversation import (
    obtenir_persona_pedagogique,
    definir_persona_pedagogique,
)

router_persona_pedagogique = APIRouter(prefix="/api/conversations", tags=["persona_pedagogique"])


@router_persona_pedagogique.get("/{conversation_id}/persona-pedagogique")
def lire(conversation_id: str, utilisateur=Depends(utilisateur_courant)):
    persona = obtenir_persona_pedagogique(conversation_id, utilisateur.id)
    return {"persona": persona}


class PersonaPedagogiquePayload(BaseModel):
    persona: str | None = None


@router_persona_pedagogique.put("/{conversation_id}/persona-pedagogique")
def definir(conversation_id: str, payload: PersonaPedagogiquePayload, utilisateur=Depends(utilisateur_courant)):
    resultat = definir_persona_pedagogique(conversation_id, utilisateur.id, payload.persona)
    if resultat is None and payload.persona is not None:
        raise erreur_api(400, "PERSONA_PEDAGOGIQUE_INVALIDE")
    return {"persona": resultat["persona"] if resultat else None}
