"""
Outil MCP pour commenter un élément du catalogue public, au nom de
l'utilisateur -- 22/09/2026, ajouté à l'occasion du catalogue public du
Programme (demande Bourama : "on doit pouvoir lire, noter, commenter").
N'existait pour aucun type d'élément avant ça (les commentaires
n'étaient utilisables que depuis l'écran de l'appli, jamais en
conversation) : cet outil est générique, il profite donc aussi aux
fichiers/dossiers/skills déjà commentables côté écran.

Toute la logique vit dans core/commentaires_catalogue_public.py (déjà
utilisée par api/commentaires_catalogue_public.py côté écran).
"""

import logging

from core.outils_generation_commun import mcp_generation, Context
from core.commentaires_catalogue_public import (
    creer_commentaire as _creer_commentaire,
    supprimer_commentaire as _supprimer_commentaire,
)


@mcp_generation.tool()
def ajouter_commentaire_catalogue_public(type_element: str, element_id: str, contenu: str, ctx: Context) -> str:
    """
    Ajoute un commentaire de l'utilisateur sur un élément du catalogue
    public. N'utilise cet outil QUE si l'utilisateur le demande
    explicitement ("commente ceci...", "laisse un commentaire disant
    que..."), jamais de ta propre initiative. Nécessite que
    l'utilisateur ait un profil public (sinon erreur explicite, à
    relayer tel quel).

    `type_element` doit être l'une de : "fichier", "dossier", "skill",
    "programme". `element_id` est l'id de cet élément. `contenu` est le
    texte du commentaire.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    if not (element_id or "").strip():
        return "Erreur : element_id manquant."
    try:
        _creer_commentaire(type_element, element_id.strip(), user_id, contenu)
    except ValueError as e:
        if str(e) == "TYPE_ELEMENT_INCONNU":
            return "Erreur : type_element invalide, doit être 'fichier', 'dossier', 'skill' ou 'programme'."
        if str(e) == "ELEMENT_INTROUVABLE":
            return "Cet élément du catalogue public est introuvable."
        if str(e) == "COMMENTAIRE_VIDE":
            return "Erreur : le commentaire ne peut pas être vide."
        if str(e) == "PROFIL_PUBLIC_REQUIS_POUR_COMMENTER":
            return "Erreur : il faut un profil public pour commenter (à activer dans les paramètres du profil)."
        raise
    except Exception as e:
        logging.error(f"ERREUR outil ajouter_commentaire_catalogue_public ({type_element} {element_id}) : {e}")
        return "Erreur : impossible d'ajouter ce commentaire, réessaie."
    return "Commentaire ajouté."


@mcp_generation.tool()
def supprimer_commentaire_catalogue_public(commentaire_id: str, ctx: Context) -> str:
    """Supprime un commentaire déjà posté par CET utilisateur (le sien
    uniquement). Paramètre : `commentaire_id`."""
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    if not (commentaire_id or "").strip():
        return "Erreur : commentaire_id manquant."
    try:
        _supprimer_commentaire(commentaire_id.strip(), user_id)
    except ValueError as e:
        if str(e) == "COMMENTAIRE_INTROUVABLE":
            return "Ce commentaire est introuvable."
        if str(e) == "COMMENTAIRE_NE_T_APPARTIENT_PAS":
            return "Erreur : tu ne peux supprimer que tes propres commentaires."
        raise
    except Exception as e:
        logging.error(f"ERREUR outil supprimer_commentaire_catalogue_public ({commentaire_id}) : {e}")
        return "Erreur : impossible de supprimer ce commentaire, réessaie."
    return "Commentaire supprimé."
