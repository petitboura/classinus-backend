"""
Commentaires sur le catalogue public (18/09/2026, chantier "profil
contributeur bibliotheque publique"). S'applique aux 4 types d'éléments
du catalogue public, même mapping que core/etoiles_catalogue_public.py :
  - "fichier" -> bibliotheque_publique
  - "dossier" -> dossiers_catalogue_public
  - "skill"   -> comportements_publics
  - "clovis"  -> clovis_infos (étape 13 : Classinus lui-même, table
    singleton à une seule ligne)

Système totalement séparé du système d'étoiles (qui n'est pas une note
chiffrée mais un simple compteur "une étoile par personne", voir
core/etoiles_catalogue_public.py). 18/09/2026 : le type "clovis" ci-
dessus est la réutilisation prévue à l'étape 13, mais sur les tables
génériques de CE chantier -- pas de lien avec agent_comments/
agent_ratings (ancien système historique, voir
core/serveur_mcp_espace.py) : il n'y a plus de système "agent" dans
Classinus, ce nommage est volontairement banni de ce chantier.

Poster un commentaire exige profil_public = true (décision Bourama,
étape 5) : un commentaire affiche toujours l'auteur, donc son profil
doit être consultable, sinon la personne qui lit le commentaire tombe
sur un profil "non public" pour rien.
"""

import logging

from api.auth import supabase

TABLES_PAR_TYPE = {
    "fichier": "bibliotheque_publique",
    "dossier": "dossiers_catalogue_public",
    "skill": "comportements_publics",
    "clovis": "clovis_infos",
}

TAILLE_PAGE_MAX = 50


def _profils_de(utilisateur_ids: list) -> dict:
    """Renvoie {user_id: {"nom_affiche":..., "avatar_url":...}} -- un
    seul aller-retour pour toute une page de commentaires, même
    principe que core/etoiles_catalogue_public.py::etoiles_utilisateur.
    Pas de jointure PostgREST directe (commentaires_catalogue_public et
    profiles référencent tous deux auth.users(id) séparément, pas l'un
    l'autre)."""
    if not utilisateur_ids:
        return {}
    try:
        res = (
            supabase.table("profiles")
            .select("user_id, nom_affiche, avatar_url")
            .in_("user_id", list(set(utilisateur_ids)))
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture profils auteurs commentaires) : {e}")
        return {}
    return {p["user_id"]: {"nom_affiche": p.get("nom_affiche") or "", "avatar_url": p.get("avatar_url")} for p in (res.data or [])}


def lister_commentaires(type_element: str, element_id: str, decalage: int, limite: int) -> dict:
    """
    Renvoie {"commentaires": [...], "total": int}, du plus récent au
    plus ancien (pagination decalage/limite, même convention que
    api/bibliotheque_publique.py, pour le scroll infini côté frontend).
    Lève ValueError("TYPE_ELEMENT_INCONNU").
    """
    if type_element not in TABLES_PAR_TYPE:
        raise ValueError("TYPE_ELEMENT_INCONNU")

    limite = max(1, min(limite, TAILLE_PAGE_MAX))

    try:
        res = (
            supabase.table("commentaires_catalogue_public")
            .select("id, contenu, created_at, utilisateur_id", count="exact")
            .eq("type_element", type_element)
            .eq("element_id", element_id)
            .order("created_at", desc=True)
            .range(decalage, decalage + limite - 1)
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (liste commentaires {type_element} {element_id}) : {e}")
        raise

    lignes = res.data or []
    profils = _profils_de([l["utilisateur_id"] for l in lignes])
    commentaires = [
        {
            "id": l["id"],
            "contenu": l["contenu"],
            "created_at": l["created_at"],
            "utilisateur_id": l["utilisateur_id"],
            "auteur_nom": profils.get(l["utilisateur_id"], {}).get("nom_affiche") or "",
            "auteur_avatar_url": profils.get(l["utilisateur_id"], {}).get("avatar_url"),
        }
        for l in lignes
    ]
    return {"commentaires": commentaires, "total": res.count or 0}


def creer_commentaire(type_element: str, element_id: str, utilisateur_id: str, contenu: str) -> dict:
    """
    Lève ValueError("TYPE_ELEMENT_INCONNU"), ValueError("ELEMENT_INTROUVABLE"),
    ValueError("COMMENTAIRE_VIDE") ou ValueError("PROFIL_PUBLIC_REQUIS_POUR_COMMENTER").
    """
    table = TABLES_PAR_TYPE.get(type_element)
    if not table:
        raise ValueError("TYPE_ELEMENT_INCONNU")

    contenu = (contenu or "").strip()
    if not contenu:
        raise ValueError("COMMENTAIRE_VIDE")

    element = supabase.table(table).select("id").eq("id", element_id).maybe_single().execute()
    if not element or not element.data:
        raise ValueError("ELEMENT_INTROUVABLE")

    profil = (
        supabase.table("profiles").select("profil_public").eq("user_id", utilisateur_id).maybe_single().execute()
    )
    if not profil or not profil.data or not profil.data.get("profil_public"):
        raise ValueError("PROFIL_PUBLIC_REQUIS_POUR_COMMENTER")

    try:
        res = (
            supabase.table("commentaires_catalogue_public")
            .insert({
                "type_element": type_element,
                "element_id": element_id,
                "utilisateur_id": utilisateur_id,
                "contenu": contenu,
            })
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (création commentaire {type_element} {element_id}) : {e}")
        raise
    return res.data[0]


def supprimer_commentaire(commentaire_id: str, utilisateur_id: str) -> None:
    """Lève ValueError("COMMENTAIRE_INTROUVABLE") ou
    ValueError("COMMENTAIRE_NE_T_APPARTIENT_PAS")."""
    res = (
        supabase.table("commentaires_catalogue_public")
        .select("id, utilisateur_id")
        .eq("id", commentaire_id)
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise ValueError("COMMENTAIRE_INTROUVABLE")
    if res.data["utilisateur_id"] != utilisateur_id:
        raise ValueError("COMMENTAIRE_NE_T_APPARTIENT_PAS")

    supabase.table("commentaires_catalogue_public").delete().eq("id", commentaire_id).execute()
