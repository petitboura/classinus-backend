"""
Outil MCP pour basculer (poser/retirer) l'étoile de l'utilisateur sur un
élément du catalogue public, au nom de l'utilisateur -- 17/09/2026,
demande Bourama : même geste que le clic sur l'icône étoile des cartes
(voir components/BoutonEtoile.tsx côté frontend), mais accessible en le
demandant simplement à l'IA. Toute la logique vit dans
core/etoiles_catalogue_public.py (réutilisée aussi par
api/etoiles_catalogue_public.py côté clic direct, et par le futur outil
équivalent côté serveur MCP public, voir core/serveur_mcp_espace.py).
"""

import logging

from core.outils_generation_commun import mcp_generation, Context
from core.etoiles_catalogue_public import basculer_etoile as _basculer_etoile


@mcp_generation.tool()
def basculer_etoile_catalogue_public(type_element: str, element_id: str, ctx: Context) -> str:
    """
    Pose l'étoile de l'utilisateur sur un fichier, un dossier ou un
    skill du catalogue public s'il ne l'a pas encore, la retire sinon
    (toggle, comme sur GitHub) -- jamais de note 1 à 5, seul le nombre
    total d'étoiles compte. N'utilise cet outil QUE si l'utilisateur le
    demande explicitement ("mets une étoile sur...", "retire mon étoile
    de..."), jamais de ta propre initiative.

    `type_element` doit être l'une de : "fichier" (voir
    gerer_document_bibliotheque), "dossier" (voir
    gerer_dossier_catalogue_public), "skill" (voir
    consulter_comportement / les comportements publics) ou "programme"
    (voir gerer_programme_catalogue_public, 22/09/2026). `element_id`
    est l'id de cet élément.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    if not (element_id or "").strip():
        return "Erreur : element_id manquant."
    try:
        resultat = _basculer_etoile(type_element, element_id.strip(), user_id)
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            return "Erreur : type_element invalide, doit être 'fichier', 'dossier', 'skill' ou 'programme'."
        if str(e) == "ELEMENT_INTROUVABLE":
            return "Cet élément du catalogue public est introuvable."
        raise
    except Exception as e:
        logging.error(f"ERREUR outil basculer_etoile_catalogue_public ({type_element} {element_id}) : {e}")
        return "Erreur : impossible de basculer l'étoile, réessaie."

    if resultat["etoile"]:
        return f"Étoile posée. Total : {resultat['etoiles_count']} étoile(s)."
    return f"Étoile retirée. Total : {resultat['etoiles_count']} étoile(s)."
