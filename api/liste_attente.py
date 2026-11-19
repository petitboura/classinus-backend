"""
Routes de la liste d'attente des modeles "Bientot" (16/11/2026, demande de Bourama).

Toute la logique vit dans core/liste_attente.py. Ces routes servent le formulaire qui s'ouvre
quand l'utilisateur clique sur un modele grise du selecteur. Aucun paiement n'est pris.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth import utilisateur_courant, utilisateur_optionnel
from core import liste_attente
from core.erreurs import erreur_api
from core.limitation_debit import limiteur

router_liste_attente = APIRouter(prefix="/api/liste-attente", tags=["liste-attente"])


def _lever(e: liste_attente.ErreurListeAttente):
    raise erreur_api(e.statut_http, e.code)


class InscriptionPayload(BaseModel):
    modele_id: str
    palier_prix: int
    # Facultatif depuis le parcours de paiement (19/11/2026) ; refuse s'il est fourni et inconnu.
    profil: Optional[str] = None
    consentement: bool
    pays: Optional[str] = None
    whatsapp: Optional[str] = None
    langue: Optional[str] = None
    source: Optional[str] = None
    moyen_paiement: Optional[str] = None


class EvenementPayload(BaseModel):
    etape: str
    modele_id: Optional[str] = None
    langue: Optional[str] = None
    source: Optional[str] = None


@router_liste_attente.get("/config")
@limiteur.limit("30/minute")
def lire_config(request: Request, utilisateur=Depends(utilisateur_optionnel)):
    """
    Paliers, textes (francais et anglais) et inscription active de l'utilisateur.

    Route publique (18/11/2026) : la page /abonnements est visible sans compte. Un visiteur recoit les
    paliers et les textes, avec une inscription nulle. Le compte n'est exige qu'a l'inscription.
    """
    try:
        return liste_attente.charger_config(utilisateur.id if utilisateur else None)
    except liste_attente.ErreurListeAttente as e:
        _lever(e)


@router_liste_attente.post("")
@limiteur.limit("10/minute")
def s_inscrire(request: Request, payload: InscriptionPayload, utilisateur=Depends(utilisateur_courant)):
    try:
        return liste_attente.inscrire(
            utilisateur.id,
            getattr(utilisateur, "email", None),
            payload.modele_id,
            payload.palier_prix,
            payload.profil,
            payload.consentement,
            pays=payload.pays,
            whatsapp=payload.whatsapp,
            langue=payload.langue,
            source=payload.source,
            moyen_paiement=payload.moyen_paiement,
        )
    except liste_attente.ErreurListeAttente as e:
        _lever(e)


@router_liste_attente.post("/desinscription")
@limiteur.limit("10/minute")
def se_desinscrire(request: Request, utilisateur=Depends(utilisateur_courant)):
    """Retire l'utilisateur de la liste d'attente (une seule liste, donc aucun modele a preciser)."""
    try:
        return liste_attente.desinscrire(utilisateur.id)
    except liste_attente.ErreurListeAttente as e:
        _lever(e)


@router_liste_attente.post("/evenement")
@limiteur.limit("60/minute")
def noter_evenement(request: Request, payload: EvenementPayload, utilisateur=Depends(utilisateur_optionnel)):
    """Une etape de l'entonnoir (ouverture du selecteur, clic, ouverture de la page)."""
    if payload.etape == "inscription_validee":
        # Cette etape n'est ecrite que par l'inscription elle-meme, jamais par le client.
        raise erreur_api(400, "LISTE_ATTENTE_ETAPE_INVALIDE")
    if utilisateur is None:
        # Un visiteur sans compte n'a pas d'identifiant a noter : on ne garde rien, sans erreur.
        return {"ok": True}
    try:
        liste_attente.enregistrer_evenement(
            utilisateur.id, payload.etape, payload.modele_id, payload.langue, payload.source
        )
    except liste_attente.ErreurListeAttente as e:
        _lever(e)
    return {"ok": True}
