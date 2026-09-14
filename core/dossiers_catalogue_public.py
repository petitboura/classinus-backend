"""
Dossiers du catalogue public (28/08/2026, demande Bourama). Voir
migrations/2026_08_28_dossiers_catalogue_public.sql pour le schéma.

Différence clé avec core/dossiers_bibliotheque.py (perso) : un dossier
public a un `statut` choisi par son créateur à la création --
'contribution_libre' (tout utilisateur connecté peut y AJOUTER un
document) ou 'privee' (seul le créateur le peut). CORRECTIF 28/08
(Bourama : "tout le monde ne peut pas retirer un dossier public, ni
lui ni ses fichiers, seulement le créateur") : contribution_libre
donne le droit d'AJOUTER, jamais de RETIRER -- retirer un fichier d'un
dossier, renommer le dossier ou le supprimer restent réservés au
créateur dans TOUS les cas, y compris contribution_libre.

Supprimer un dossier public NE supprime JAMAIS les documents qu'il
contenait (contrairement au perso) : ce sont des ressources partagées
par toute la communauté, pas la propriété du dossier.

ÉVOLUTION 09/09/2026 (demande Bourama, "confirmation contributeurs") :
voir migrations/2026_09_09_demandes_dossiers_catalogue_public.sql. Dans
un dossier à contribution libre, retirer/déplacer un FICHIER ou
déplacer/supprimer un SOUS-DOSSIER (dossier_parent_id non nul) ne sont
plus des actions bloquées pour un non-créateur : elles deviennent une
DEMANDE bloquée tant que le créateur concerné n'a pas confirmé (il peut
aussi refuser explicitement). Le dossier racine lui-même (renommer,
supprimer) n'est pas concerné, reste strictement réservé au créateur,
immédiat, comportement inchangé. Ajouter reste également immédiat pour
tous en contribution_libre, jamais concerné par une demande.
Qui doit confirmer : le créateur du DOSSIER QUI CONTIENT le fichier
pour une action fichier, le créateur DU SOUS-DOSSIER lui-même pour une
action sous-dossier (chaque dossier a son propre créateur, jamais celui
du parent).
"""

from api.auth import supabase
from core.notifications import creer_notification


_CAMPOS_DOSSIER = (
    "id, cree_par, nom, description, statut, dossier_parent_id, created_at, "
    "pays, niveau, categorie, classe, specialite, "
    # 13/09/2026, demande Bourama : réglages d'héritage vers sous-dossiers/fichiers, par filtre.
    "pays_heritage_sous_dossiers, pays_heritage_fichiers, "
    "niveau_heritage_sous_dossiers, niveau_heritage_fichiers, "
    "categorie_heritage_sous_dossiers, categorie_heritage_fichiers, "
    "classe_heritage_sous_dossiers, classe_heritage_fichiers, "
    "specialite_heritage_sous_dossiers, specialite_heritage_fichiers"
)


def _dossier(dossier_id: str) -> dict | None:
    res = (
        supabase.table("dossiers_catalogue_public")
        .select(_CAMPOS_DOSSIER)
        .eq("id", dossier_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def peut_ajouter_contenu(dossier_id: str, user_id: str) -> bool:
    """Renvoie True si `user_id` peut RANGER un document dans ce dossier (créateur toujours, ou n'importe qui si statut='contribution_libre')."""
    dossier = _dossier(dossier_id)
    if not dossier:
        return False
    return dossier["statut"] == "contribution_libre" or dossier["cree_par"] == user_id


def peut_retirer_contenu(dossier_id: str, user_id: str) -> bool:
    """Renvoie True si `user_id` peut RETIRER un document de ce dossier -- réservé au créateur, MÊME si statut='contribution_libre' (28/08, correctif Bourama)."""
    dossier = _dossier(dossier_id)
    if not dossier:
        return False
    return dossier["cree_par"] == user_id


def creer_dossier(
    user_id: str, nom: str, statut: str = "contribution_libre", dossier_parent_id: str = None,
    pays: list[str] | None = None, niveau: list[str] | None = None, categorie: list[str] | None = None,
    classe: list[str] | None = None, specialite: list[str] | None = None, description: str = "",
    # 13/09/2026, demande Bourama : pour chaque filtre, quelles valeurs
    # (parmi celles ci-dessus) descendent automatiquement aux
    # sous-dossiers et/ou aux fichiers, à n'importe quelle profondeur --
    # voir dossiers_heritant_valeur() plus bas. Chaque liste DOIT être
    # un sous-ensemble de la liste de base correspondante (vérifié par
    # l'appelant, voir api/dossiers_catalogue_public.py).
    pays_heritage_sous_dossiers: list[str] | None = None, pays_heritage_fichiers: list[str] | None = None,
    niveau_heritage_sous_dossiers: list[str] | None = None, niveau_heritage_fichiers: list[str] | None = None,
    categorie_heritage_sous_dossiers: list[str] | None = None, categorie_heritage_fichiers: list[str] | None = None,
    classe_heritage_sous_dossiers: list[str] | None = None, classe_heritage_fichiers: list[str] | None = None,
    specialite_heritage_sous_dossiers: list[str] | None = None, specialite_heritage_fichiers: list[str] | None = None,
) -> dict:
    insertion = supabase.table("dossiers_catalogue_public").insert({
        "cree_par": user_id,
        "nom": nom,
        # 08/09/2026, demande Bourama : les dossiers suivent la même
        # logique que les fichiers -- description optionnelle, y compris
        # pour un sous-dossier (même formulaire, voir api/dossiers_
        # catalogue_public.py).
        "description": description or "",
        "statut": statut,
        "dossier_parent_id": dossier_parent_id,
        # 02/09/2026, demande Bourama : 3 filtres optionnels, cochables
        # aussi à la publication d'un DOSSIER (pas seulement un fichier),
        # voir core/listes_bibliotheque_publique.py.
        # 13/09/2026, demande Bourama : chaque filtre accepte désormais
        # PLUSIEURS valeurs pour un dossier (uniquement -- un fichier
        # garde une seule valeur, inchangé). Colonnes text[] côté
        # Supabase, voir migrations/2026_09_13_filtres_dossiers_
        # catalogue_public_multi.sql.
        "pays": pays or [],
        "niveau": niveau or [],
        "categorie": categorie or [],
        # 04/09/2026, demande Bourama : 2 filtres supplémentaires, même principe.
        "classe": classe or [],
        "specialite": specialite or [],
        # 13/09/2026 (suite), demande Bourama : héritage vers sous-dossiers/fichiers,
        # voir migrations/2026_09_13b_heritage_filtres_dossiers_catalogue_public.sql.
        "pays_heritage_sous_dossiers": pays_heritage_sous_dossiers or [],
        "pays_heritage_fichiers": pays_heritage_fichiers or [],
        "niveau_heritage_sous_dossiers": niveau_heritage_sous_dossiers or [],
        "niveau_heritage_fichiers": niveau_heritage_fichiers or [],
        "categorie_heritage_sous_dossiers": categorie_heritage_sous_dossiers or [],
        "categorie_heritage_fichiers": categorie_heritage_fichiers or [],
        "classe_heritage_sous_dossiers": classe_heritage_sous_dossiers or [],
        "classe_heritage_fichiers": classe_heritage_fichiers or [],
        "specialite_heritage_sous_dossiers": specialite_heritage_sous_dossiers or [],
        "specialite_heritage_fichiers": specialite_heritage_fichiers or [],
    }).execute()
    return insertion.data[0]


def renommer_dossier(dossier_id: str, nouveau_nom: str) -> None:
    supabase.table("dossiers_catalogue_public").update({"nom": nouveau_nom}).eq("id", dossier_id).execute()


def modifier_filtres_dossier(
    dossier_id: str,
    pays: list[str] | None = None, niveau: list[str] | None = None, categorie: list[str] | None = None,
    classe: list[str] | None = None, specialite: list[str] | None = None,
    pays_heritage_sous_dossiers: list[str] | None = None, pays_heritage_fichiers: list[str] | None = None,
    niveau_heritage_sous_dossiers: list[str] | None = None, niveau_heritage_fichiers: list[str] | None = None,
    categorie_heritage_sous_dossiers: list[str] | None = None, categorie_heritage_fichiers: list[str] | None = None,
    classe_heritage_sous_dossiers: list[str] | None = None, classe_heritage_fichiers: list[str] | None = None,
    specialite_heritage_sous_dossiers: list[str] | None = None, specialite_heritage_fichiers: list[str] | None = None,
) -> None:
    """
    13/09/2026, demande Bourama : les 5 filtres d'un dossier n'étaient
    modifiables nulle part jusqu'ici (seul renommer_dossier existait) --
    permet désormais de les changer après coup, réservé au créateur du
    dossier (même règle que renommer_dossier, voir api/dossiers_
    catalogue_public.py pour la vérification cree_par).

    13/09/2026 (suite) : + réglage d'héritage vers sous-dossiers/fichiers
    par valeur, voir dossiers_heritant_valeur() plus bas.
    """
    supabase.table("dossiers_catalogue_public").update({
        "pays": pays or [],
        "niveau": niveau or [],
        "categorie": categorie or [],
        "classe": classe or [],
        "specialite": specialite or [],
        "pays_heritage_sous_dossiers": pays_heritage_sous_dossiers or [],
        "pays_heritage_fichiers": pays_heritage_fichiers or [],
        "niveau_heritage_sous_dossiers": niveau_heritage_sous_dossiers or [],
        "niveau_heritage_fichiers": niveau_heritage_fichiers or [],
        "categorie_heritage_sous_dossiers": categorie_heritage_sous_dossiers or [],
        "categorie_heritage_fichiers": categorie_heritage_fichiers or [],
        "classe_heritage_sous_dossiers": classe_heritage_sous_dossiers or [],
        "classe_heritage_fichiers": classe_heritage_fichiers or [],
        "specialite_heritage_sous_dossiers": specialite_heritage_sous_dossiers or [],
        "specialite_heritage_fichiers": specialite_heritage_fichiers or [],
    }).eq("id", dossier_id).execute()


def lister_dossiers(pays_prioritaire: str | None = None) -> list:
    """
    Liste TOUS les dossiers du catalogue public, à plat -- visible par
    tout le monde, contrairement au perso.

    08/09/2026, demande Bourama : les dossiers du pays détecté de
    l'utilisateur (voir core/geolocalisation_pays.py) remontent en tête
    de liste. Pas de pagination ici (liste complète, filtrée/affichée
    ensuite côté frontend par arborescence) -- un simple tri Python
    suffit, contrairement au listing paginé des fichiers (voir
    api/bibliotheque_publique.py) où un tri en deux temps est nécessaire.
    """
    dossiers = (
        supabase.table("dossiers_catalogue_public")
        .select(_CAMPOS_DOSSIER)
        .order("created_at")
        .execute()
        .data
    )
    if pays_prioritaire:
        # 13/09/2026 : "pays" est désormais une liste (plusieurs valeurs
        # possibles par dossier) -- on regarde si le pays prioritaire en
        # fait partie, au lieu d'une égalité stricte.
        dossiers.sort(key=lambda d: 0 if pays_prioritaire in (d.get("pays") or []) else 1)
    return dossiers


def lister_fichiers_ids_dossier(dossier_id: str) -> list:
    res = (
        supabase.table("fichiers_dossiers_catalogue_public")
        .select("fichier_id")
        .eq("dossier_id", dossier_id)
        .execute()
    )
    return [ligne["fichier_id"] for ligne in res.data]


def fichier_ids_pour_dossiers(dossier_ids: set) -> list:
    """
    13/09/2026, demande Bourama (héritage des filtres) : même chose que
    lister_fichiers_ids_dossier() ci-dessus, mais pour tout un ensemble
    de dossiers d'un coup (utilisé pour retrouver les fichiers qui
    héritent d'une valeur via leur dossier, voir dossiers_heritant_
    valeur() plus bas et api/bibliotheque_publique.py).
    """
    if not dossier_ids:
        return []
    res = (
        supabase.table("fichiers_dossiers_catalogue_public")
        .select("fichier_id")
        .in_("dossier_id", list(dossier_ids))
        .execute()
    )
    return [ligne["fichier_id"] for ligne in res.data]


def ranger_fichier(fichier_id: str, dossier_id: str) -> None:
    supabase.table("fichiers_dossiers_catalogue_public").upsert({
        "fichier_id": fichier_id,
        "dossier_id": dossier_id,
    }).execute()


def retirer_fichier(fichier_id: str, dossier_id: str) -> None:
    supabase.table("fichiers_dossiers_catalogue_public").delete().eq("fichier_id", fichier_id).eq("dossier_id", dossier_id).execute()


def supprimer_dossier(dossier_id: str) -> None:
    """Supprime le dossier (et ses sous-dossiers, ON DELETE CASCADE) -- ne touche JAMAIS aux documents eux-mêmes, voir docstring du module."""
    supabase.table("dossiers_catalogue_public").delete().eq("id", dossier_id).execute()


def _tous_les_dossiers_par_id() -> dict:
    return {d["id"]: d for d in lister_dossiers()}


def _map_enfants(dossiers: list) -> dict:
    """13/09/2026 : parent_id -> liste des ids de ses sous-dossiers DIRECTS."""
    enfants: dict = {}
    for d in dossiers:
        parent = d.get("dossier_parent_id")
        if parent:
            enfants.setdefault(parent, []).append(d["id"])
    return enfants


def _descendants(dossier_id: str, enfants: dict) -> set:
    """13/09/2026 : tous les sous-dossiers de dossier_id, à N'IMPORTE
    QUELLE profondeur (sans dossier_id lui-même)."""
    resultat: set = set()
    a_visiter = list(enfants.get(dossier_id, []))
    while a_visiter:
        courant = a_visiter.pop()
        if courant in resultat:
            continue
        resultat.add(courant)
        a_visiter.extend(enfants.get(courant, []))
    return resultat


def dossiers_heritant_valeur(filtre: str, valeur: str, camp: str, dossiers: list | None = None) -> set:
    """
    13/09/2026, demande Bourama : un dossier peut faire descendre
    automatiquement une valeur de filtre à tous ses descendants (sous-
    dossiers ET fichiers, à n'importe quelle profondeur, de façon
    additive -- jamais de remplacement des valeurs propres d'un
    descendant). `camp` vaut "sous_dossiers" ou "fichiers" (colonne
    `{filtre}_heritage_{camp}` sur dossiers_catalogue_public).

    Retourne l'ensemble des ids de dossier concernés :
    - camp="fichiers" : le(s) dossier(s) racine(s) qui portent cette
      valeur en héritage EUX-MÊMES, PLUS tous leurs descendants -- les
      fichiers rangés directement dans n'importe lequel de ces dossiers
      héritent de la valeur (voir fichier_ids_pour_dossiers ci-dessus).
    - camp="sous_dossiers" : uniquement les descendants (le dossier
      racine lui-même n'est pas "son propre sous-dossier").
    """
    colonne = f"{filtre}_heritage_{camp}"
    tous = dossiers if dossiers is not None else lister_dossiers()
    racines = {d["id"] for d in tous if valeur in (d.get(colonne) or [])}
    if not racines:
        return set()
    enfants = _map_enfants(tous)
    descendants_totaux: set = set()
    for racine in racines:
        descendants_totaux |= _descendants(racine, enfants)
    if camp == "fichiers":
        return racines | descendants_totaux
    return descendants_totaux


def deplacerait_en_boucle(dossier_id: str, nouveau_parent_id: str | None) -> bool:
    """Vrai si donner `nouveau_parent_id` comme parent à `dossier_id`
    créerait une boucle (dans lui-même ou dans l'un de ses propres
    sous-dossiers)."""
    if not nouveau_parent_id:
        return False
    if nouveau_parent_id == dossier_id:
        return True
    par_id = _tous_les_dossiers_par_id()
    courant = par_id.get(nouveau_parent_id, {}).get("dossier_parent_id")
    while courant:
        if courant == dossier_id:
            return True
        courant = par_id.get(courant, {}).get("dossier_parent_id")
    return False


def deplacer_dossier(dossier_id: str, nouveau_parent_id: str | None) -> None:
    """Change le parent d'un sous-dossier. Permissions et boucle à
    vérifier par l'appelant (voir api/dossiers_catalogue_public.py)."""
    supabase.table("dossiers_catalogue_public").update(
        {"dossier_parent_id": nouveau_parent_id}
    ).eq("id", dossier_id).execute()


# ---------------------------------------------------------------------------
# Confirmation contributeurs (09/09/2026, demande Bourama) -- voir docstring
# du module et migrations/2026_09_09_demandes_dossiers_catalogue_public.sql.
# ---------------------------------------------------------------------------

_LIBELLES_ACTIONS = {
    "deplacer_fichier": "Déplacer un fichier",
    "supprimer_fichier": "Retirer un fichier",
    "deplacer_dossier": "Déplacer un sous-dossier",
    "supprimer_dossier": "Supprimer un sous-dossier",
}


def _demande(demande_id: str) -> dict | None:
    res = (
        supabase.table("demandes_dossiers_catalogue_public")
        .select("*")
        .eq("id", demande_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def creer_demande(
    action: str, createur_id: str, demandeur_id: str, dossier_id: str,
    fichier_id: str | None = None, dossier_destination_id: str | None = None,
) -> dict:
    """Enregistre une demande bloquée + notifie le créateur concerné.
    N'exécute jamais l'action elle-même -- voir confirmer_demande."""
    insertion = supabase.table("demandes_dossiers_catalogue_public").insert({
        "action": action,
        "fichier_id": fichier_id,
        "dossier_id": dossier_id,
        "dossier_destination_id": dossier_destination_id,
        "demandeur_id": demandeur_id,
        "createur_id": createur_id,
    }).execute()
    demande = insertion.data[0]
    creer_notification(
        user_id=createur_id,
        type_notif="demande_confirmation_dossier_public",
        titre="Une demande attend ta confirmation",
        contenu=f"{_LIBELLES_ACTIONS.get(action, action)} -- quelqu'un le demande dans un de tes dossiers de la bibliothèque publique.",
        lien="/bibliotheque-publique?demandes=1",
    )
    return demande


def lister_demandes_en_attente(user_id: str) -> list:
    """Demandes que `user_id` (créateur concerné) doit confirmer ou refuser."""
    res = (
        supabase.table("demandes_dossiers_catalogue_public")
        .select("*")
        .eq("createur_id", user_id)
        .eq("statut", "en_attente")
        .order("created_at")
        .execute()
    )
    return res.data or []


def _marquer_demande(demande_id: str, statut: str) -> dict:
    import datetime

    res = (
        supabase.table("demandes_dossiers_catalogue_public")
        .update({"statut": statut, "traite_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        .eq("id", demande_id)
        .execute()
    )
    return res.data[0]


def confirmer_demande(demande_id: str, acteur_id: str) -> dict:
    from core.erreurs import erreur_api

    demande = _demande(demande_id)
    if not demande:
        raise erreur_api(404, "DEMANDE_INTROUVABLE")
    if demande["statut"] != "en_attente":
        raise erreur_api(409, "DEMANDE_DEJA_TRAITEE")
    if demande["createur_id"] != acteur_id:
        raise erreur_api(403, "SEUL_LE_CREATEUR_CONCERNE_PEUT_CONFIRMER")

    action = demande["action"]
    if action == "deplacer_fichier":
        from core.dossiers_publics_attaches import propager_fichier_public_range_dossier

        retirer_fichier(demande["fichier_id"], demande["dossier_id"])
        ranger_fichier(demande["fichier_id"], demande["dossier_destination_id"])
        # Même règle que api/dossiers_catalogue_public.py::ranger : toute
        # arrivée d'un fichier dans un dossier du catalogue public doit
        # se propager chez qui a attaché ce dossier (ou un de ses
        # ancêtres) à sa bibliothèque perso -- oublié dans la 1ère version
        # de cette fonction, corrigé le 09/09/2026 en vérifiant tout avant
        # de dire "c'est fait" à Bourama.
        propager_fichier_public_range_dossier(demande["fichier_id"], demande["dossier_destination_id"])
    elif action == "supprimer_fichier":
        retirer_fichier(demande["fichier_id"], demande["dossier_id"])
    elif action == "deplacer_dossier":
        deplacer_dossier(demande["dossier_id"], demande["dossier_destination_id"])
    elif action == "supprimer_dossier":
        supprimer_dossier(demande["dossier_id"])

    mise_a_jour = _marquer_demande(demande_id, "confirmee")
    creer_notification(
        user_id=demande["demandeur_id"],
        type_notif="demande_dossier_public_traitee",
        titre="Ta demande a été confirmée",
        contenu=f"{_LIBELLES_ACTIONS.get(action, action)} -- confirmé, c'est fait.",
        lien="/bibliotheque-publique",
    )
    return mise_a_jour


def refuser_demande(demande_id: str, acteur_id: str) -> dict:
    from core.erreurs import erreur_api

    demande = _demande(demande_id)
    if not demande:
        raise erreur_api(404, "DEMANDE_INTROUVABLE")
    if demande["statut"] != "en_attente":
        raise erreur_api(409, "DEMANDE_DEJA_TRAITEE")
    if demande["createur_id"] != acteur_id:
        raise erreur_api(403, "SEUL_LE_CREATEUR_CONCERNE_PEUT_REFUSER")

    mise_a_jour = _marquer_demande(demande_id, "refusee")
    creer_notification(
        user_id=demande["demandeur_id"],
        type_notif="demande_dossier_public_traitee",
        titre="Ta demande a été refusée",
        contenu=f"{_LIBELLES_ACTIONS.get(demande['action'], demande['action'])} -- refusé par le créateur concerné.",
        lien="/bibliotheque-publique",
    )
    return mise_a_jour
