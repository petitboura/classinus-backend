"""
Bibliothèque de fichiers uploadés, persistante, à 3 niveaux d'accès :
- "plateforme"  : uploadé par Bourama, visible par TOUS les agents
- "agent"       : uploadé par le créateur d'un agent, visible par tous
                   les utilisateurs de CET agent précis
- "utilisateur" : uploadé par un utilisateur dans le chat, visible par
                   lui seul

Remplace le comportement précédent où un fichier uploadé (image ou
document) n'était utilisé qu'une seule fois puis jeté (voir
api/uploads.py avant le 2026-07-22) : ici, tout fichier est conservé
dans Supabase Storage (bucket "bibliotheque") ET indexé dans la table
fichiers_uploades, pour qu'un agent puisse le retrouver et le
redonner/afficher plus tard, y compris dans une autre conversation.

Un seul type de fichier n'est pas privilégié : image, PDF, audio,
vidéo... tout passe par le même mécanisme, seule la description texte
(fournie à l'upload) permet à l'IA de savoir ce que contient le fichier
sans avoir besoin de l'ouvrir.
"""

import logging
import os

from supabase import create_client, ClientOptions
from client_http_supabase import nouveau_client_http_supabase
from dedoublonnage_stockage import stocker_avec_dedoublonnage, supprimer_stockage_si_dernier_usage

BUCKET = "bibliotheque"


def _get_secret(cle):
    return os.environ.get(cle)


supabase = create_client(_get_secret("SUPABASE_URL"), _get_secret("SUPABASE_SECRET"), options=ClientOptions(httpx_client=nouveau_client_http_supabase()))


def enregistrer_lien(
    url: str,
    nom_fichier: str,
    niveau: str,
    uploade_par: str,
    agent_id: str = None,
    user_id: str = None,
    description: str = None,
    origine: str = "bibliotheque",
) -> dict:
    """
    Variante de enregistrer_fichier pour une entrée "lien" (juste une URL,
    aucun fichier uploadé -- Bourama 01/08 : l'onglet "Lien" existait déjà
    côté filtre mais rien ne permettait vraiment d'en ajouter un). Pas
    d'upload Supabase Storage ici : url_publique EST l'URL donnée.
    chemin_stockage est NOT NULL en base mais inutilisé pour un lien --
    on y met l'URL aussi, pour rester traçable sans complexifier le schéma.
    type_mime="text/uri-list" sert de marqueur "ceci est un lien" pour
    categorieFichierBiblio côté frontend.

    statut_vectorisation="pret" en dur (29/08, file d'attente de
    vectorisation) : un lien n'est jamais vectorisé, il n'y a donc jamais
    rien à attendre pour celui-ci -- voir core/file_attente_vectorisation.py.
    """
    insertion = supabase.table("fichiers_uploades").insert({
        "niveau": niveau,
        "agent_id": agent_id,
        "user_id": user_id,
        "uploade_par": uploade_par,
        "chemin_stockage": url,
        "url_publique": url,
        "nom_fichier": nom_fichier,
        "type_mime": "text/uri-list",
        "description": description,
        "taille_octets": None,
        "statut_vectorisation": "pret",
        "origine": origine,
    }).execute()
    return insertion.data[0]


def enregistrer_fichier(
    contenu: bytes,
    nom_fichier: str,
    type_mime: str,
    niveau: str,
    uploade_par: str,
    agent_id: str = None,
    user_id: str = None,
    description: str = None,
    origine: str = "bibliotheque",
    statut_vectorisation: str = "pret",
) -> dict:
    """
    Stocke un fichier dans Supabase Storage et l'indexe dans
    fichiers_uploades. `niveau` doit être "plateforme", "agent" ou
    "utilisateur" (voir docstring du module) ; `agent_id`/`user_id` sont
    requis en cohérence avec le niveau (ex. niveau="agent" -> agent_id
    obligatoire) mais ce n'est pas vérifié ici -- c'est à l'appelant
    (route API) de garantir la cohérence selon qui uploade.
    `origine` (2026-08-01, voir migration fichiers_uploades_origine ;
    étendu le 02/09/2026, demande Bourama : onglets d'origine dans la
    bibliothèque perso) : "chat" (pièce jointe de conversation --
    DEPUIS le 02/09/2026 visible dans "Mon espace > Bibliothèque", son
    propre onglet "Uploadé dans un chat" ; ce commentaire disait encore
    "jamais dans Bibliothèque" avant correction du 14/09/2026, resté
    obsolète après le changement -- seule la recherche/liste côté IA
    l'exclut encore par défaut, voir exclut_origine ci-dessous), "publique"
    (copié depuis la bibliothèque publique), "code_partage" (reçu via un
    code de partage), "ia_generee" (généré par l'IA -- document, code,
    image, audio, vidéo, 3D...), ou par défaut "bibliotheque" (ajout
    direct par l'utilisateur, ou note/lien/fichier ajouté par l'IA via
    gerer_document_bibliotheque -- pas une génération, juste un ajout).

    `statut_vectorisation` (29/08/2026, file d'attente de vectorisation
    en arrière-plan -- voir core/file_attente_vectorisation.py) :
    "en_attente" si l'appelant sait que ce fichier doit être vectorisé
    (le worker le prendra en charge juste après), "pret" par défaut pour
    tout ce qui n'a de toute façon jamais été vectorisé (docx, vidéo,
    type inconnu...) -- ne rien mettre en attente pour rien.

    Renvoie la ligne insérée (avec son id et son url_publique).
    """
    extension = nom_fichier.rsplit(".", 1)[-1] if "." in nom_fichier else "bin"

    try:
        chemin_stockage, hash_contenu = stocker_avec_dedoublonnage(supabase, contenu, extension, niveau, type_mime)
    except Exception as e:
        logging.error(f"ERREUR SUPABASE STORAGE (upload bibliothèque, niveau {niveau}) : {e}")
        raise

    url_publique = supabase.storage.from_(BUCKET).get_public_url(chemin_stockage)

    try:
        insertion = supabase.table("fichiers_uploades").insert({
            "niveau": niveau,
            "agent_id": agent_id,
            "user_id": user_id,
            "uploade_par": uploade_par,
            "chemin_stockage": chemin_stockage,
            "hash_contenu": hash_contenu,
            "url_publique": url_publique,
            "nom_fichier": nom_fichier,
            "type_mime": type_mime,
            "description": description,
            "taille_octets": len(contenu),
            "origine": origine,
            "statut_vectorisation": statut_vectorisation,
        }).execute()
    except Exception as e:
        logging.error(f"ERREUR ECRITURE fichiers_uploades ({chemin_stockage}) : {e}")
        # CORRECTIF 16/09/2026 (Bourama : fichiers orphelins dans le
        # Storage sans ligne BDD, decouverts lors d'un depassement de
        # quota Supabase) -- l'upload Storage ci-dessus a reussi mais
        # l'insertion BDD echoue : sans ce rollback, le fichier restait
        # pour toujours dans le bucket "bibliotheque", invisible et
        # inutilisable (rien ne le retrouve jamais, faute de ligne
        # chemin_stockage), mais consommant quand meme le quota de
        # stockage. On supprime le fichier fraichement uploade avant de
        # relancer l'erreur d'origine.
        # 16/09/2026 (suite, dedoublonnage) : passe desormais par
        # supprimer_stockage_si_dernier_usage plutot qu'un remove direct
        # -- avec le dedoublonnage, chemin_stockage peut correspondre a
        # un fichier REUTILISE (deja reference par une autre ligne,
        # potentiellement dans une autre bibliotheque) ; un remove
        # direct casserait alors l'acces de cet autre proprietaire.
        try:
            supprimer_stockage_si_dernier_usage(supabase, chemin_stockage)
        except Exception as e2:
            logging.error(f"ECHEC ROLLBACK STORAGE apres echec BDD ({chemin_stockage}) : {e2}")
        raise

    return insertion.data[0]


def renommer_fichier_par_url(url_publique: str, nouveau_nom: str, user_id: str) -> dict | None:
    """
    Renomme (met à jour la description, utilisée comme nom affiché,
    voir lister_fichiers/chercher_fichiers) un fichier identifié par
    son url_publique -- ajouté le 14/09/2026 (demande Bourama) pour
    core/outils_fichiers_conversation.py : contrairement à
    gerer_document_bibliotheque, le modèle ne connaît JAMAIS le
    `fichier_id` d'une pièce jointe de conversation (jamais montré),
    seulement son url_publique (visible dans le texte juste après
    l'upload) -- donc on retrouve/renomme par url, pas par id.

    Scope STRICT sur user_id (`.eq("user_id", user_id)` en plus de
    l'url) : un utilisateur ne peut jamais renommer le fichier d'un
    autre, même en devinant/hallucinant une url. Renvoie la ligne mise
    à jour, ou None si introuvable ou n'appartenant pas à cet
    utilisateur (pas d'erreur levée dans ce cas, à l'appelant de
    distinguer via la valeur None).
    """
    res = (
        supabase.table("fichiers_uploades")
        .update({"description": nouveau_nom})
        .eq("url_publique", url_publique)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else None


def indexer_fichier_existant(
    url_publique: str,
    chemin_stockage: str,
    nom_fichier: str,
    type_mime: str,
    niveau: str,
    uploade_par: str,
    agent_id: str = None,
    user_id: str = None,
    description: str = None,
    taille_octets: int = None,
) -> dict:
    """
    Indexe dans fichiers_uploades un fichier DÉJÀ stocké ailleurs (ex.
    bucket images-publiques pour les images de chat) -- évite un second
    upload redondant vers le bucket "bibliotheque" quand le fichier
    existe déjà quelque part avec une URL publique utilisable.
    """
    try:
        insertion = supabase.table("fichiers_uploades").insert({
            "niveau": niveau,
            "agent_id": agent_id,
            "user_id": user_id,
            "uploade_par": uploade_par,
            "chemin_stockage": chemin_stockage,
            "url_publique": url_publique,
            "nom_fichier": nom_fichier,
            "type_mime": type_mime,
            "description": description,
            "taille_octets": taille_octets,
        }).execute()
    except Exception as e:
        logging.error(f"ERREUR ECRITURE fichiers_uploades (indexation {chemin_stockage}) : {e}")
        raise

    return insertion.data[0]


def chercher_fichiers(recherche: str, agent_id: str = None, user_id: str = None, limite: int = 10, origine: str = None) -> list:
    """
    Cherche des fichiers accessibles dans le contexte courant (agent_id
    + user_id de la conversation en cours), tous niveaux confondus,
    triés du plus spécifique au plus large : utilisateur -> agent ->
    plateforme. `recherche` filtre sur le nom de fichier ou la
    description (recherche texte simple, pas de recherche sémantique
    pour l'instant).

    Un utilisateur non connecté (user_id=None) ne voit que les niveaux
    agent et plateforme -- pas d'erreur, juste moins de résultats.

    `origine` (14/09/2026, demande Bourama) : optionnel, filtre EXACT
    sur une origine -- utilisé par gerer_fichier_conversation
    (origine="chat") pour ne chercher QUE les pièces jointes de
    conversation, jamais mélangées aux documents de la bibliothèque
    "officielle".
    """
    niveaux_accessibles = ["plateforme"]
    if agent_id:
        niveaux_accessibles.append("agent")
    if user_id:
        niveaux_accessibles.append("utilisateur")

    requete = (
        supabase.table("fichiers_uploades")
        .select("*")
        .in_("niveau", niveaux_accessibles)
        .or_(f"nom_fichier.ilike.%{recherche}%,description.ilike.%{recherche}%")
        .limit(limite)
    )
    if origine:
        requete = requete.eq("origine", origine)

    resultat = requete.execute()

    # Filtre applicatif : "agent" ne doit remonter que les fichiers du
    # bon agent, "utilisateur" que ceux du bon user -- .in_("niveau",...)
    # seul ne suffit pas à scoper correctement, ça ne fait que dire
    # quels NIVEAUX sont autorisés, pas QUEL agent/user précisément.
    fichiers = [
        f for f in resultat.data
        if f["niveau"] == "plateforme"
        or (f["niveau"] == "agent" and f["agent_id"] == agent_id)
        or (f["niveau"] == "utilisateur" and f["user_id"] == user_id)
    ]

    ordre_priorite = {"utilisateur": 0, "agent": 1, "plateforme": 2}
    fichiers.sort(key=lambda f: ordre_priorite[f["niveau"]])
    return fichiers


def lister_fichiers(
    niveau: str,
    agent_id: str = None,
    user_id: str = None,
    origine: str = None,
    exclut_origine: str = None,
    limite: int = None,
    decalage: int = 0,
) -> list | dict:
    """
    Liste des fichiers d'un niveau précis. Historiquement exhaustive
    (pas une recherche par mot-clé) -- utilisée pour l'écran de gestion
    du créateur ("ma bibliothèque pour cet agent") -- ce comportement
    est INCHANGÉ par défaut (`limite=None`, renvoie une simple `list`
    comme avant).

    `limite`/`decalage` (05/09/2026, demande Bourama : l'action "lister"
    de gerer_document_bibliotheque -- voir core/serveur_mcp_generation.py
    -- n'avait, contrairement au catalogue public, AUCUN plafond : un
    fallback censé être rare pouvait renvoyer toute une bibliothèque
    d'un coup) : quand `limite` est fourni, renvoie un `dict`
    {"fichiers": [...], "total": N} au lieu d'une liste brute, pour que
    l'appelant sache s'il reste des pages (pagination par lots de
    `limite`, les plus récents en premier, `decalage` en fichiers déjà
    vus à sauter).
    `origine` (2026-08-01) : optionnel, filtre EXACT sur une origine.
    `exclut_origine` (02/09/2026, demande Bourama : distinguer les
    origines "publique"/"code_partage"/"ia_generee" de l'ancien
    fourre-tout "bibliotheque") : optionnel, exclut une origine au lieu
    d'en filtrer une seule -- utilisé par la vue "Perso" (tout SAUF
    "chat") pour continuer à voir tous ces fichiers ensemble tant que le
    découpage en onglets d'origine n'est pas fait côté frontend.
    """
    requete = supabase.table("fichiers_uploades").select("*", count="exact" if limite else None).eq("niveau", niveau)
    if agent_id:
        requete = requete.eq("agent_id", agent_id)
    if user_id:
        requete = requete.eq("user_id", user_id)
    if origine:
        requete = requete.eq("origine", origine)
    if exclut_origine:
        requete = requete.neq("origine", exclut_origine)
    requete = requete.order("created_at", desc=True)

    if limite is None:
        return requete.execute().data

    reponse = requete.range(decalage, decalage + limite - 1).execute()
    total = reponse.count if reponse.count is not None else None
    return {"fichiers": reponse.data or [], "total": total}


def obtenir_fichier(fichier_id: str) -> dict | None:
    """Un fichier de la bibliothèque perso par son id, SANS filtre
    propriétaire, utilisé par la consultation en lecture seule via
    lien de partage direct (11/09/2026, demande Bourama : chaque fichier
    a désormais son propre lien, ouvert par n'importe quel utilisateur
    connecté, sans que ça l'ajoute chez lui). Ne renvoie que les champs
    nécessaires à l'affichage, jamais user_id/chemin_stockage."""
    res = (
        supabase.table("fichiers_uploades")
        .select("id, nom_fichier, description, type_mime, taille_octets, url_publique")
        .eq("id", fichier_id)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


def obtenir_fichiers_par_ids(fichier_ids: list[str]) -> list[dict]:
    """Plusieurs fichiers par leurs ids, mêmes champs que obtenir_fichier
    ci-dessus, utilisé pour afficher le contenu d'un dossier consulté
    via lien (core/dossiers_bibliotheque.py::obtenir_dossier_consultation)."""
    if not fichier_ids:
        return []
    res = (
        supabase.table("fichiers_uploades")
        .select("id, nom_fichier, description, type_mime, taille_octets, url_publique")
        .in_("id", fichier_ids)
        .execute()
    )
    return res.data or []


def supprimer_fichier(fichier_id: str) -> None:
    """
    Supprime un fichier de la bibliothèque : ligne en base ET objet
    Storage. Ne lève pas d'erreur si l'objet Storage est déjà absent
    (suppression déjà faite ailleurs, ou incohérence mineure) -- seule
    la suppression de la ligne en base est considérée critique.

    16/09/2026 (dedoublonnage) : la ligne BDD est supprimée AVANT de
    toucher au Storage (ordre important -- supprimer_stockage_si_dernier_usage
    vérifie s'il reste une ligne qui référence ce chemin ; si on
    vérifiait avant d'avoir supprimé CETTE ligne, elle se trouverait
    toujours elle-même et ne supprimerait jamais rien).
    """
    ligne = supabase.table("fichiers_uploades").select("chemin_stockage").eq("id", fichier_id).execute()
    if not ligne.data:
        return

    chemin_stockage = ligne.data[0]["chemin_stockage"]
    supabase.table("fichiers_uploades").delete().eq("id", fichier_id).execute()

    try:
        supprimer_stockage_si_dernier_usage(supabase, chemin_stockage)
    except Exception as e:
        logging.warning(f"Suppression Storage bibliothèque échouée ({chemin_stockage}), ligne supprimée quand même : {e}")


def supprimer_fichiers(fichier_ids: list[str]) -> None:
    """
    Même chose que supprimer_fichier, mais pour plusieurs fichiers d'un
    coup : 1 SELECT + suppression Storage + 1 DELETE groupé, au lieu de
    3 appels PAR fichier.

    Ajoutée le 2026-08-27 (bug remonté par Bourama : supprimer un
    dossier importé avec plusieurs dizaines de fichiers échouait avec
    "Failed to fetch" -- l'ancienne boucle appelait supprimer_fichier
    un par un, soit ~3 allers-retours réseau séquentiels par fichier,
    largement de quoi dépasser le timeout de la requête pour un dossier
    de taille réelle). Ne lève pas d'erreur si la suppression Storage
    échoue pour tout ou partie des fichiers, même logique que la
    version unitaire -- seules les lignes en base sont critiques.

    16/09/2026 (dedoublonnage) : lignes BDD supprimées AVANT le Storage
    (même raison que supprimer_fichier), et chaque chemin (dédupliqué)
    vérifié individuellement via supprimer_stockage_si_dernier_usage au
    lieu d'un remove groupé -- un même chemin peut être partagé par
    plusieurs fichiers désormais, un remove aveugle casserait les autres.
    """
    if not fichier_ids:
        return

    lignes = (
        supabase.table("fichiers_uploades")
        .select("chemin_stockage")
        .in_("id", fichier_ids)
        .execute()
    )
    chemins = {l["chemin_stockage"] for l in lignes.data if l.get("chemin_stockage")}

    supabase.table("fichiers_uploades").delete().in_("id", fichier_ids).execute()

    for chemin_stockage in chemins:
        try:
            supprimer_stockage_si_dernier_usage(supabase, chemin_stockage)
        except Exception as e:
            logging.warning(f"Suppression Storage bibliothèque échouée ({chemin_stockage}), ligne supprimée quand même : {e}")
