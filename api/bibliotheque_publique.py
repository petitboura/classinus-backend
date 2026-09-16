"""
Bibliothèque publique (21/08/2026, demande Bourama : "un bibliothèque
publique dans la section bibliothèque, tout le monde peut y ajouter des
documents, juste en le décrivant et en donnant un nom").

CORRECTION du même jour (Bourama, après malentendu de ma part sur cette
phrase) : "nom" et "description" accompagnent un VRAI fichier uploadé,
ce ne sont pas des entrées texte à la place d'un fichier. Upload réel
dans Supabase Storage, même pattern que enregistrer_fichier (voir
core/bibliotheque_fichiers.py) -- bucket "bibliotheque", sous-dossier
"publique/" pour rester distinct des niveaux plateforme/agent/utilisateur.

Reste DISTINCT de fichiers_uploades/consulter_bibliotheque (bibliothèque
perso) : catalogue consultable par les humains dans l'appli, jamais
injecté automatiquement dans une conversation.

MISE À JOUR 28/08/2026 bis (demande Bourama : "le bouton + doit être
comme en privé -- texte/lien/fichier/dossier, nom et description
optionnels même pour un dossier") : ajout de "/lien" et "/texte" en
plus de l'upload de fichier, même principe que api/bibliotheque_
utilisateur.py côté perso. `dossier_id` optionnel sur les 3 routes
d'ajout pour classer directement à l'ajout (voir api/dossiers_
catalogue_public.py).
"""

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import create_client, ClientOptions
from core.client_http_supabase import nouveau_client_http_supabase

from api.auth import utilisateur_courant, utilisateur_optionnel
from core.erreurs import erreur_api
from core.file_attente_vectorisation import (
    necessite_vectorisation_fichier_publique,
    necessite_extraction_texte_publique,
    necessite_vectorisation_note,
    reinitialiser_pour_reessai,
)
from core.dossiers_catalogue_public import (
    ranger_fichier as _ranger_fichier_dossier,
    peut_ajouter_contenu as _peut_ajouter_contenu_dossier,
    _dossier as _dossier_catalogue_public,
    lister_fichiers_ids_dossier as _lister_fichiers_ids_dossier,
    dossiers_heritant_valeur,
    fichier_ids_pour_dossiers,
)
from core.dossiers_publics_attaches import propager_fichier_public_range_dossier as _propager_fichier_public_range_dossier
from core.catalogue_public_publication import modifier_entree_publique
from core.geolocalisation_pays import pays_utilisateur
from core.listes_bibliotheque_publique import lister_valeurs, normaliser_et_enregistrer_liste

router = APIRouter(prefix="/api/bibliotheque-publique", tags=["bibliotheque_publique"])


def _classer_si_autorise(fichier_id: str, dossier_id: str, utilisateur_id: str) -> None:
    if not (dossier_id or "").strip():
        return
    try:
        if _dossier_catalogue_public(dossier_id) and _peut_ajouter_contenu_dossier(dossier_id, utilisateur_id):
            _ranger_fichier_dossier(fichier_id, dossier_id)
            _propager_fichier_public_range_dossier(fichier_id, dossier_id)
    except Exception as e:
        logging.error(f"ERREUR classement dossier catalogue public (fichier_id={fichier_id}, dossier_id={dossier_id}) : {e}")


BUCKET = "bibliotheque"
TAILLE_MAX_OCTETS = 50 * 1024 * 1024  # 50 Mo, même limite que la bibliothèque personnelle


def _get_secret(cle):
    return os.environ.get(cle)


supabase = create_client(_get_secret("SUPABASE_URL"), _get_secret("SUPABASE_SECRET"), options=ClientOptions(httpx_client=nouveau_client_http_supabase()))


class EntreeBibliothequePublique(BaseModel):
    id: str
    nom: str
    description: str
    nom_fichier: str | None = None
    type_mime: str | None = None
    taille_octets: int | None = None
    url_publique: str | None = None
    created_at: str
    # 29/08/2026, file d'attente de vectorisation en arrière-plan (voir
    # core/file_attente_vectorisation.py) : "en_attente" / "en_cours" /
    # "pret" / "echec" -- sert au frontend pour le badge par fichier.
    statut_vectorisation: str = "pret"
    # 02/09/2026, demande Bourama : 3 filtres cochables à la publication
    # (voir core/listes_bibliotheque_publique.py), optionnels.
    # 15/09/2026, demande Bourama : un fichier peut désormais avoir
    # plusieurs valeurs par filtre, même principe que les dossiers
    # depuis le 13/09/2026 (colonnes passées en text[] côté Supabase,
    # voir migrations/2026_09_15_filtres_fichiers_catalogue_public_multi.sql).

    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    # 04/09/2026, demande Bourama : 2 filtres supplémentaires (voir
    # core/listes_bibliotheque_publique.py), même principe.
    classe: list[str] = []
    specialite: list[str] = []
    # 15/09/2026, demande Bourama (modifier les filtres après
    # publication) : True si l'utilisateur courant est le contributeur
    # d'origine de cette entrée, jamais `ajoute_par` en clair (pas
    # d'id d'un autre utilisateur exposé), juste ce booléen calculé
    # côté serveur, pour que le frontend sache s'il doit proposer le
    # bouton "Modifier les filtres" (qui échouerait en 403 sinon).
    est_a_moi: bool = False


@router.get("/listes")
def lister_listes_filtres():
    """Valeurs déjà connues pour pays/niveau/catégorie, pour peupler les menus du formulaire de publication ET les filtres de recherche côté frontend."""
    return {
        "pays": lister_valeurs("pays"),
        "niveaux": lister_valeurs("niveau"),
        "categories": lister_valeurs("categorie"),
        "classes": lister_valeurs("classe"),
        "specialites": lister_valeurs("specialite"),
    }


_CAMPOS_ENTREE = (
    "id, nom, description, nom_fichier, type_mime, taille_octets, url_publique, created_at, "
    "statut_vectorisation, pays, niveau, categorie, classe, specialite, ajoute_par"
)


def _marquer_est_a_moi(lignes: list, utilisateur) -> list:
    """
    15/09/2026, demande Bourama : calcule `est_a_moi` sur chaque ligne
    juste avant de la renvoyer. `ajoute_par` reste sélectionné en base
    (_CAMPOS_ENTREE) mais n'est jamais exposé tel quel : le modèle de
    réponse EntreeBibliothequePublique ne déclare pas ce champ, donc
    FastAPI le filtre automatiquement à la sérialisation.
    """
    for ligne in lignes:
        ligne["est_a_moi"] = bool(utilisateur and ligne.get("ajoute_par") == utilisateur.id)
    return lignes


@router.get("", response_model=list[EntreeBibliothequePublique])
def lister_bibliotheque_publique(
    request: Request,
    q: str | None = None,
    pays: str | None = None,
    niveau: str | None = None,
    categorie: str | None = None,
    classe: str | None = None,
    specialite: str | None = None,
    dossier_id: str | None = None,
    decalage: int = 0,
    limite: int = 30,
    utilisateur=Depends(utilisateur_optionnel),
):
    # Filtre statut="publie" (22/08, chantier signalements) : une entrée
    # retirée par un admin suite à un signalement reste en base (trace
    # pour l'audit) mais ne doit plus jamais réapparaître dans le
    # catalogue, voir api/signalements.py.
    #
    # 04/09/2026, demande Bourama : plus de plafond fixe (l'ancien
    # limit(200) cachait silencieusement les fichiers les plus anciens
    # dès que le catalogue dépassait 200 entrées) -- scroll infini façon
    # réseau social, chargé par lots via decalage/limite. dossier_id
    # filtre sur la table de jonction fichiers_dossiers_catalogue_public
    # pour qu'un dossier ouvert bénéficie du même chargement par lots que
    # l'onglet "Tous", au lieu de charger tout son contenu d'un coup.
    limite = min(max(limite, 1), 100)
    decalage = max(decalage, 0)

    ids_dossier = None
    if (dossier_id or "").strip():
        ids_dossier = _lister_fichiers_ids_dossier(dossier_id.strip())
        if not ids_dossier:
            return []

    def _echapper_valeur_or(v: str) -> str:
        # 13/09/2026 : valeur passée telle quelle dans le mini-langage
        # or_() de PostgREST -- toujours entre guillemets pour rester
        # sûr même si elle contient une virgule ou une parenthèse.
        return '"' + v.replace('"', '""') + '"'

    def _filtrer_avec_heritage(requete, champ: str, valeur: str):
        # 13/09/2026, demande Bourama (héritage des filtres d'un
        # dossier) : un fichier peut correspondre soit parce qu'il a
        # lui-même cette valeur, soit parce qu'un dossier ancêtre la
        # fait descendre jusqu'à lui (voir core/dossiers_catalogue_
        # public.py::dossiers_heritant_valeur, camp="fichiers").
        #
        # 15/09/2026 : `champ` est désormais un tableau (text[]) côté
        # fichier aussi (comme déjà le cas côté dossier), donc "eq" est
        # remplacé par "contains" (opérateur "cs" de PostgREST, teste
        # qu'une valeur fait partie du tableau) au lieu d'une égalité
        # stricte.
        dossiers_concernes = dossiers_heritant_valeur(champ, valeur, "fichiers")
        ids_heritage = fichier_ids_pour_dossiers(dossiers_concernes) if dossiers_concernes else []
        if not ids_heritage:
            return requete.contains(champ, [valeur])
        return requete.or_(f"{champ}.cs.{{{_echapper_valeur_or(valeur)}}},id.in.({','.join(ids_heritage)})")

    def _base(campos: str = _CAMPOS_ENTREE, count: str | None = None):
        requete = supabase.table("bibliotheque_publique").select(campos, count=count).eq("statut", "publie")
        if (q or "").strip():
            requete = requete.or_(f"nom.ilike.%{q.strip()}%,description.ilike.%{q.strip()}%")
        # 02/09/2026, demande Bourama : filtres pays/niveau/catégorie, en
        # plus du filtre par type déjà géré côté frontend.
        if (niveau or "").strip():
            requete = _filtrer_avec_heritage(requete, "niveau", niveau.strip())
        if (categorie or "").strip():
            requete = _filtrer_avec_heritage(requete, "categorie", categorie.strip())
        # 04/09/2026, demande Bourama : 2 filtres supplémentaires, même principe.
        if (classe or "").strip():
            requete = _filtrer_avec_heritage(requete, "classe", classe.strip())
        if (specialite or "").strip():
            requete = _filtrer_avec_heritage(requete, "specialite", specialite.strip())
        if ids_dossier is not None:
            requete = requete.in_("id", ids_dossier)
        return requete

    # 08/09/2026, demande Bourama : les fichiers du pays détecté de
    # l'utilisateur (voir core/geolocalisation_pays.py) remontent en
    # tête des résultats. Sans objet si l'appelant a déjà explicitement
    # filtré par pays (son filtre prime, la priorité n'a plus de sens).
    pays_filtre = (pays or "").strip()
    pays_prioritaire = None if pays_filtre else pays_utilisateur(request)

    if pays_filtre:
        res = _filtrer_avec_heritage(_base(), "pays", pays_filtre).order("created_at", desc=True).range(decalage, decalage + limite - 1).execute()
        return _marquer_est_a_moi(res.data or [], utilisateur)

    if not pays_prioritaire:
        res = _base().order("created_at", desc=True).range(decalage, decalage + limite - 1).execute()
        return _marquer_est_a_moi(res.data or [], utilisateur)

    # Mise en avant en deux temps : d'abord les entrées du pays détecté
    # (les plus récentes en premier), puis le reste -- chaque groupe
    # trié par date décroissante. Le compte du 1er groupe permet de
    # savoir, pour une fenêtre decalage/limite donnée (scroll infini),
    # quelle part de cette page vient de chaque groupe, sans jamais
    # sauter ni répéter une entrée d'une page à l'autre.
    try:
        compte_prioritaire = _base(campos="id", count="exact").contains("pays", [pays_prioritaire]).limit(1).execute().count or 0
    except Exception as e:
        logging.error(f"ERREUR comptage priorite pays (bibliotheque publique) : {e}")
        compte_prioritaire = 0

    if compte_prioritaire == 0:
        res = _base().order("created_at", desc=True).range(decalage, decalage + limite - 1).execute()
        return _marquer_est_a_moi(res.data or [], utilisateur)

    resultats: list = []
    if decalage < compte_prioritaire:
        a_prendre = min(limite, compte_prioritaire - decalage)
        res1 = (
            _base().contains("pays", [pays_prioritaire])
            .order("created_at", desc=True)
            .range(decalage, decalage + a_prendre - 1)
            .execute()
        )
        resultats.extend(res1.data or [])

    if len(resultats) < limite:
        decalage_reste = max(0, decalage - compte_prioritaire)
        a_prendre = limite - len(resultats)
        res2 = (
            # 15/09/2026 : "pays" est un tableau, donc "ne contient pas
            # cette valeur" remplace l'ancien "pays != valeur OU pays
            # est NULL" (un tableau vide n'est jamais NULL, il couvre
            # déjà ce cas via not_.contains).
            _base().not_.contains("pays", [pays_prioritaire])
            .order("created_at", desc=True)
            .range(decalage_reste, decalage_reste + a_prendre - 1)
            .execute()
        )
        resultats.extend(res2.data or [])

    return _marquer_est_a_moi(resultats, utilisateur)


@router.get("/par-url")
def obtenir_entree_bibliotheque_publique_par_url(url: str):
    """13/09/2026, demande Bourama : quand l'IA retrouve un fichier de la
    bibliothèque publique et le montre dans le chat, la carte fichier
    (components/chat/FichierChip.tsx) ne reçoit qu'un lien -- cette route
    permet au frontend de retrouver l'entrée correspondante (id) à partir
    de cette URL, pour proposer là aussi "Ajouter à ma bibliothèque" en
    plus du téléchargement réel. Renvoie 404 si l'URL ne correspond à
    aucune entrée publiée (cas normal la plupart du temps : fichier
    généré par l'IA, pas issu de la bibliothèque). Déclarée AVANT
    "/{entree_id}" ci-dessous : sinon FastAPI matcherait "par-url" comme
    un entree_id et renverrait toujours ENTREE_INTROUVABLE.
    """
    res = (
        supabase.table("bibliotheque_publique")
        .select("id")
        .eq("url_publique", url)
        .eq("statut", "publie")
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    return res.data


@router.get("/{entree_id}", response_model=EntreeBibliothequePublique)
def obtenir_entree_bibliotheque_publique(entree_id: str, utilisateur=Depends(utilisateur_optionnel)):
    """Détail d'une entrée publiée, pour la page publique /bibliotheque/[id]
    (chantier "Clovis ouvert" du 10/09/2026, demande Bourama : chaque
    PDF retrouvable par son nom et téléchargeable via un lien propre).

    Même filtre statut="publie" que la liste ci-dessus : une entrée
    retirée par un admin suite à un signalement (voir api/signalements.py)
    ou pas encore publiée ne doit jamais être accessible en devinant
    son id dans l'URL, même si le catalogue "" ne la montre plus."""
    res = (
        supabase.table("bibliotheque_publique")
        .select(_CAMPOS_ENTREE)
        .eq("id", entree_id)
        .eq("statut", "publie")
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    return _marquer_est_a_moi([res.data], utilisateur)[0]


class ModifierFiltresFichierPayload(BaseModel):
    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    classe: list[str] = []
    specialite: list[str] = []


@router.patch("/{entree_id}/filtres", response_model=EntreeBibliothequePublique)
def modifier_filtres_fichier(entree_id: str, payload: ModifierFiltresFichierPayload, utilisateur=Depends(utilisateur_courant)):
    """
    15/09/2026, demande Bourama : les filtres d'un fichier/lien/texte
    déjà publié n'étaient modifiables nulle part côté API humaine
    (seul l'outil MCP clovis_modifier_entree_catalogue_public le
    pouvait, voir core/catalogue_public_publication.py::
    modifier_entree_publique, réutilisé ici), réservé au
    contributeur d'origine, même règle que supprimer ci-dessous.
    Remplace toujours entièrement chaque filtre par la liste fournie
    (liste vide efface ce filtre), même contrat que PATCH
    /dossiers/{dossier_id}/filtres côté dossier.
    """
    erreur = modifier_entree_publique(
        entree_id, utilisateur.id,
        pays=payload.pays, niveau=payload.niveau, categorie=payload.categorie,
        classe=payload.classe, specialite=payload.specialite,
    )
    if erreur == "ENTREE_INTROUVABLE":
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    if erreur == "CETTE_ENTREE_NE_T_APPARTIENT_PAS":
        raise erreur_api(403, "CETTE_ENTREE_NE_T_APPARTIENT_PAS")
    res = supabase.table("bibliotheque_publique").select(_CAMPOS_ENTREE).eq("id", entree_id).maybe_single().execute()
    if not res or not res.data:
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    return _marquer_est_a_moi([res.data], utilisateur)[0]


@router.post("", response_model=EntreeBibliothequePublique, status_code=201)
async def ajouter_a_bibliotheque_publique(
    fichier: UploadFile = File(...),
    nom: str = Form(""),
    description: str = Form(""),
    dossier_id: str = Form(""),
    # 15/09/2026, demande Bourama : plusieurs valeurs possibles par
    # filtre, même principe que les dossiers. Le frontend envoie
    # chaque valeur comme une entrée distincte du FormData sous le même
    # nom de champ (ex. formData.append("pays", "Mali");
    # formData.append("pays", "Sénégal")).
    pays: list[str] = Form([]),
    niveau: list[str] = Form([]),
    categorie: list[str] = Form([]),
    classe: list[str] = Form([]),
    specialite: list[str] = Form([]),
    utilisateur=Depends(utilisateur_courant),
):
    # Nom optionnel (28/08, demande Bourama : "nom et description
    # optionnels même pour dossier") -- repli sur le nom du fichier
    # sans extension, même logique que la bibliothèque perso.
    nom_final = (nom or "").strip() or (fichier.filename or "Document").rsplit(".", 1)[0]

    contenu = await fichier.read()
    if len(contenu) == 0:
        raise erreur_api(400, "FICHIER_VIDE")
    if len(contenu) > TAILLE_MAX_OCTETS:
        raise erreur_api(400, "FICHIER_TROP_LOURD_50_MO_MAX")

    nom_original = fichier.filename or "fichier"
    extension = nom_original.rsplit(".", 1)[-1] if "." in nom_original else "bin"
    chemin_stockage = f"publique/{uuid.uuid4()}.{extension}"

    def _stocker_et_inserer():
        # Factorisé le 02/09 (bug remonté par Bourama : upload perçu
        # comme lent) pour pouvoir déporter l'ENSEMBLE storage+DB sur un
        # thread via asyncio.to_thread -- ces appels Supabase sont
        # synchrones/bloquants, et appelés tels quels dans cette route
        # async, ils bloquaient tout le serveur (event loop) pendant
        # toute la durée de l'upload.
        supabase.storage.from_(BUCKET).upload(
            chemin_stockage, contenu, {"content-type": fichier.content_type or "application/octet-stream"}
        )
        url_publique = supabase.storage.from_(BUCKET).get_public_url(chemin_stockage)
        return (
            supabase.table("bibliotheque_publique")
            .insert({
                "ajoute_par": utilisateur.id,
                "nom": nom_final,
                "description": (description or "").strip(),
                "nom_fichier": nom_original,
                "chemin_stockage": chemin_stockage,
                "url_publique": url_publique,
                "type_mime": fichier.content_type,
                "taille_octets": len(contenu),
                # 29/08/2026, file d'attente de vectorisation en
                # arrière-plan (voir core/file_attente_vectorisation.py) :
                # avant, la vectorisation (_indexer_catalogue_public,
                # retirée) se faisait ici, de façon synchrone et
                # bloquante -- long sur un gros fichier ou un upload en
                # masse.
                # 06/09/2026, demande Bourama : seule l'image garde une
                # vraie vectorisation automatique ; pdf/word/excel/texte
                # reçoivent une extraction de texte gratuite automatique
                # (statut_extraction_texte) ; audio/vidéo/inconnu restent
                # entièrement à la demande (voir docstring de
                # core/file_attente_vectorisation.py).
                **(
                    {"statut_vectorisation": "en_attente", "statut_extraction_texte": "non_applicable"}
                    if necessite_vectorisation_fichier_publique(fichier.content_type)
                    else {"statut_vectorisation": "a_la_demande", "statut_extraction_texte": "en_attente"}
                    if necessite_extraction_texte_publique(fichier.content_type)
                    else {"statut_vectorisation": "a_la_demande", "statut_extraction_texte": "non_applicable"}
                ),
                # 02/09/2026, demande Bourama : 3 filtres optionnels à la
                # publication (voir core/listes_bibliotheque_publique.py).
                "pays": normaliser_et_enregistrer_liste("pays", pays),
                "niveau": normaliser_et_enregistrer_liste("niveau", niveau),
                "categorie": normaliser_et_enregistrer_liste("categorie", categorie),
                "classe": normaliser_et_enregistrer_liste("classe", classe),
                "specialite": normaliser_et_enregistrer_liste("specialite", specialite),
            })
            .execute()
        )

    def _rollback_storage():
        # CORRECTIF 16/09/2026 (Bourama : fichiers orphelins dans le
        # Storage sans ligne BDD, decouverts lors d'un depassement de
        # quota Supabase -- 714 fichiers, ~2 Go, rien que sur ce dossier
        # "publique"). _stocker_et_inserer uploade d'abord vers le
        # Storage PUIS insere en base (une seule transaction cote appel,
        # mais deux systemes distincts) ; si l'insertion echoue pour
        # N'IMPORTE QUELLE raison (doublon de nom, coupure reseau,
        # erreur Supabase...), le fichier deja uploade restait pour
        # toujours dans le bucket, invisible et inutilisable puisque rien
        # ne le retrouve sans ligne chemin_stockage, mais consommant quand
        # meme le quota de stockage. On le supprime ici avant de relancer
        # l'erreur d'origine vers le client.
        try:
            supabase.storage.from_(BUCKET).remove([chemin_stockage])
        except Exception as e2:
            logging.error(f"ECHEC ROLLBACK STORAGE apres echec BDD ({chemin_stockage}) : {e2}")

    try:
        ligne = await asyncio.to_thread(_stocker_et_inserer)
    except APIError as e:
        # CORRECTIF 02/09 (bug remonté par Bourama : aucun traitement
        # d'erreur à l'upload, notamment pour les doublons désormais
        # refusés par un index unique Supabase -- code Postgres 23505).
        await asyncio.to_thread(_rollback_storage)
        if getattr(e, "code", None) == "23505":
            raise erreur_api(409, "NOM_DEJA_UTILISE_BIBLIOTHEQUE_PUBLIQUE", nom=nom_original)
        logging.error(f"ERREUR SUPABASE (upload bibliothèque publique {chemin_stockage}) : {e}")
        raise erreur_api(500, "ECHEC_DU_STOCKAGE_REESSAIE")
    except Exception as e:
        await asyncio.to_thread(_rollback_storage)
        logging.error(f"ERREUR SUPABASE (upload bibliothèque publique {chemin_stockage}) : {e}")
        raise erreur_api(500, "ECHEC_DU_STOCKAGE_REESSAIE")

    entree = ligne.data[0]
    await asyncio.to_thread(_classer_si_autorise, entree["id"], dossier_id, utilisateur.id)
    return _marquer_est_a_moi([entree], utilisateur)[0]


class AjouterLienPayload(BaseModel):
    url: str
    nom: str = ""
    description: str = ""
    dossier_id: str = ""
    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    classe: list[str] = []
    specialite: list[str] = []


@router.post("/lien", response_model=EntreeBibliothequePublique, status_code=201)
def ajouter_lien_bibliotheque_publique(payload: AjouterLienPayload, utilisateur=Depends(utilisateur_courant)):
    """Ajoute un lien au catalogue public (28/08, parité avec le sélecteur du privé). Pas de fichier réel : url_publique EST le lien lui-même."""
    if not (payload.url or "").strip():
        raise erreur_api(400, "URL_MANQUANTE")
    nom_final = (payload.nom or "").strip() or payload.url.strip()

    try:
        ligne = (
            supabase.table("bibliotheque_publique")
            .insert({
                "ajoute_par": utilisateur.id,
                "nom": nom_final,
                "description": (payload.description or "").strip(),
                "nom_fichier": nom_final,
                "url_publique": payload.url.strip(),
                "type_mime": "text/uri-list",
                "statut_vectorisation": "pret",  # un lien n'est jamais vectorisé
                "pays": normaliser_et_enregistrer_liste("pays", payload.pays),
                "niveau": normaliser_et_enregistrer_liste("niveau", payload.niveau),
                "categorie": normaliser_et_enregistrer_liste("categorie", payload.categorie),
                "classe": normaliser_et_enregistrer_liste("classe", payload.classe),
                "specialite": normaliser_et_enregistrer_liste("specialite", payload.specialite),
            })
            .execute()
        )
    except APIError as e:
        if getattr(e, "code", None) == "23505":
            raise erreur_api(409, "NOM_DEJA_UTILISE_BIBLIOTHEQUE_PUBLIQUE", nom=nom_final)
        logging.error(f"ERREUR ECRITURE bibliotheque_publique (lien) : {e}")
        raise erreur_api(500, "ERREUR_INCONNUE")
    except Exception as e:
        logging.error(f"ERREUR ECRITURE bibliotheque_publique (lien) : {e}")
        raise erreur_api(500, "ERREUR_INCONNUE")

    entree = ligne.data[0]
    _classer_si_autorise(entree["id"], payload.dossier_id, utilisateur.id)
    return _marquer_est_a_moi([entree], utilisateur)[0]


class AjouterTextePayload(BaseModel):
    contenu: str
    nom: str = ""
    dossier_id: str = ""
    pays: list[str] = []
    niveau: list[str] = []
    categorie: list[str] = []
    classe: list[str] = []
    specialite: list[str] = []


@router.post("/texte", response_model=EntreeBibliothequePublique, status_code=201)
def ajouter_texte_bibliotheque_publique(payload: AjouterTextePayload, utilisateur=Depends(utilisateur_courant)):
    """Ajoute une note de texte libre au catalogue public (28/08, parité avec le sélecteur du privé) -- stockée comme un .txt ordinaire, indexée directement."""
    contenu_texte = (payload.contenu or "").strip()
    if not contenu_texte:
        raise erreur_api(400, "TEXTE_VIDE")
    nom_final = (payload.nom or "").strip() or (contenu_texte[:80] + ("…" if len(contenu_texte) > 80 else ""))
    contenu_octets = contenu_texte.encode("utf-8")
    nom_fichier = f"{nom_final}.txt"
    chemin_stockage = f"publique/{uuid.uuid4()}.txt"

    try:
        supabase.storage.from_(BUCKET).upload(chemin_stockage, contenu_octets, {"content-type": "text/plain"})
    except Exception as e:
        logging.error(f"ERREUR SUPABASE STORAGE (note texte bibliothèque publique {chemin_stockage}) : {e}")
        raise erreur_api(500, "ECHEC_DU_STOCKAGE_REESSAIE")

    url_publique = supabase.storage.from_(BUCKET).get_public_url(chemin_stockage)

    try:
        ligne = (
            supabase.table("bibliotheque_publique")
            .insert({
                "ajoute_par": utilisateur.id,
                "nom": nom_final,
                "description": "",
                "nom_fichier": nom_fichier,
                "chemin_stockage": chemin_stockage,
                "url_publique": url_publique,
                "type_mime": "text/plain",
                "taille_octets": len(contenu_octets),
                "statut_vectorisation": "en_attente" if necessite_vectorisation_note() else "pret",
                "pays": normaliser_et_enregistrer_liste("pays", payload.pays),
                "niveau": normaliser_et_enregistrer_liste("niveau", payload.niveau),
                "categorie": normaliser_et_enregistrer_liste("categorie", payload.categorie),
                "classe": normaliser_et_enregistrer_liste("classe", payload.classe),
                "specialite": normaliser_et_enregistrer_liste("specialite", payload.specialite),
            })
            .execute()
        )
    except APIError as e:
        if getattr(e, "code", None) == "23505":
            raise erreur_api(409, "NOM_DEJA_UTILISE_BIBLIOTHEQUE_PUBLIQUE", nom=nom_fichier)
        logging.error(f"ERREUR ECRITURE bibliotheque_publique (texte) : {e}")
        raise erreur_api(500, "ERREUR_INCONNUE")
    except Exception as e:
        logging.error(f"ERREUR ECRITURE bibliotheque_publique (texte) : {e}")
        raise erreur_api(500, "ERREUR_INCONNUE")

    entree = ligne.data[0]
    _classer_si_autorise(entree["id"], payload.dossier_id, utilisateur.id)
    # Vectorisation en arrière-plan (29/08, voir core/file_attente_vectorisation.py) --
    # avant, indexer_texte_catalogue_public était appelé directement ici.
    return _marquer_est_a_moi([entree], utilisateur)[0]


@router.post("/{entree_id}/reessayer-vectorisation", status_code=204)
def reessayer_vectorisation_publique(entree_id: str, utilisateur=Depends(utilisateur_courant)):
    """Pendant de reessayer_vectorisation (api/bibliotheque_utilisateur.py) pour la bibliothèque publique -- voir sa docstring."""
    res = (
        supabase.table("bibliotheque_publique")
        .select("ajoute_par, statut_vectorisation")
        .eq("id", entree_id)
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    if res.data["ajoute_par"] != utilisateur.id:
        raise erreur_api(403, "CETTE_ENTREE_NE_T_APPARTIENT_PAS")

    if not reinitialiser_pour_reessai("bibliotheque_publique", entree_id):
        raise erreur_api(409, "ENTREE_PAS_EN_ECHEC")


@router.delete("/{entree_id}", status_code=204)
def supprimer_de_bibliotheque_publique(entree_id: str, utilisateur=Depends(utilisateur_courant)):
    """Seul le contributeur d'origine peut retirer SA propre entrée --
    même principe que declasser_document sur les plugins publics. Le
    fichier dans Supabase Storage n'est pas explicitement retiré ici
    (même choix que le reste de la bibliothèque -- voir
    core/bibliotheque_fichiers.py, aucune suppression de storage n'y est
    faite non plus au retrait d'une ligne)."""
    res = (
        supabase.table("bibliotheque_publique")
        .select("ajoute_par")
        .eq("id", entree_id)
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise erreur_api(404, "ENTREE_INTROUVABLE")
    if res.data["ajoute_par"] != utilisateur.id:
        raise erreur_api(403, "CETTE_ENTREE_NE_T_APPARTIENT_PAS")
    supabase.table("bibliotheque_publique").delete().eq("id", entree_id).execute()
