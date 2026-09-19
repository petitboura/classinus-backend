"""
Compteurs bruts d'usage sur le catalogue public (18/09/2026, chantier
"profil contributeur bibliotheque publique") : partages, clics CTA
(BoutonAvecIA) et enregistrements. Même mapping type_element que
core/etoiles_catalogue_public.py.

Contrairement aux étoiles (une par personne, toggle), ce sont de purs
compteurs cumulatifs jamais décrémentés par un clic répété -- décision
Bourama du 18/09/2026 ("ces boutons ne servent qu'à partager rien
d'autre, donc il doit les compter rien d'autre") : chaque clic compte,
pas de déduplication par utilisateur.

"enregistrements_count" est légèrement différent : incrémenté à la
copie d'un fichier public vers une bibliothèque perso
(api/bibliotheque_utilisateur.py::copier_depuis_bibliotheque_publique)
et à l'attache d'un dossier public
(core/dossiers_publics_attaches.py::attacher_dossier/detacher_dossier,
là décrémenté au détachement puisque l'attache, elle, est réversible).
Pas de colonne pour "skill" : comportements_publics a déjà
activations_count (comportement_public_activations), qui couvre le même
rôle.
"""

import logging

from api.auth import supabase

TABLES_PAR_TYPE = {
    "fichier": "bibliotheque_publique",
    "dossier": "dossiers_catalogue_public",
    "skill": "comportements_publics",
}


def _incrementer(table: str, colonne: str, element_id: str) -> int:
    """Incrémente colonne de 1 sur la ligne element_id, renvoie le
    nouveau total. Lève ValueError("ELEMENT_INTROUVABLE")."""
    element = supabase.table(table).select(colonne).eq("id", element_id).maybe_single().execute()
    if not element or not element.data:
        raise ValueError("ELEMENT_INTROUVABLE")
    nouveau = (element.data.get(colonne) or 0) + 1
    supabase.table(table).update({colonne: nouveau}).eq("id", element_id).execute()
    return nouveau


def incrementer_cta(type_element: str, element_id: str) -> int:
    """Lève ValueError("TYPE_ELEMENT_INCONNU") ou ValueError("ELEMENT_INTROUVABLE")."""
    table = TABLES_PAR_TYPE.get(type_element)
    if not table:
        raise ValueError("TYPE_ELEMENT_INCONNU")
    return _incrementer(table, "cta_count", element_id)


def incrementer_partage(type_element: str, element_id: str) -> int:
    """Lève ValueError("TYPE_ELEMENT_INCONNU") ou ValueError("ELEMENT_INTROUVABLE")."""
    table = TABLES_PAR_TYPE.get(type_element)
    if not table:
        raise ValueError("TYPE_ELEMENT_INCONNU")
    return _incrementer(table, "partages_count", element_id)


def incrementer_enregistrement_fichier(fichier_id: str) -> None:
    """Best effort (jamais bloquant, voir appelant) : incrémente
    bibliotheque_publique.enregistrements_count à chaque copie vers une
    bibliothèque perso."""
    try:
        _incrementer("bibliotheque_publique", "enregistrements_count", fichier_id)
    except Exception as e:
        logging.error(f"ERREUR compteur enregistrements (fichier public {fichier_id}) : {e}")
