"""
Messages et réponses envoyés pendant que Classinus travaille (chat normal).

Chantier "messages et questions pendant que Classinus travaille" (25/11/2026,
demande de Bourama). Deux routes, qui ne font que passer par les mêmes
structures que le canal en direct (core/canal_agent_applicatif.py) :

- POST /api/chat/message-en-cours : un message libre écrit pendant un tour. S'il
  y a un tour en cours, il est mis dans la file que la boucle d'agent
  (core/boucle_agent.py) relit à chaque aller-retour avec le modèle. Sinon, ou
  s'il est trop long pour la file, la réponse dit pris_en_compte=false et la page
  l'envoie comme un message normal (rien n'est jamais coupé ni perdu).
- POST /api/chat/question-reponse : la réponse à une carte posée par l'outil
  poser_question (core/outils_question.py). Question bloquante en attente : elle
  la reçoit et le tour reprend. Sinon (question non bloquante, délai dépassé),
  la réponse passe par la file comme un message, ou est renvoyée à la page.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import utilisateur_optionnel
from core.canal_agent_applicatif import (
    LONGUEUR_MAX_MESSAGE_ETUDIANT,
    deposer_message_etudiant,
    repondre_question,
)
from core.erreurs import erreur_api
from core.questions_utilisateur import LONGUEUR_MAX_REPONSE_QUESTION

router = APIRouter(prefix="/api/chat", tags=["chat"])

LONGUEUR_MAX_TEXTE_QUESTION_FILE = 300


class MessageEnCoursPayload(BaseModel):
    texte: str = Field(..., max_length=LONGUEUR_MAX_REPONSE_QUESTION)


class ReponseQuestionPayload(BaseModel):
    id_question: str = Field(..., min_length=1, max_length=200)
    reponse: str = Field(..., max_length=LONGUEUR_MAX_REPONSE_QUESTION)
    # Texte de la question, repris dans le message de la file pour que le modèle sache
    # à quoi la réponse correspond quand elle ne retrouve pas une attente.
    question: Optional[str] = Field(None, max_length=LONGUEUR_MAX_TEXTE_QUESTION_FILE)


@router.post("/message-en-cours")
async def deposer_message_en_cours(
    payload: MessageEnCoursPayload,
    utilisateur=Depends(utilisateur_optionnel),
):
    texte = payload.texte.strip()
    if not texte:
        raise erreur_api(422, "REPONSE_CHAT_VIDE")
    user_id = utilisateur.id if utilisateur else None
    if not user_id or len(texte) > LONGUEUR_MAX_MESSAGE_ETUDIANT:
        return {"pris_en_compte": False}
    return {"pris_en_compte": deposer_message_etudiant(user_id, texte)}


@router.post("/question-reponse")
async def repondre_a_une_question(
    payload: ReponseQuestionPayload,
    utilisateur=Depends(utilisateur_optionnel),
):
    texte = payload.reponse.strip()
    if not texte:
        raise erreur_api(422, "REPONSE_CHAT_VIDE")
    user_id = utilisateur.id if utilisateur else None
    if not user_id:
        return {"statut": "a_renvoyer", "pris_en_compte": False}
    if repondre_question(user_id, payload.id_question, texte):
        return {"statut": "recue", "pris_en_compte": True}
    question = (payload.question or "").strip()
    texte_file = f"Réponse à ta question « {question} » : {texte}" if question else f"Réponse à ta question : {texte}"
    if len(texte_file) <= LONGUEUR_MAX_MESSAGE_ETUDIANT and deposer_message_etudiant(user_id, texte_file):
        return {"statut": "en_file", "pris_en_compte": True}
    return {"statut": "a_renvoyer", "pris_en_compte": False}
