"""
Permissions des outils par personne (24/11/2026, demande de Bourama : "une page dédiée avec
autoriser, bloquer, toujours autoriser comme chez Claude, pour toutes les catégories d'outils").

Trois états pour chaque outil d'une application connectée ou d'un serveur MCP personnalisé :
- autoriser : l'outil s'exécute sans confirmation ;
- demander : confirmation à chaque fois ;
- bloquer : l'outil est refusé, et l'IA explique à la personne qu'elle l'a bloqué.

Deux catégories par application : "lecture" (outils qui ne modifient rien) et "ecriture" (outils qui
créent, modifient ou suppriment). La personne règle la catégorie entière, puis peut faire une
exception outil par outil.

Priorité à l'exécution : réglage de l'outil, puis réglage de sa catégorie, puis valeur par défaut.
Valeurs par défaut (identiques au comportement d'avant cette fonction) :
- application connectée : lecture = autoriser, écriture = demander ;
- serveur MCP personnalisé : tout = demander (un outil externe n'a pas de convention de lecture fiable).

Table : permissions_outils (user_id, cle, etat, nom_lisible, created_at, updated_at), voir
migrations/2026_11_24_permissions_outils.sql. Une ligne par réglage explicite ; pas de ligne = défaut.

Ce module ne dépend d'aucun serveur ni d'aucun client réseau au chargement : la base est atteinte
seulement dans les fonctions qui la lisent ou l'écrivent, ce qui permet de tester toute la logique
hors ligne (test_permissions_outils.py).
"""

import logging
import re
from datetime import datetime, timezone

TABLE = "permissions_outils"
LONGUEUR_MAX_CLE = 200
LONGUEUR_MAX_NOM = 300

AUTORISER = "autoriser"
DEMANDER = "demander"
BLOQUER = "bloquer"
ETATS = frozenset({AUTORISER, DEMANDER, BLOQUER})

LECTURE = "lecture"
ECRITURE = "ecriture"
TYPES_OUTILS = (LECTURE, ECRITURE)

_PREFIXE_CATEGORIE = "categorie:"
_PREFIXE_SERVEUR_PERSO = "custommcp_"
# Nom exposé d'un outil de serveur personnalisé : custommcp_<verbe>_<6 caractères du serveur>_<nom>.
_MOTIF_SERVEUR_PERSO = re.compile(r"^custommcp_[a-z]{0,8}_([0-9a-f]{6})_")
_MOTIF_GROUPE_SERVEUR_PERSO = re.compile(r"^custommcp_[0-9a-f]{6}$")


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

GROUPES_APPLICATIONS = frozenset(appli for _prefixe, appli in _APPLI_PAR_PREFIXE if appli != "mcp_personnalise")


def appli_de_cle(cle):
    """Nom de l'application concernée, ou None si elle n'est dans aucune."""
    for prefixe, appli in _APPLI_PAR_PREFIXE:
        if cle.startswith(prefixe):
            return appli
    return None


def groupe_de_outil(nom_outil):
    """Groupe de réglages d'un outil : le nom de son application, ou "custommcp_<6 caractères>" pour un
    serveur personnalisé. None pour un outil qui n'appartient à aucune application (outil interne)."""
    if not isinstance(nom_outil, str) or not nom_outil:
        return None
    base = nom_outil.split(":", 1)[0]
    if base.startswith(_PREFIXE_SERVEUR_PERSO):
        trouve = _MOTIF_SERVEUR_PERSO.match(base)
        return f"{_PREFIXE_SERVEUR_PERSO}{trouve.group(1)}" if trouve else None
    appli = appli_de_cle(base)
    return None if appli == "mcp_personnalise" else appli


def groupe_valide(groupe):
    """True pour une application connue ou un groupe de serveur personnalisé bien formé."""
    return isinstance(groupe, str) and (groupe in GROUPES_APPLICATIONS or bool(_MOTIF_GROUPE_SERVEUR_PERSO.match(groupe)))


def groupe_serveur_perso(serveur_id):
    """Groupe d'un serveur personnalisé, d'après son identifiant (les 6 premiers caractères sans tirets)."""
    return f"{_PREFIXE_SERVEUR_PERSO}{str(serveur_id).replace('-', '')[:6].lower()}"


def cle_categorie(groupe, type_outil):
    return f"{_PREFIXE_CATEGORIE}{groupe}:{type_outil}"


def est_cle_categorie(cle):
    return isinstance(cle, str) and cle.startswith(_PREFIXE_CATEGORIE)


def defaut_pour(groupe, type_outil):
    """Réglage appliqué quand la personne n'a rien choisi."""
    if isinstance(groupe, str) and groupe.startswith(_PREFIXE_SERVEUR_PERSO):
        return DEMANDER
    return AUTORISER if type_outil == LECTURE else DEMANDER


def _cles_interdites():
    """Actions qui ne peuvent jamais être autorisées d'avance (registre_outils.py).

    Pas de try/except volontairement : si la liste ne se charge pas, l'erreur doit se voir (l'appelant du
    chat retombe alors sur l'ancien comportement prudent) au lieu d'autoriser par défaut en silence."""
    from registre_outils import AUTORISATION_PERMANENTE_INTERDITE
    return AUTORISATION_PERMANENTE_INTERDITE


class Permissions:
    """Réglages d'une personne, chargés une fois par tour de chat.

    `cle in permissions` reste vrai pour une action explicitement autorisée, comme l'ancien ensemble
    d'autorisations, pour que le code qui n'a pas besoin de la nouveauté continue de fonctionner."""

    def __init__(self, etats=None):
        self._etats = {cle: etat for cle, etat in (etats or {}).items() if etat in ETATS}

    def __bool__(self):
        return bool(self._etats)

    def __contains__(self, cle):
        return self._etats.get(cle) == AUTORISER and cle not in _cles_interdites()

    def etat_explicite(self, cle):
        """Réglage choisi par la personne pour cette clé, ou None."""
        return self._etats.get(cle)

    def a_des_blocages(self):
        return any(etat == BLOQUER for etat in self._etats.values())

    def etat(self, cle_outil, groupe, type_outil, defaut=None):
        """Réglage appliqué : outil, puis catégorie, puis défaut. Une action qui doit toujours être
        confirmée (AUTORISATION_PERMANENTE_INTERDITE) ne devient jamais "autoriser"."""
        resultat = self._etats.get(cle_outil)
        if resultat is None and groupe:
            resultat = self._etats.get(cle_categorie(groupe, type_outil))
        if resultat is None:
            resultat = defaut if defaut in ETATS else defaut_pour(groupe, type_outil)
        if resultat == AUTORISER and cle_outil in _cles_interdites():
            return DEMANDER
        return resultat


def construire_vue(groupe, outils, permissions):
    """Ce que la page affiche pour une application : deux catégories, chacune avec son réglage et ses outils.

    `outils` : liste de {"cle", "nom_lisible", "type"} où type vaut "lecture" ou "ecriture"."""
    categories = []
    for type_outil in TYPES_OUTILS:
        defaut = defaut_pour(groupe, type_outil)
        explicite = permissions.etat_explicite(cle_categorie(groupe, type_outil))
        liste = []
        for outil in sorted((o for o in outils if o["type"] == type_outil), key=lambda o: o["nom_lisible"].lower()):
            liste.append({
                "cle": outil["cle"],
                "nom_lisible": outil["nom_lisible"],
                "etat": permissions.etat_explicite(outil["cle"]),
                "etat_effectif": permissions.etat(outil["cle"], groupe, type_outil, defaut),
                # Une action qui doit toujours être confirmée ne propose pas "autoriser".
                "autorisation_possible": outil["cle"] not in _cles_interdites(),
            })
        categories.append({
            "type": type_outil,
            "etat": explicite,
            "etat_effectif": explicite or defaut,
            "par_defaut": defaut,
            "outils": liste,
        })
    return {"groupe": groupe, "categories": categories}


def valider_reglage(groupe, cle, etat):
    """Message d'erreur technique (jamais montré tel quel) si le réglage demandé est refusé, sinon None."""
    if etat not in ETATS:
        return "etat_invalide"
    if not groupe_valide(groupe):
        return "groupe_invalide"
    if not isinstance(cle, str) or not cle or len(cle) > LONGUEUR_MAX_CLE:
        return "cle_invalide"
    if est_cle_categorie(cle):
        morceaux = cle.split(":")
        if len(morceaux) != 3 or morceaux[1] != groupe or morceaux[2] not in TYPES_OUTILS:
            return "categorie_invalide"
        return None
    if groupe_de_outil(cle) != groupe:
        return "outil_hors_application"
    if etat == AUTORISER and cle in _cles_interdites():
        return "autorisation_interdite"
    return None


# ---------------------------------------------------------------------------
# Accès à la base (chargé seulement à l'appel, voir la note en tête de fichier)
# ---------------------------------------------------------------------------

def _client():
    from core.outils_generation_commun import _supabase_memoire
    return _supabase_memoire


def charger_permissions(user_id):
    """Réglages de la personne. Vide en cas de panne : les valeurs par défaut s'appliquent donc
    (lecture sans confirmation, écriture avec confirmation), comme avant."""
    if not user_id:
        return Permissions()
    try:
        lignes = _client().table(TABLE).select("cle, etat").eq("user_id", user_id).execute().data or []
        return Permissions({ligne["cle"]: ligne["etat"] for ligne in lignes})
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture {TABLE} user={user_id}) : {e}")
        return Permissions()


def lire_lignes(user_id):
    """Lignes complètes d'une personne. Lève l'erreur de la base."""
    return (
        _client().table(TABLE).select("cle, etat, nom_lisible, created_at").eq("user_id", user_id)
        .order("created_at", desc=True).execute()
    ).data or []


def ecrire_etat(user_id, cle, etat, nom_lisible=""):
    """Enregistre un réglage. Lève l'erreur de la base."""
    _client().table(TABLE).upsert(
        {
            "user_id": user_id,
            "cle": cle,
            "etat": etat,
            "nom_lisible": (nom_lisible or "")[:LONGUEUR_MAX_NOM],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,cle",
    ).execute()


def retirer_reglage(user_id, cle):
    """Supprime un réglage : la valeur par défaut s'applique de nouveau. Lève l'erreur de la base."""
    _client().table(TABLE).delete().eq("user_id", user_id).eq("cle", cle).execute()
