"""
Catalogue public du Programme (22/09/2026, demande Bourama : "il faut un
moyen de partager et de trouver des programmes publics" -- même genre
de catalogue public que ce qui existe déjà pour la bibliothèque
(core/catalogue_public_publication.py) et les skills, transposé au
Programme (arborescence de notions par code de partage, voir
core/programme_notions.py).

Publier = COPIE FIGÉE (snapshot) du Programme au moment de la
publication, jamais un lien vivant vers le code source (décision
Bourama 22/09/2026 : "pas de lien"). Copier vers son propre espace crée
à son tour une copie indépendante dans la table `notions` vivante :
aucun lien gardé, ni avec l'original, ni avec l'entrée publique.

`inclut_regles_consignes` est un choix à DEUX endroits séparés,
décision Bourama : le publieur choisit d'inclure ou non
regle_comportement/consigne_llm dans la copie figée (si non, rien
n'est stocké, même si l'original en avait) ; le télécharge-ur choisit
séparément, au moment de copier_vers_perso, s'il veut ces
règles/consignes dans SA copie (impossible bien sûr si le publieur ne
les a pas incluses).

Le `statut` d'avancement (à_venir/en_cours/acquis) n'est PAS repris
dans le catalogue public ni dans la copie perso : c'est une info
d'avancement propre à UNE classe/UN code, sans sens une fois partagée.
Une notion copiée démarre toujours au statut par défaut de la table
`notions` (à_venir). Point non discuté explicitement avec Bourama,
à confirmer si besoin.

Toute la logique métier vit ici (réutilisée par l'outil MCP côté chat
ET par le futur outil équivalent côté serveur MCP public, même
convention que core/catalogue_public_publication.py).
"""

import logging
import uuid
from datetime import datetime

from supabase import create_client, ClientOptions
from client_http_supabase import nouveau_client_http_supabase
from core.programme_notions import code_appartient_a
from core.codes_partage import creer_code as _creer_code

import os


def _get_secret(key):
    return os.environ.get(key)


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_SECRET = _get_secret("SUPABASE_SECRET")
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET, options=ClientOptions(httpx_client=nouveau_client_http_supabase()))

TAILLE_PAGE_MAX = 15


def _vers_liste(valeur) -> list[str]:
    """Accepte une chaîne unique OU une liste (le serveur chat envoie
    une chaîne par filtre, le serveur MCP public une liste -- même
    tolérance que catalogue_public_publication.py::_vers_liste)."""
    if valeur is None:
        return []
    if isinstance(valeur, list):
        return [v.strip() for v in valeur if (v or "").strip()]
    valeur = (valeur or "").strip()
    return [valeur] if valeur else []


def _filtres_normalises(pays, niveau, categorie, classe, specialite) -> dict:
    """Même contrat que core/catalogue_public_publication.py::_filtres_normalises
    (pas de normalisation en table à part -- le Programme n'a pas
    encore besoin de normaliser/dédupliquer les valeurs comme la
    bibliothèque)."""
    return {
        "pays": _vers_liste(pays),
        "niveau": _vers_liste(niveau),
        "categorie": _vers_liste(categorie),
        "classe": _vers_liste(classe),
        "specialite": _vers_liste(specialite),
    }


def publier_programme_public(
    code_id: str, proprietaire_id: str, nom: str, description: str = "",
    inclure_regles_consignes: bool = False,
    pays: str = "", niveau: str = "", categorie: str = "", classe: str = "", specialite: str = "",
) -> dict | str:
    """Publie une copie figée du Programme entier de `code_id` dans le
    catalogue public. Renvoie l'entrée créée (dict), ou un message
    d'erreur (str) : "CODE_INTROUVABLE" (n'appartient pas à
    proprietaire_id), "NOM_REQUIS" ou "PROGRAMME_VIDE" (aucune notion à
    publier)."""
    if not code_appartient_a(code_id, proprietaire_id):
        return "CODE_INTROUVABLE"
    nom = (nom or "").strip()
    if not nom:
        return "NOM_REQUIS"

    notions = supabase.table("notions").select(
        "id, notion_parent_id, nom, ordre, regle_comportement, consigne_llm"
    ).eq("code_id", code_id).execute().data or []
    if not notions:
        return "PROGRAMME_VIDE"

    entree = supabase.table("programmes_catalogue_public").insert({
        "publie_par": proprietaire_id,
        "nom": nom,
        "description": (description or "").strip(),
        "inclut_regles_consignes": bool(inclure_regles_consignes),
        **_filtres_normalises(pays, niveau, categorie, classe, specialite),
    }).execute().data[0]

    # Nouveaux ids générés côté Python (plutôt que de laisser Supabase
    # les générer) pour pouvoir écrire notion_parent_id dès l'insertion
    # en une seule fois, sans étape de remappage après coup.
    nouveaux_ids = {n["id"]: str(uuid.uuid4()) for n in notions}
    lignes = [{
        "id": nouveaux_ids[n["id"]],
        "programme_catalogue_public_id": entree["id"],
        "notion_parent_id": nouveaux_ids.get(n["notion_parent_id"]) if n["notion_parent_id"] else None,
        "nom": n["nom"],
        "ordre": n["ordre"],
        "regle_comportement": n["regle_comportement"] if inclure_regles_consignes else None,
        "consigne_llm": n["consigne_llm"] if inclure_regles_consignes else None,
    } for n in notions]
    supabase.table("notions_catalogue_public").insert(lignes).execute()

    return entree


def modifier_programme_public(
    entree_id: str, utilisateur_id: str, nom: str = None, description: str = None,
    pays: str = None, niveau: str = None, categorie: str = None, classe: str = None, specialite: str = None,
) -> str | None:
    """Même contrat que catalogue_public_publication.modifier_entree_publique :
    None = champ non touché, chaîne vide = filtre effacé. Renvoie None
    si tout va bien, sinon un message d'erreur."""
    res = supabase.table("programmes_catalogue_public").select("publie_par").eq("id", entree_id).maybe_single().execute()
    if not res or not res.data:
        return "ENTREE_INTROUVABLE"
    if res.data["publie_par"] != utilisateur_id:
        return "CETTE_ENTREE_NE_T_APPARTIENT_PAS"

    maj = {}
    if nom is not None:
        nom_nettoye = nom.strip()
        if not nom_nettoye:
            return "NOM_REQUIS"
        maj["nom"] = nom_nettoye
    if description is not None:
        maj["description"] = description.strip()
    if pays is not None:
        maj["pays"] = _filtres_normalises(pays, "", "", "", "")["pays"]
    if niveau is not None:
        maj["niveau"] = _filtres_normalises("", niveau, "", "", "")["niveau"]
    if categorie is not None:
        maj["categorie"] = _filtres_normalises("", "", categorie, "", "")["categorie"]
    if classe is not None:
        maj["classe"] = _filtres_normalises("", "", "", classe, "")["classe"]
    if specialite is not None:
        maj["specialite"] = _filtres_normalises("", "", "", "", specialite)["specialite"]

    if not maj:
        return "AUCUNE_MODIFICATION_FOURNIE"
    maj["updated_at"] = datetime.utcnow().isoformat()
    supabase.table("programmes_catalogue_public").update(maj).eq("id", entree_id).execute()
    return None


def supprimer_programme_public(entree_id: str, utilisateur_id: str) -> bool:
    """Supprime définitivement une entrée (et ses notions figées, ON
    DELETE CASCADE côté base). Réservé au contributeur d'origine."""
    res = supabase.table("programmes_catalogue_public").select("publie_par").eq("id", entree_id).maybe_single().execute()
    if not res or not res.data or res.data["publie_par"] != utilisateur_id:
        return False
    supabase.table("programmes_catalogue_public").delete().eq("id", entree_id).execute()
    return True


def _arbre_notions_publiees(entree_id: str) -> list[dict]:
    return supabase.table("notions_catalogue_public").select(
        "id, notion_parent_id, nom, ordre, regle_comportement, consigne_llm"
    ).eq("programme_catalogue_public_id", entree_id).order("notion_parent_id", desc=False, nullsfirst=True).order("ordre").execute().data or []


def obtenir_programmes_publics_par_ids(ids: list[str]) -> dict[str, dict]:
    """Recharge les lignes complètes (avec `publie_par`) pour une liste
    d'ids -- utilisé par la route REST de recherche/liste qui a besoin
    de `publie_par` (pour calculer `est_a_moi`) alors que
    lister_programmes_catalogue_public/chercher_programmes_catalogue_public
    ne renvoient qu'un sous-ensemble de colonnes (suffisant pour le chat)."""
    if not ids:
        return {}
    lignes = supabase.table("programmes_catalogue_public").select("*").in_("id", ids).execute().data or []
    return {l["id"]: l for l in lignes}


def lire_programme_public(entree_id: str) -> dict | None:
    """Renvoie l'entrée (nom, description, filtres...) avec ses notions
    À PLAT (comme lister_notions côté perso -- à l'appelant de
    reconstruire l'arborescence via notion_parent_id). None si
    introuvable."""
    entree = supabase.table("programmes_catalogue_public").select("*").eq("id", entree_id).maybe_single().execute()
    if not entree or not entree.data:
        return None
    resultat = dict(entree.data)
    resultat["notions"] = _arbre_notions_publiees(entree_id)
    return resultat


def lister_programmes_catalogue_public(
    limite: int = 15, decalage: int = 0,
    pays: str = None, niveau: str = None, categorie: str = None, classe: str = None, specialite: str = None,
) -> dict:
    """Liste les entrées les plus récentes, sans recherche par mot clé
    -- pour une demande vague. Même pagination/plafond que
    core.catalogue_public_rag.lister_catalogue_public."""
    limite = max(1, min(limite, TAILLE_PAGE_MAX))
    res = supabase.rpc("lister_programmes_catalogue_public_filtre", {
        "p_limite": limite, "p_decalage": decalage,
        "p_pays": (pays or "").strip() or None, "p_niveau": (niveau or "").strip() or None,
        "p_categorie": (categorie or "").strip() or None, "p_classe": (classe or "").strip() or None,
        "p_specialite": (specialite or "").strip() or None,
    }).execute()
    lignes = res.data or []
    total = lignes[0]["total"] if lignes else 0
    entrees = [{k: l[k] for k in ("id", "nom", "description", "inclut_regles_consignes", "etoiles_count", "created_at")} for l in lignes]
    return {"programmes": entrees, "total": total}


def chercher_programmes_catalogue_public(
    question: str, match_count: int = 5,
    pays: str = None, niveau: str = None, categorie: str = None, classe: str = None, specialite: str = None,
) -> list[dict]:
    """Recherche par mot clé (nom + description), même filtres que
    lister_programmes_catalogue_public. Pas de recherche vectorielle
    (aucun besoin exprimé au-delà des filtres, à revoir plus tard si
    nécessaire)."""
    match_count = max(1, min(match_count, 20))
    res = supabase.rpc("chercher_programmes_catalogue_public_mots_cles", {
        "p_question": question, "match_count": match_count,
        "p_pays": (pays or "").strip() or None, "p_niveau": (niveau or "").strip() or None,
        "p_categorie": (categorie or "").strip() or None, "p_classe": (classe or "").strip() or None,
        "p_specialite": (specialite or "").strip() or None,
    }).execute()
    return res.data or []


def copier_programme_vers_perso(
    entree_id: str, utilisateur_id: str,
    code_id: str = None, nouveau_code_nom: str = None,
    inclure_regles_consignes: bool = False,
) -> dict | str:
    """Copie une entrée publiée vers un code de l'utilisateur (existant
    via `code_id`, ou nouveau créé à la volée avec `nouveau_code_nom` --
    décision Bourama 22/09/2026 : les deux options). Copie
    indépendante, aucun lien gardé. `inclure_regles_consignes` ne peut
    reprendre que ce que le publieur a lui-même inclus (si l'entrée n'a
    pas `inclut_regles_consignes`, rien à reprendre, ignoré
    silencieusement). Renvoie {"code_id", "code", "nb_notions"} ou un
    message d'erreur."""
    entree = supabase.table("programmes_catalogue_public").select("*").eq("id", entree_id).maybe_single().execute()
    if not entree or not entree.data:
        return "ENTREE_INTROUVABLE"

    if code_id:
        if not code_appartient_a(code_id, utilisateur_id):
            return "CODE_INTROUVABLE"
        code_cible_id = code_id
        code_cible = None
    else:
        nouveau_code = _creer_code(utilisateur_id, nom=(nouveau_code_nom or entree.data["nom"]))
        code_cible_id = nouveau_code["id"]
        code_cible = nouveau_code

    notions = _arbre_notions_publiees(entree_id)
    if not notions:
        return "PROGRAMME_VIDE"

    reprendre_regles = inclure_regles_consignes and entree.data.get("inclut_regles_consignes")
    nouveaux_ids = {n["id"]: str(uuid.uuid4()) for n in notions}
    lignes = [{
        "id": nouveaux_ids[n["id"]],
        "code_id": code_cible_id,
        "notion_parent_id": nouveaux_ids.get(n["notion_parent_id"]) if n["notion_parent_id"] else None,
        "nom": n["nom"],
        "ordre": n["ordre"],
        "regle_comportement": n["regle_comportement"] if reprendre_regles else None,
        "consigne_llm": n["consigne_llm"] if reprendre_regles else None,
    } for n in notions]
    # Copie en bloc : pas de revectorisation notion par notion ici
    # (coûteux en appels Gemini pour un Programme qui peut contenir
    # beaucoup de notions d'un coup) -- les notions copiées restent
    # sans embedding tant qu'elles ne sont pas renommées/éditées
    # individuellement ensuite (voir core/programme_notions.py). Point
    # non discuté explicitement avec Bourama, à confirmer si la
    # recherche sémantique du Programme doit couvrir ces notions.
    supabase.table("notions").insert(lignes).execute()

    return {"code_id": code_cible_id, "code": code_cible, "nb_notions": len(lignes)}
