"""Relais des appels d'outils lances depuis un widget MCP (08/11/2026).

POST /api/widgets/appel-outil : le frontend y transmet le `tools/call` d'un widget. Regles dans
core/widgets_appel_outil.py : meme serveur que le widget, confirmation pour ce qui modifie ou coute.

Reponse :
- {"statut": "ok", "contenu": [{"type": "text", "text": ...}], "est_erreur": bool}
- {"statut": "confirmation_requise", "nom_lisible": ..., "plateforme": ..., "cle": ...} : le frontend
  demande la confirmation, puis renvoie la meme demande avec approuve=true.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth import utilisateur_courant, get_secret
from api.journal import journaliser
from core.autorisations_outils import charger_autorisations, enregistrer_autorisation
from core.constantes_agent import AGENT_ID_PAR_DEFAUT
from core.erreurs import erreur_api
from core.execution_outils import cle_autorisation_appel
from core.limitation_debit import limiteur
from core.mcp_tools import appeler_outil, lister_outils_autorises_pour_agent
from core.profils_agents import _nom_lisible_appel
from core.registre_outils import plateforme_outil_personnel
from core.widgets_appel_outil import (
    ErreurWidget,
    LONGUEUR_MAX_NOM,
    appel_au_format_chat,
    est_erreur,
    resoudre_appel,
    texte_pour_widget,
)

router = APIRouter(prefix="/api/widgets", tags=["widgets_outils"])


class DemandeAppelWidget(BaseModel):
    outil_source: str = Field(min_length=1, max_length=LONGUEUR_MAX_NOM)
    nom_outil: str = Field(min_length=1, max_length=LONGUEUR_MAX_NOM)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    approuve: bool = False
    toujours_autoriser: bool = False


@router.post("/appel-outil")
@limiteur.limit("60/minute")
def appeler_outil_de_widget(request: Request, demande: DemandeAppelWidget, utilisateur=Depends(utilisateur_courant)):
    try:
        _, table_routage = lister_outils_autorises_pour_agent(get_secret, utilisateur.id, AGENT_ID_PAR_DEFAUT)
    except Exception as e:
        logging.error(f"ERREUR WIDGET (catalogue outils user={utilisateur.id}) : {e}")
        raise erreur_api(502, "WIDGET_APPEL_ECHEC")
    try:
        nom_expose = resoudre_appel(demande.outil_source, demande.nom_outil, table_routage)
    except ErreurWidget as e:
        raise erreur_api(403 if e.code == "WIDGET_APPEL_REFUSE" else 404, e.code)

    appel = appel_au_format_chat(nom_expose, demande.arguments)
    cle = cle_autorisation_appel(appel)
    if cle is not None and not demande.approuve and cle not in charger_autorisations(utilisateur.id):
        return {
            "statut": "confirmation_requise",
            "nom_lisible": _nom_lisible_appel(appel),
            "plateforme": plateforme_outil_personnel(nom_expose),
            "cle": cle,
        }
    if cle is not None and demande.approuve and demande.toujours_autoriser:
        enregistrer_autorisation(utilisateur.id, cle, _nom_lisible_appel(appel))

    try:
        resultat = appeler_outil(nom_expose, demande.arguments, table_routage)
    except Exception as e:
        logging.error(f"ERREUR WIDGET (appel {nom_expose} user={utilisateur.id}) : {e}")
        raise erreur_api(502, "WIDGET_APPEL_ECHEC")
    if cle is not None:
        journaliser(
            action="outils.widget_appel_confirme",
            user_id=utilisateur.id,
            cible_type="profile",
            cible_id=utilisateur.id,
            details={"outil": nom_expose, "source": demande.outil_source},
            request=request,
        )
    return {
        "statut": "ok",
        "contenu": [{"type": "text", "text": texte_pour_widget(resultat)}],
        "est_erreur": est_erreur(resultat),
    }
