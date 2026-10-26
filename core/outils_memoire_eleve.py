"""
Outils MCP de la mémoire utilisateur (chantier 27/09/2026, demande Bourama).
Trois actions séparées plutôt qu'un seul outil à actions :
`memoire_sommaire` doit pouvoir être
appelé très souvent, à moindre coût, sans jamais charger de contenu ,
un seul outil "action" aurait quand même une description unique plus
longue à envoyer à chaque tour.

Décision de Bourama (27/09/2026) : ces outils ne sont PAS exposés sur le
serveur MCP PUBLIC (core/serveur_mcp_espace.py).

Ces outils sont enregistrés comme des outils MCP normaux, donc
découvrables via
demander_outils (catégorie "memoire", voir registre_outils.py). Le
principe "toujours disponible, comme demander_outils" décidé par Bourama
est une décision d'INJECTION dans outils_mcp, câblée séparément dans
core/routage_outils.py (_outils_memoire_toujours_disponibles) et
core/main.py, ne dépend pas de ce fichier. Voir patch-wiring.md pour
le détail exact (l'injection dans outils_mcp seule ne suffit PAS,
l'entrée correspondante dans table_routage est nécessaire aussi, sans
quoi l'appel échoue silencieusement à l'exécution).
"""

import json
import logging

from core.outils_generation_commun import mcp_generation, Context
from core.memoire_eleve import (
    normaliser_nom,
    completer_categorie as _completer_categorie,
    obtenir_sommaire as _obtenir_sommaire,
    formater_sommaire as _formater_sommaire,
    lire_categorie as _lire_categorie,
    ecrire_categorie as _ecrire_categorie,
)


def _user_id(ctx: Context) -> str | None:
    return ctx.request_context.request.query_params.get("user_id")


@mcp_generation.tool()
def memoire_sommaire(ctx: Context) -> str:
    """
    Renvoie la liste des catégories/sous-catégories déjà connues pour CET
    utilisateur, JAMAIS leur contenu, juste de quoi savoir où aller (une
    ligne = une catégorie ou sous-catégorie, sa description en une
    phrase, sa date de dernière mise à jour). C'est toi qui as
    construit cette structure : grandes catégories puis sous-catégories.

    À appeler en début de conversation si le contexte de l'utilisateur peut
    aider à répondre, et systématiquement AVANT d'écrire une nouvelle
    sous-catégorie (pour vérifier qu'une sous-catégorie équivalente
    n'existe pas déjà, ex. ne pas créer "ecole" si "etablissement"
    existe déjà pour cet utilisateur). Une fois la ligne pertinente repérée
    ici, utilise memoire_lire pour son contenu complet, ou memoire_ecrire
    pour la créer/modifier, jamais besoin de relire tout le sommaire à
    chaque fois, seulement quand tu as besoin d'une vue d'ensemble.
    Appelle-le sans jamais l'annoncer à l'utilisateur.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    try:
        lignes = _obtenir_sommaire(user_id)
    except Exception as e:
        logging.error(f"ERREUR outil memoire_sommaire : {e}")
        return "Erreur : impossible de consulter la mémoire, réessaie."

    return _formater_sommaire(lignes)


@mcp_generation.tool()
def memoire_lire(categorie: str, ctx: Context, sous_categorie: str = "") -> str:
    """
    Contenu complet d'UNE catégorie ou sous-catégorie précise de la
    mémoire de CET utilisateur (repérée via memoire_sommaire au préalable).
    `categorie` : le nom exact vu dans memoire_sommaire. `sous_categorie` optionnelle (notation pointée si
    plusieurs niveaux, ex. "maths.derivees") ; laisse vide pour lire
    directement la catégorie racine. Renvoie un JSON, ou un message si
    rien n'est encore noté à cet endroit. Appelle-le sans jamais l'annoncer
    à l'utilisateur.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    if not normaliser_nom(categorie):
        return "Erreur : nom de catégorie manquant ou invalide."
    try:
        ligne = _lire_categorie(user_id, categorie, sous_categorie or None)
    except Exception as e:
        logging.error(f"ERREUR outil memoire_lire ({categorie}/{sous_categorie}) : {e}")
        return "Erreur : impossible de lire cette catégorie, réessaie."
    if not ligne:
        return "Rien noté à cet endroit pour l'instant."
    return json.dumps(ligne["contenu"], ensure_ascii=False)


@mcp_generation.tool()
def memoire_ecrire(categorie: str, contenu_json: str, description: str, ctx: Context, sous_categorie: str = "") -> str:
    """
    Crée ou remplace le contenu d'UNE catégorie ou sous-catégorie précise
    de la mémoire de CET utilisateur, ne touche JAMAIS aux autres
    catégories/sous-catégories déjà notées. À utiliser pour créer une
    fiche entière, la réorganiser ou retirer une information (pour
    ajouter ou modifier un élément dans une fiche existante, préfère
    memoire_completer). Ne note que ce que l'utilisateur a lui-même dit
    ou corrigé, jamais une déduction de ta part, et jamais de numéro de
    pièce d'identité, de carte ou de compte bancaire, ni de token ou de
    clé d'accès.

    `categorie` : libre, tu en crées autant que nécessaire quand rien
    dans memoire_sommaire ne convient. Range par sujet (identite,
    preferences, projets, travail_et_etudes, vie_quotidienne...) avec
    des sous-catégories dedans, plutôt que de multiplier les catégories
    à plat. Les règles de comportement demandées par l'utilisateur vont
    dans preferences, à part des faits. Vérifie via memoire_sommaire
    qu'un équivalent n'existe pas déjà avant d'en créer une.
    `sous_categorie` optionnelle, libre, notation pointée si plusieurs
    niveaux (ex. "projets.startup") ; laisse vide pour écrire directement
    au niveau de la catégorie racine. `contenu_json` : objet JSON avec le
    contenu complet de cette catégorie/sous-catégorie après mise à jour
    (remplace tout ce qui y était noté avant, pas une fusion partielle ,
    relis d'abord avec memoire_lire si tu dois compléter plutôt que
    remplacer). `description` : résumé en une phrase de ce que contient
    désormais cette ligne, affiché ensuite dans memoire_sommaire.
    Appelle-le sans jamais annoncer à l'utilisateur que tu retiens quelque
    chose.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    try:
        contenu = json.loads(contenu_json)
    except Exception:
        return "Erreur : contenu_json doit être un objet JSON valide."
    if not isinstance(contenu, dict):
        return "Erreur : contenu_json doit être un objet JSON (pas une liste ou une valeur simple)."
    if not description.strip():
        return "Erreur : description manquante."

    try:
        succes, erreur = _ecrire_categorie(user_id, categorie, sous_categorie or None, contenu, description.strip())
    except Exception as e:
        logging.error(f"ERREUR outil memoire_ecrire ({categorie}/{sous_categorie}) : {e}")
        return "Erreur : l'écriture en mémoire a échoué, réessaie."
    if not succes:
        return erreur
    chemin = categorie if not sous_categorie else f"{categorie}.{sous_categorie}"
    return f"Mémoire mise à jour ({chemin})."


@mcp_generation.tool()
def memoire_completer(categorie: str, ajouts_json: str, description: str, ctx: Context, sous_categorie: str = "") -> str:
    """
    Ajoute ou modifie seulement quelques éléments dans UNE catégorie ou
    sous-catégorie de la mémoire de CET utilisateur, sans jamais toucher au
    reste de son contenu et sans avoir besoin de le relire. C'est
    l'outil par défaut pour compléter ou mettre à jour une fiche qui
    existe déjà. Les clés nouvelles sont ajoutées, les objets sont
    fusionnés clé par clé, les listes reçoivent les éléments qu'elles
    n'ont pas déjà, une valeur simple déjà notée est remplacée par la
    nouvelle. Pour retirer une information ou réécrire toute la fiche,
    utilise memoire_ecrire à la place.

    `categorie` et `sous_categorie` : comme memoire_ecrire (la catégorie
    est créée si elle n'existe pas). `ajouts_json` : objet JSON avec
    seulement ce qui s'ajoute ou change. `description` : résumé en une
    phrase de tout ce que contient désormais la ligne (pas seulement de
    l'ajout). Appelle-le sans jamais l'annoncer à l'utilisateur.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    try:
        ajouts = json.loads(ajouts_json)
    except Exception:
        return "Erreur : ajouts_json doit être un objet JSON valide."
    if not isinstance(ajouts, dict):
        return "Erreur : ajouts_json doit être un objet JSON (pas une liste ou une valeur simple)."
    if not description.strip():
        return "Erreur : description manquante."
    try:
        succes, erreur = _completer_categorie(user_id, categorie, sous_categorie or None, ajouts, description.strip())
    except Exception as e:
        logging.error(f"ERREUR outil memoire_completer ({categorie}/{sous_categorie}) : {e}")
        return "Erreur : l'écriture en mémoire a échoué, réessaie."
    if not succes:
        return erreur
    chemin = categorie if not sous_categorie else f"{categorie}.{sous_categorie}"
    return f"Mémoire mise à jour ({chemin})."
