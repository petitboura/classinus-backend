"""
Routes des minuteurs du chat (20/09/2026, demande Bourama) : ce que
l'etudiant fait avec les boutons de la carte (lancer, arreter, ajouter ou
retirer du temps) et la prise en charge de la fin d'un minuteur.
Meme logique que l'outil de Clovis (core/outils_minuteurs.py) : tout passe
par core/minuteurs.py.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
from core.minuteurs import (
    ErreurMinuteur,
    ajuster_minuteur,
    arreter_minuteur,
    creer_minuteur,
    lister_minuteurs_actifs,
    serialiser,
    terminer_minuteur,
)

router_minuteurs = APIRouter(prefix="/api/minuteurs", tags=["minuteurs"])


def _lever(e: ErreurMinuteur):
    raise erreur_api(e.statut_http, e.code)


class LancerMinuteurPayload(BaseModel):
    duree_secondes: int
    titre: Optional[str] = None
    # Ce que Clovis fera a la fin. Facultatif quand c'est l'etudiant qui
    # lance : Clovis decidera alors selon la conversation.
    action_fin: Optional[str] = None
    conversation_id: Optional[str] = None


class ModifierMinuteurPayload(BaseModel):
    # Positif pour ajouter du temps, negatif pour en retirer.
    ajuster_secondes: Optional[int] = None
    titre: Optional[str] = None


@router_minuteurs.get("")
def lister(utilisateur=Depends(utilisateur_courant)):
    """Minuteurs en cours. `maintenant` (horloge du serveur) permet a
    l'appli de corriger l'ecart avec l'horloge de l'appareil."""
    try:
        maintenant = datetime.now(timezone.utc)
        return {
            "minuteurs": [serialiser(m, maintenant) for m in lister_minuteurs_actifs(utilisateur.id)],
            "maintenant": maintenant.isoformat(),
        }
    except ErreurMinuteur as e:
        _lever(e)


@router_minuteurs.post("")
def lancer(payload: LancerMinuteurPayload, utilisateur=Depends(utilisateur_courant)):
    try:
        ligne = creer_minuteur(
            utilisateur.id,
            payload.duree_secondes,
            titre=payload.titre,
            action_fin=payload.action_fin,
            lance_par="etudiant",
            conversation_id=payload.conversation_id,
        )
        return {"minuteur": serialiser(ligne)}
    except ErreurMinuteur as e:
        _lever(e)


@router_minuteurs.patch("/{minuteur_id}")
def modifier(minuteur_id: str, payload: ModifierMinuteurPayload, utilisateur=Depends(utilisateur_courant)):
    try:
        ligne = ajuster_minuteur(
            utilisateur.id,
            minuteur_id,
            ajuster_secondes=payload.ajuster_secondes or 0,
            titre=payload.titre,
        )
        return {"minuteur": serialiser(ligne)}
    except ErreurMinuteur as e:
        _lever(e)


@router_minuteurs.post("/{minuteur_id}/arreter")
def arreter(minuteur_id: str, utilisateur=Depends(utilisateur_courant)):
    try:
        return {"minuteur": serialiser(arreter_minuteur(utilisateur.id, minuteur_id))}
    except ErreurMinuteur as e:
        _lever(e)


@router_minuteurs.post("/{minuteur_id}/terminer")
def terminer(minuteur_id: str, utilisateur=Depends(utilisateur_courant)):
    """L'appli signale qu'un minuteur est arrive a zero. `a_traiter` vaut
    True pour UN SEUL appelant (meme si l'appli est ouverte a plusieurs
    endroits) : c'est celui-la qui reveille Clovis, les autres ne font
    rien."""
    try:
        a_traiter, ligne = terminer_minuteur(utilisateur.id, minuteur_id)
        return {"a_traiter": a_traiter, "minuteur": serialiser(ligne)}
    except ErreurMinuteur as e:
        _lever(e)
