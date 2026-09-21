"""
Étoiles sur le catalogue public (17/09/2026, demande Bourama : "comme
sur GitHub, une étoile par personne, seul le nombre compte"). S'applique
aux 4 types d'éléments du catalogue public :
  - "fichier" -> bibliotheque_publique
  - "dossier" -> dossiers_catalogue_public
  - "skill"   -> comportements_publics
  - "clovis"  -> clovis_infos (18/09/2026, étape 13 : Classinus lui-même,
    table singleton à une seule ligne -- il n'y a plus de système
    "agent" dans Classinus, ce n'est PAS agent_comments/agent_ratings)

Toggle simple (basculer_etoile) : pose l'étoile de cet utilisateur si
elle n'existe pas encore, la retire sinon -- jamais de note 1 à 5,
jamais plus d'une étoile par personne et par élément (contrainte unique
en base, voir migration etoiles_catalogue_public). Le total est gardé
en dénormalisé sur chaque table cible (colonne etoiles_count, même
principe que comportements_publics.activations_count) pour ne jamais
avoir à recompter à l'affichage.
"""

import logging

from api.auth import supabase

TABLES_PAR_TYPE = {
    "fichier": "bibliotheque_publique",
    "dossier": "dossiers_catalogue_public",
    "skill": "comportements_publics",
    "clovis": "classinus_infos",
}


def _a_etoile(type_element: str, element_id: str, utilisateur_id: str) -> bool:
    res = (
        supabase.table("etoiles_catalogue_public")
        .select("id")
        .eq("type_element", type_element)
        .eq("element_id", element_id)
        .eq("utilisateur_id", utilisateur_id)
        .maybe_single()
        .execute()
    )
    return bool(res and res.data)


def basculer_etoile(type_element: str, element_id: str, utilisateur_id: str) -> dict:
    """
    Retourne {"etoile": bool, "etoiles_count": int} -- `etoile` indique
    le nouvel état (True = posée) après le basculement. Lève
    ValueError("TYPE_ELEMENT_INCONNU") ou ValueError("ELEMENT_INTROUVABLE").
    """
    table = TABLES_PAR_TYPE.get(type_element)
    if not table:
        raise ValueError("TYPE_ELEMENT_INCONNU")

    element = (
        supabase.table(table)
        .select("etoiles_count")
        .eq("id", element_id)
        .maybe_single()
        .execute()
    )
    if not element or not element.data:
        raise ValueError("ELEMENT_INTROUVABLE")

    compte_actuel = element.data.get("etoiles_count") or 0
    deja_posee = _a_etoile(type_element, element_id, utilisateur_id)

    if deja_posee:
        supabase.table("etoiles_catalogue_public").delete().eq("type_element", type_element).eq(
            "element_id", element_id
        ).eq("utilisateur_id", utilisateur_id).execute()
        nouveau_compte = max(0, compte_actuel - 1)
        nouvel_etat = False
    else:
        try:
            supabase.table("etoiles_catalogue_public").insert({
                "type_element": type_element,
                "element_id": element_id,
                "utilisateur_id": utilisateur_id,
            }).execute()
        except Exception as e:
            # Contrainte unique déjà là (double-clic/course entre deux
            # requêtes) : l'étoile est de toute façon posée, ce n'est
            # pas une vraie erreur.
            if getattr(e, "code", None) == "23505":
                return {"etoile": True, "etoiles_count": compte_actuel}
            logging.error(f"ERREUR SUPABASE (pose etoile {type_element} {element_id}) : {e}")
            raise
        nouveau_compte = compte_actuel + 1
        nouvel_etat = True

    try:
        supabase.table(table).update({"etoiles_count": nouveau_compte}).eq("id", element_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (compteur etoiles {type_element} {element_id}) : {e}")

    return {"etoile": nouvel_etat, "etoiles_count": nouveau_compte}


def etoiles_utilisateur(type_element: str, element_ids: list, utilisateur_id: str | None) -> set:
    """
    Renvoie l'ensemble des element_id (parmi element_ids) déjà étoilés
    par cet utilisateur -- un seul aller-retour pour tout un affichage
    en liste, plutôt qu'une requête par élément. Ensemble vide si pas
    connecté ou liste vide.
    """
    if not utilisateur_id or not element_ids:
        return set()
    res = (
        supabase.table("etoiles_catalogue_public")
        .select("element_id")
        .eq("type_element", type_element)
        .eq("utilisateur_id", utilisateur_id)
        .in_("element_id", list(element_ids))
        .execute()
    )
    return {r["element_id"] for r in (res.data or [])}
