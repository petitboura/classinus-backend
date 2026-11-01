"""
Autorisations permanentes des actions sensibles (bouton "Toujours autoriser",
demande de Bourama, 31/10/2026).

Quand la personne clique sur "Toujours autoriser" au lieu de "Confirmer", la
clé de l'action (le nom de l'outil, ou "outil:action" pour les outils à
plusieurs actions) est gardée en base pour CETTE personne. Les fois suivantes,
cette action précise ne redemande plus rien. Rien d'autre n'est autorisé :
une autre action du même service redemande toujours confirmation.

Table : autorisations_outils_permanentes (user_id, cle, nom_lisible, created_at).
La personne les retire depuis Applications connectées (api/autorisations_outils.py).
"""

import logging

from core.outils_generation_commun import _supabase_memoire
from registre_outils import OUTILS_SENSIBLES, est_outil_sensible_serveur_personnel

TABLE = "autorisations_outils_permanentes"
LONGUEUR_MAX_CLE = 200
LONGUEUR_MAX_NOM = 300


# Application de l'écran Applications connectées (noms de lib/outils.ts côté frontend)
# à laquelle appartient une action, d'après le début de son nom.
_APPLI_PAR_PREFIXE = (
    ("gerer_depot_github", "github"),
    ("notion-", "notion"),
    ("higgsfield_", "higgsfield_mcp"),
    ("vercel_", "vercel_mcp"),
    ("railway_", "railway_mcp"),
    ("supabase_", "supabase_mcp"),
    ("render_", "render_mcp"),
    ("cloudflare_", "cloudflare_mcp"),
    ("netlify_", "netlify_mcp"),
    ("gmail_", "google_gmail_mcp"),
    ("gdocs_", "google_docs_mcp"),
    ("gsheets_", "google_sheets_mcp"),
    ("gslides_", "google_slides_mcp"),
    ("gcal_", "google_calendar_mcp"),
    ("gchat_", "google_chat_mcp"),
    ("gclass_", "google_classroom_mcp"),
    ("gpeople_", "google_people_mcp"),
    ("ms365_", "microsoft_mcp"),
    ("custommcp_", "mcp_personnalise"),
)


def appli_de_cle(cle):
    """Nom de l'application concernée, ou None si elle n'est dans aucune."""
    for prefixe, appli in _APPLI_PAR_PREFIXE:
        if cle.startswith(prefixe):
            return appli
    return None


def cle_valide(cle):
    """True seulement pour une action qui demande normalement une confirmation."""
    if not isinstance(cle, str) or not cle or len(cle) > LONGUEUR_MAX_CLE:
        return False
    return cle in OUTILS_SENSIBLES or est_outil_sensible_serveur_personnel(cle)


def charger_autorisations(user_id):
    """Ensemble des clés autorisées pour cette personne. Vide en cas de panne (donc on redemande)."""
    if not user_id:
        return frozenset()
    try:
        lignes = (
            _supabase_memoire.table(TABLE).select("cle").eq("user_id", user_id).execute()
        ).data or []
        return frozenset(ligne["cle"] for ligne in lignes)
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture {TABLE} user={user_id}) : {e}")
        return frozenset()


def lister_autorisations(user_id):
    """Lignes complètes pour l'écran Applications connectées. Lève l'erreur de la base."""
    lignes = (
        _supabase_memoire.table(TABLE)
        .select("cle, nom_lisible, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    return [{**ligne, "appli": appli_de_cle(ligne["cle"])} for ligne in lignes]


def enregistrer_autorisation(user_id, cle, nom_lisible):
    """Garde l'autorisation. False si la clé n'est pas une action sensible ou si la base échoue."""
    if not user_id or not cle_valide(cle):
        return False
    try:
        _supabase_memoire.table(TABLE).upsert(
            {"user_id": user_id, "cle": cle, "nom_lisible": (nom_lisible or cle)[:LONGUEUR_MAX_NOM]},
            on_conflict="user_id,cle",
        ).execute()
        return True
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (écriture {TABLE} user={user_id} cle={cle}) : {e}")
        return False


def retirer_autorisation(user_id, cle):
    """Retire l'autorisation. Lève l'erreur de la base."""
    _supabase_memoire.table(TABLE).delete().eq("user_id", user_id).eq("cle", cle).execute()
