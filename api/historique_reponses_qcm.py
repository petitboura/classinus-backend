"""Item 2 des specs indépendantes ScholarFlow AI (volet étudiant),
14/09/2026, demande Bourama -- voir core/historique_reponses_qcm.py.
Une seule route, en écriture : QCMInteractif.tsx (item 3) l'appelle
au moment où l'étudiant sélectionne une réponse, pour brancher la
jonction "QCM complet" (item 3 -> item 5 -> item 2, voir
specs-independantes.md).

Volontairement PAS d'erreur 500 si l'écriture échoue côté base -- la
correction est déjà affichée côté frontend avant cet appel (état local
du composant), un échec d'historisation ne doit jamais se répercuter sur
l'expérience de l'étudiant. `enregistre` dans la réponse indique si
l'écriture a réussi, purement informatif (pas utilisé aujourd'hui côté
frontend, QCMInteractif.tsx ignore délibérément le résultat de l'appel).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.historique_reponses_qcm import enregistrer_reponse_qcm

router_historique_reponses_qcm = APIRouter(prefix="/api/conversations", tags=["historique_reponses_qcm"])


class ReponseQCMPayload(BaseModel):
    question: str
    choix: list[str]
    reponse_choisie: int
    reponse_correcte: int
    explication: str | None = None


@router_historique_reponses_qcm.post("/{conversation_id}/reponses-qcm")
def enregistrer(conversation_id: str, payload: ReponseQCMPayload, utilisateur=Depends(utilisateur_courant)):
    resultat = enregistrer_reponse_qcm(
        conversation_id,
        utilisateur.id,
        payload.question,
        payload.choix,
        payload.reponse_choisie,
        payload.reponse_correcte,
        payload.explication,
    )
    return {"enregistre": resultat is not None}
