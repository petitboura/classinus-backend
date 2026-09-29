"""
Outils MCP de la mémoire élève (chantier 27/09/2026, demande Bourama).
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
    CATEGORIES_MEMOIRE_ELEVE,
    obtenir_sommaire as _obtenir_sommaire,
    lire_categorie as _lire_categorie,
    ecrire_categorie as _ecrire_categorie,
)


def _user_id(ctx: Context) -> str | None:
    return ctx.request_context.request.query_params.get("user_id")


@mcp_generation.tool()
def memoire_sommaire(ctx: Context) -> str:
    """
    Renvoie la liste des catégories/sous-catégories déjà connues pour CET
    élève, JAMAIS leur contenu, juste de quoi savoir où aller (une
    ligne = une catégorie ou sous-catégorie, sa description en une
    phrase, sa date de dernière mise à jour). Les catégories du socle
    (identite, scolarite, apprentissage, preferences) apparaissent même
    vides pour que tu saches où ranger un premier fait sans en inventer
    une nouvelle.

    À appeler en début de conversation si le contexte de l'élève peut
    aider à répondre, et systématiquement AVANT d'écrire une nouvelle
    sous-catégorie (pour vérifier qu'une sous-catégorie équivalente
    n'existe pas déjà, ex. ne pas créer "ecole" si "etablissement"
    existe déjà pour cet élève). Une fois la ligne pertinente repérée
    ici, utilise memoire_lire pour son contenu complet, ou memoire_ecrire
    pour la créer/modifier, jamais besoin de relire tout le sommaire à
    chaque fois, seulement quand tu as besoin d'une vue d'ensemble.
    Appelle-le sans jamais l'annoncer à l'élève.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'élève."
    try:
        lignes = _obtenir_sommaire(user_id)
    except Exception as e:
        logging.error(f"ERREUR outil memoire_sommaire : {e}")
        return "Erreur : impossible de consulter la mémoire, réessaie."

    textes = []
    for l in lignes:
        chemin = l["categorie"] if not l["sous_categorie"] else f"{l['categorie']}.{l['sous_categorie']}"
        if l["description"] is None:
            textes.append(f"{chemin}: (vide)")
        else:
            textes.append(f"{chemin}: {l['description']} (maj: {l['updated_at']})")
    return "\n".join(textes)


@mcp_generation.tool()
def memoire_lire(categorie: str, ctx: Context, sous_categorie: str = "") -> str:
    """
    Contenu complet d'UNE catégorie ou sous-catégorie précise de la
    mémoire de CET élève (repérée via memoire_sommaire au préalable).
    `categorie` doit être l'une de : identite, scolarite, apprentissage,
    preferences. `sous_categorie` optionnelle (notation pointée si
    plusieurs niveaux, ex. "maths.derivees") ; laisse vide pour lire
    directement la catégorie racine. Renvoie un JSON, ou un message si
    rien n'est encore noté à cet endroit. Appelle-le sans jamais l'annoncer
    à l'élève.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'élève."
    if categorie not in CATEGORIES_MEMOIRE_ELEVE:
        return f"Erreur : categorie '{categorie}' invalide. Catégories possibles : {', '.join(CATEGORIES_MEMOIRE_ELEVE)}."
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
    de la mémoire de CET élève, ne touche JAMAIS aux autres
    catégories/sous-catégories déjà notées. À utiliser dès que l'élève
    énonce ou corrige un fait explicite qui mérite d'être retenu d'une
    conversation à l'autre (établissement, niveau, difficulté récurrente,
    préférence...), jamais sur une simple déduction ou un ressenti
    passager.

    `categorie` doit être l'une de : identite, scolarite, apprentissage,
    preferences (vérifie via memoire_sommaire avant d'inventer une
    sous-catégorie qui existe peut-être déjà sous un autre nom).
    `sous_categorie` optionnelle, libre, notation pointée si plusieurs
    niveaux (ex. "maths.derivees") ; laisse vide pour écrire directement
    au niveau de la catégorie racine. `contenu_json` : objet JSON avec le
    contenu complet de cette catégorie/sous-catégorie après mise à jour
    (remplace tout ce qui y était noté avant, pas une fusion partielle ,
    relis d'abord avec memoire_lire si tu dois compléter plutôt que
    remplacer). `description` : résumé en une phrase de ce que contient
    désormais cette ligne, affiché ensuite dans memoire_sommaire.
    Appelle-le sans jamais annoncer à l'élève que tu retiens quelque
    chose.
    """
    user_id = _user_id(ctx)
    if not user_id:
        return "Erreur : impossible d'identifier l'élève."
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
