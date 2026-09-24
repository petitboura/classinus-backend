"""
Analytique agrégée du catalogue public (18/09/2026, étape 7) : partages,
étoiles, enregistrements et CTA, en un seul appel PAR LOT (voir note
performance de l'étape 7 -- pensé pour être appelé une fois par page de
bibliotheque_publique affichée, pas une requête par carte, même
philosophie que lib/contexteDossiersCataloguePublic.tsx côté frontend).

"étoiles" ici est un TOTAL (une étoile par personne, voir
core/etoiles_catalogue_public.py) -- pas de moyenne, ce système n'est
pas une note chiffrée.

"enregistrements" :
  - fichier : bibliotheque_publique.enregistrements_count (dénormalisé,
    voir migration 2026_09_18b).
  - dossier : dossiers_catalogue_public.enregistrements_count (idem).
  - skill : comportements_publics.activations_count (mécanisme déjà
    existant, comportement_public_activations, même rôle).
"""

import logging
from collections import defaultdict

from api.auth import supabase

TABLES_PAR_TYPE = {
    "fichier": "bibliotheque_publique",
    "dossier": "dossiers_catalogue_public",
    "skill": "comportements_publics",
    "programme": "programmes_catalogue_public",  # 22/09/2026
}

COLONNES_PAR_TYPE = {
    "fichier": ["id", "partages_count", "etoiles_count", "cta_count", "enregistrements_count"],
    "dossier": ["id", "partages_count", "etoiles_count", "cta_count", "enregistrements_count"],
    "skill": ["id", "partages_count", "etoiles_count", "cta_count", "activations_count"],
    # Programme n'a que les étoiles pour l'instant (pas de compteurs
    # partages/cta/enregistrements, décision de scope 22/09/2026) --
    # les autres colonnes ci-dessous retombent simplement à 0.
    "programme": ["id", "etoiles_count"],
}


def analytique_en_lot(elements: list[dict]) -> dict:
    """
    elements : liste de {"type_element": str, "id": str}.
    Renvoie {f"{type_element}:{id}": {"partages_count", "etoiles_count",
    "cta_count", "enregistrements_count"}} -- une entrée absente du
    dictionnaire de retour = élément introuvable (ignoré, jamais
    d'erreur bloquante sur tout le lot pour une entrée invalide).
    """
    ids_par_type: dict[str, list[str]] = defaultdict(list)
    for e in elements:
        type_element = e.get("type_element")
        element_id = e.get("id")
        if type_element in TABLES_PAR_TYPE and element_id:
            ids_par_type[type_element].append(element_id)

    resultat: dict[str, dict] = {}
    for type_element, ids in ids_par_type.items():
        table = TABLES_PAR_TYPE[type_element]
        colonnes = COLONNES_PAR_TYPE[type_element]
        try:
            res = supabase.table(table).select(",".join(colonnes)).in_("id", list(set(ids))).execute()
        except Exception as e:
            logging.error(f"ERREUR SUPABASE (analytique en lot {type_element}) : {e}")
            continue
        for ligne in res.data or []:
            enregistrements = ligne.get("enregistrements_count", ligne.get("activations_count", 0)) or 0
            resultat[f"{type_element}:{ligne['id']}"] = {
                "partages_count": ligne.get("partages_count") or 0,
                "etoiles_count": ligne.get("etoiles_count") or 0,
                "cta_count": ligne.get("cta_count") or 0,
                "enregistrements_count": enregistrements,
            }
    return resultat
