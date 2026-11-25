"""
Page "Permissions des outils" (25/11/2026) : réglages d'une application connectée ou d'un serveur MCP
personnalisé, ouverts depuis le panneau de l'application.

- GET /api/permissions-outils/{groupe} : deux catégories (lecture, écriture), chacune avec son réglage
  (autoriser, demander, bloquer) et ses outils, chacun avec son réglage propre éventuel.
- PUT /api/permissions-outils/{groupe} : {"cle", "etat"}. `cle` est un outil ou une catégorie
  ("categorie:<groupe>:lecture"). etat vaut "autoriser", "demander", "bloquer", ou null pour retirer
  le réglage (la valeur par défaut s'applique de nouveau).

Règles et calculs : core/permissions_outils.py. Liste des outils : core/catalogue_permissions.py.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant, get_secret
from api.journal import journaliser
from core import catalogue_permissions
from core.erreurs import erreur_api
from core.permissions_outils import (
    ECRITURE,
    LONGUEUR_MAX_CLE,
    appartient_au_groupe,
    charger_permissions,
    construire_vue,
    ecrire_etat,
    est_cle_categorie,
    groupe_valide,
    lire_lignes,
    retirer_reglage,
    valider_reglage,
)

router = APIRouter(prefix="/api/permissions-outils", tags=["permissions_outils"])

_CODE_PAR_REFUS = {
    "etat_invalide": "PERMISSIONS_OUTILS_REGLAGE_INVALIDE",
    "groupe_invalide": "PERMISSIONS_OUTILS_APPLICATION_INCONNUE",
    "cle_invalide": "PERMISSIONS_OUTILS_REGLAGE_INVALIDE",
    "categorie_invalide": "PERMISSIONS_OUTILS_REGLAGE_INVALIDE",
    "outil_hors_application": "PERMISSIONS_OUTILS_REGLAGE_INVALIDE",
    "autorisation_interdite": "PERMISSIONS_OUTILS_AUTORISATION_INTERDITE",
}


class DemandeReglage(BaseModel):
    cle: str = Field(min_length=1, max_length=LONGUEUR_MAX_CLE)
    etat: Optional[str] = Field(default=None, max_length=20)


def _est_serveur_perso(groupe):
    return groupe.startswith("custommcp_")


def _verifier_groupe(groupe, user_id):
    if not groupe_valide(groupe):
        raise erreur_api(404, "PERMISSIONS_OUTILS_APPLICATION_INCONNUE")
    if _est_serveur_perso(groupe):
        try:
            possede = catalogue_permissions.serveur_perso_appartient(groupe, user_id)
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (serveurs perso user={user_id}) : {e}")
            raise erreur_api(500, "PERMISSIONS_OUTILS_LECTURE_ECHEC")
        if not possede:
            raise erreur_api(404, "PERMISSIONS_OUTILS_APPLICATION_INCONNUE")


@router.get("/{groupe}")
def lire(groupe: str, utilisateur=Depends(utilisateur_courant)):
    _verifier_groupe(groupe, utilisateur.id)
    try:
        if _est_serveur_perso(groupe):
            outils = catalogue_permissions.lister_outils_serveur(groupe, utilisateur.id)
        else:
            outils = catalogue_permissions.lister_outils_application(groupe, utilisateur.id, get_secret)
    except Exception as e:
        logging.error(f"ERREUR PERMISSIONS (catalogue {groupe} user={utilisateur.id}) : {e}")
        raise erreur_api(502, "PERMISSIONS_OUTILS_CATALOGUE_INDISPONIBLE")
    # Un réglage posé sur un outil qui n'est plus dans le catalogue (serveur injoignable, outil retiré)
    # reste visible : sinon la personne ne pourrait pas le défaire.
    try:
        permissions = charger_permissions(utilisateur.id)
        lignes = lire_lignes(utilisateur.id)
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture permissions_outils user={utilisateur.id}) : {e}")
        raise erreur_api(500, "PERMISSIONS_OUTILS_LECTURE_ECHEC")
    connues = {o["cle"] for o in outils}
    for ligne in lignes:
        cle = ligne["cle"]
        if cle in connues or est_cle_categorie(cle) or not appartient_au_groupe(cle, groupe):
            continue
        outils.append({"cle": cle, "nom_lisible": ligne.get("nom_lisible") or cle, "type": ECRITURE})
    return construire_vue(groupe, outils, permissions)


@router.put("/{groupe}", status_code=204)
def regler(groupe: str, demande: DemandeReglage, request: Request, utilisateur=Depends(utilisateur_courant)):
    _verifier_groupe(groupe, utilisateur.id)
    # Retirer un réglage : seuls la clé et le groupe comptent.
    refus = valider_reglage(groupe, demande.cle, demande.etat if demande.etat is not None else "demander")
    if refus and not (demande.etat is None and refus == "autorisation_interdite"):
        raise erreur_api(400, _CODE_PAR_REFUS.get(refus, "PERMISSIONS_OUTILS_REGLAGE_INVALIDE"))
    try:
        if demande.etat is None:
            retirer_reglage(utilisateur.id, demande.cle)
        else:
            ecrire_etat(utilisateur.id, demande.cle, demande.etat)
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (écriture permissions_outils user={utilisateur.id} cle={demande.cle}) : {e}")
        raise erreur_api(500, "PERMISSIONS_OUTILS_ECRITURE_ECHEC")
    journaliser(
        action="outils.permission_modifiee",
        user_id=utilisateur.id,
        cible_type="profile",
        cible_id=utilisateur.id,
        details={"groupe": groupe, "cle": demande.cle, "etat": demande.etat},
        request=request,
    )
