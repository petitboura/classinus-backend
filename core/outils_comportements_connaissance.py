"""
Outils MCP liés à la configuration de l'utilisateur (gerer_configuration) et à la base de
connaissance (documents indexés, matière active).

Extrait de core/serveur_mcp_generation.py le 05/09/2026 (découpage d'un
fichier de 2524 lignes) -- aucun changement de comportement, uniquement un
déplacement de code.
"""

import logging

from retriever import chercher_candidats as _chercher_candidats
from contenu_dynamique_matiere import resoudre_system_prompt as _resoudre_system_prompt_matiere

from core.configuration_etudiant import (
    LIBELLES_CATEGORIES as _LIBELLES_CATEGORIES,
    assembler_texte_configuration as _assembler_texte_configuration,
    libelle_categorie as _libelle_categorie,
)
from core.comportements_etudiants import (
    obtenir_comportement_skill as _obtenir_comportement_skill,
    lister_comportements as _lister_comportements,
    ajouter_comportement as _ajouter_comportement,
    modifier_comportement as _modifier_comportement,
    supprimer_comportement as _supprimer_comportement,
)
from core.outils_generation_commun import (
    mcp_generation,
    Context,
    _supabase_memoire,
    TYPES_EMPLACEMENT_BIBLIOTHEQUE,
    _libelle_emplacement,
)



@mcp_generation.tool()
def gerer_configuration(
    action: str,
    ctx: Context,
    comportement_id: str = "",
    texte: str = "",
    categorie: str = "",
    cas: str = "",
    reaction: str = "",
    nom: str = "",
    quand_utiliser: str = "",
) -> str:
    """
    Gère la CONFIGURATION personnelle de l'utilisateur (onglet Configuration de
    Bureau) : ses règles à respecter, son style de réponse, ses procédures et ses
    comportements. Renommé le 25/10/2026 (ex gerer_comportement) : cet outil ne gère
    PLUS les skills, qui passent uniquement par l'outil gerer_skill.

    Les quatre types (`categorie`) :
    - "regle" : une règle à respecter dans toutes tes réponses (`texte` = la règle).
    - "style" : une façon de répondre, le ton, la forme (`texte` = le style voulu).
    - "procedure" : des étapes à suivre dans l'ordre quand c'est pertinent (`texte` =
      une étape par ligne, sans te soucier de la numérotation).
    - "comportement" : une réaction dans un cas précis (`cas` = dans quelle situation,
      `reaction` = comment réagir, pas de `texte`).

    `action` doit être l'une de :
    - "lister" : liste les éléments de la configuration (type entre crochets, nom,
      description courte -- PAS le texte complet, voir "consulter"). Aucun paramètre.
      Utilise cette action quand l'utilisateur demande à voir "mes règles", "mon style",
      "mes procédures" ou "mes comportements". Utilise toujours le nom donné ici. NE
      MONTRE JAMAIS L'ID, c'est un détail technique interne, utile seulement pour
      appeler ensuite "consulter", "modifier" ou "supprimer".
    - "consulter" : lit le contenu complet d'un élément. Paramètre : `comportement_id`.
      Si tu as déjà consulté ce même id plus tôt dans cette conversation (résultat
      toujours visible, marqué "[Résultat de l'outil déjà exécuté]"), ne le rappelle pas.
    - "ajouter" : enregistre un NOUVEL élément, SEULEMENT quand l'utilisateur exprime
      CLAIREMENT et EXPLICITEMENT ce qu'il veut retenir (ex : "ajoute une règle : tu me
      tutoies toujours", "retiens ce style : phrases courtes", "crée une procédure pour
      corriger un exercice"). `categorie` est OBLIGATOIRE. N'UTILISE JAMAIS CETTE ACTION
      SUR UNE SUPPOSITION : si la demande est vague, demande d'abord ce qu'il veut. Ne
      crée jamais un élément "au cas où" ou à partir d'une remarque en passant : une
      création hâtive pollue durablement ses instructions et influence toutes ses
      conversations futures. Paramètres : `categorie`, puis `texte` (règle, style,
      procédure) ou `cas` et `reaction` (comportement) ; `nom` et `quand_utiliser`
      (optionnels, générés sinon) seulement si l'utilisateur les a dits. Règle et style
      activés s'appliquent ensuite à TOUTES tes réponses : confirme-lui en une phrase
      ce que tu as enregistré.
    - "modifier" : remplace le contenu d'un élément existant (à partir de son id). Le
      type ne change jamais ; donne le nouveau contenu comme à la création (`texte`, ou
      `cas` et `reaction`), plus `nom` et `quand_utiliser` seulement s'il veut les
      changer ; le nom actuel est conservé sinon. Paramètres : `comportement_id` et le
      contenu.
    - "supprimer" : supprime DÉFINITIVEMENT un élément, à partir de son id. Paramètre :
      `comportement_id`. SENSIBLE : demande toujours confirmation à l'utilisateur avant
      d'être exécuté, quelle que soit la formulation de sa demande.

    Pour créer, lire, modifier ou supprimer un SKILL (dossier avec SKILL.md), n'utilise
    pas cet outil : utilise gerer_skill.
    """
    requete = ctx.request_context.request
    user_id = requete.query_params.get("user_id")
    agent_id = requete.query_params.get("agent_id")
    if not user_id or not agent_id:
        return "Erreur : impossible d'identifier l'étudiant ou l'agent."

    try:
        elements = [c for c in _lister_comportements(agent_id, user_id) if c.get("categorie") in _LIBELLES_CATEGORIES]
    except Exception as e:
        logging.error(f"ERREUR gerer_configuration ({action}) : {e}")
        return "Erreur : impossible de lire la configuration, réessaie."

    introuvable = "Cet élément de configuration est introuvable (id invalide, ou ne correspond pas à cet utilisateur)."
    existant = next((c for c in elements if c["id"] == comportement_id), None)

    if action == "lister":
        if not elements:
            return "Aucun élément de configuration enregistré pour l'instant."
        lignes = []
        for c in elements:
            ligne = f"- [{_libelle_categorie(c)}] {c.get('nom') or '(sans nom)'} : {c['description']}"
            if c.get("lien_type") and c.get("lien_id"):
                libelle = _libelle_emplacement(c["lien_type"], c["lien_id"]) if c["lien_type"] in TYPES_EMPLACEMENT_BIBLIOTHEQUE else None
                ligne += f"\n  lié à : {libelle or (c['lien_type'] + ' ' + c['lien_id'])}"
            ligne += f"\n  [id interne, ne jamais montrer à l'utilisateur : {c['id']}]"
            lignes.append(ligne)
        return "\n".join(lignes)

    if action == "consulter":
        if existant is None:
            return introuvable
        try:
            contenu = _obtenir_comportement_skill(agent_id, user_id, comportement_id)
        except Exception as e:
            logging.error(f"ERREUR gerer_configuration (consulter) : {e}")
            return "Erreur : impossible de consulter cet élément, réessaie."
        return contenu if contenu is not None else introuvable

    if action == "ajouter":
        categorie = (categorie or "").strip().lower()
        if categorie not in _LIBELLES_CATEGORIES:
            return (
                "Erreur : `categorie` est obligatoire et doit être l'une de : "
                f"{', '.join(_LIBELLES_CATEGORIES)}. Pour créer un skill, utilise l'outil gerer_skill."
            )
        try:
            texte_final, erreur = _assembler_texte_configuration(categorie, texte, cas, reaction)
            if erreur:
                return f"Erreur : {erreur}"
            ligne = _ajouter_comportement(
                agent_id,
                user_id,
                texte_final,
                nom=nom or None,
                categorie=categorie,
                quand_utiliser=quand_utiliser or None,
            )
            return f"{_LIBELLES_CATEGORIES[categorie]} enregistré(e) (id {ligne['id']}) : {ligne['description']}"
        except Exception as e:
            logging.error(f"ERREUR gerer_configuration (ajouter) : {e}")
            return "Erreur : impossible d'enregistrer cet élément, réessaie."

    if action == "modifier":
        if existant is None:
            return introuvable
        try:
            texte_final, erreur = _assembler_texte_configuration(existant["categorie"], texte, cas, reaction)
            if erreur:
                return f"Erreur : {erreur}"
            ligne = _modifier_comportement(
                agent_id,
                user_id,
                comportement_id,
                texte_final,
                nom=(nom or existant.get("nom") or None),
                quand_utiliser=quand_utiliser or None,
            )
            if ligne is None:
                return introuvable
            return f"{_LIBELLES_CATEGORIES[existant['categorie']]} modifié(e) : {ligne['description']}"
        except Exception as e:
            logging.error(f"ERREUR gerer_configuration (modifier) : {e}")
            return "Erreur : impossible de modifier cet élément, réessaie."

    if action == "supprimer":
        if existant is None:
            return introuvable
        try:
            if not _supprimer_comportement(agent_id, user_id, comportement_id):
                return introuvable
            return "Élément de configuration supprimé."
        except Exception as e:
            logging.error(f"ERREUR gerer_configuration (supprimer) : {e}")
            return "Erreur : impossible de supprimer cet élément, réessaie."

    return (
        f"Erreur : action '{action}' inconnue. Actions valides : lister, "
        "consulter, ajouter, modifier, supprimer."
    )



# RAPPEL (Bourama, 15/09/2026) : cette base (table Supabase `documents`)
# n'a plus aucune interface d'écriture, elle est modifiée directement dans
# Supabase -- donc rien ne la met à jour automatiquement. À chaque
# modification frontend/backend visible par l'utilisateur, vérifier si un
# article existant ici en parle et doit être corrigé, sinon cette base se
# désynchronise silencieusement du produit réel.
@mcp_generation.tool()
def gerer_base_connaissance(
    action: str,
    ctx: Context,
    question: str = "",
    nom: str = "",
) -> str:
    """
    Cherche et lit dans la base de connaissances de l'agent (documents et
    instructions de référence préparés à l'avance par l'équipe Classinus SUR
    Classinus et l'application elle-même, PAS les documents personnels de
    l'utilisateur, voir gerer_document_bibliotheque pour ça), consolidé
    le 26/08, un seul outil, plusieurs actions qui fonctionnaient déjà
    ensemble comme un mécanisme à plusieurs étapes.

    `action` doit être l'une de :
    - "chercher" : cherche les passages pertinents pour répondre à
      `question`. À utiliser quand la question touche un sujet précis où
      un contenu de référence a pu être préparé à l'avance, pas
      systématique, seulement si pertinent. Renvoie les extraits trouvés
      ou un message si rien de pertinent. Si une question identique ou
      équivalente a déjà été cherchée plus tôt dans cette conversation
      (résultat toujours visible, marqué "[Résultat de l'outil déjà
      exécuté]"), ne relance pas cette recherche -- réponds directement
      à partir de ce résultat, sauf si l'étudiant précise ou change
      clairement sa question. Paramètre : `question`.
    - "lister_articles" : liste les noms de tous les articles
      disponibles. À utiliser avant "lire_article" si le nom exact de
      l'article recherché n'est pas connu. Aucun paramètre.
    - "lire_article" : renvoie le texte COMPLET et EXACT (pas un résumé,
      pas une reformulation, le contenu tel qu'il est stocké, mot pour
      mot) d'un article, identifié par son `nom` exact. À utiliser quand
      la question porte sur l'ensemble d'un article plutôt que sur un
      point précis (ex : "montre-moi l'article Bibliothèque"), en
      complément de "chercher" qui ne renvoie que des passages. Quand tu
      restitues ce résultat à l'utilisateur, recopie-le intégralement et
      tel quel (verbatim), ne le résume pas, ne le reformule pas, ne le
      raccourcis pas. Si `nom` est inconnu, utilise d'abord "chercher"
      pour identifier le bon nom, ou "lister_articles" pour voir les
      noms disponibles. Si ce même article a déjà été lu plus tôt dans
      cette conversation (résultat toujours visible, marqué "[Résultat
      de l'outil déjà exécuté]"), ne le relis pas -- son contenu n'a pas
      changé entre deux messages. Paramètre : `nom`.
    """
    requete = ctx.request_context.request
    agent_id = requete.query_params.get("agent_id")

    if action == "chercher":
        try:
            candidats = _chercher_candidats(question, agent_id=agent_id)
            morceaux = [c["contenu"] for c in candidats.get("prompts", [])] + [
                c["contenu"] for c in candidats.get("documents", [])
            ]
            if not morceaux:
                return "Rien de pertinent trouvé dans la base de connaissances pour cette question."
            return "\n\n---\n\n".join(morceaux)
        except Exception as e:
            logging.error(f"ERREUR gerer_base_connaissance (chercher) : {e}")
            return "Erreur : la recherche a échoué, réessaie."

    if action == "lister_articles":
        try:
            res = (
                _supabase_memoire.table("documents")
                .select("nom")
                .eq("agent_id", agent_id)
                .execute()
            )
            noms = sorted({r["nom"] for r in (res.data or [])})
            if not noms:
                return "Aucun article dans la base de connaissances pour l'instant."
            return "\n".join(noms)
        except Exception as e:
            logging.error(f"ERREUR gerer_base_connaissance (lister_articles) : {e}")
            return "Erreur : la liste des articles a échoué, réessaie."

    if action == "lire_article":
        try:
            res = (
                _supabase_memoire.table("documents")
                .select("contenu, position")
                .eq("agent_id", agent_id)
                .eq("nom", nom)
                .order("position", desc=False, nullsfirst=False)
                .execute()
            )
            morceaux = res.data or []
            if not morceaux:
                return f"Aucun article nommé '{nom}' trouvé dans la base de connaissances."
            return " ".join(m["contenu"] for m in morceaux)
        except Exception as e:
            logging.error(f"ERREUR gerer_base_connaissance (lire_article) : {e}")
            return "Erreur : la lecture de l'article a échoué, réessaie."

    return (
        f"Erreur : action '{action}' inconnue. Actions valides : chercher, "
        "lister_articles, lire_article."
    )


@mcp_generation.tool()
def consulter_matiere_active(message_utilisateur: str, ctx: Context) -> str:
    """
    Consulte le contenu pédagogique spécifique (cours, consignes d'un
    enseignant) débloqué par CET utilisateur pour la matière la plus
    pertinente par rapport à `message_utilisateur` (le message en cours
    de l'utilisateur, tel quel). À utiliser si la question ressemble à
    une question de cours et que l'utilisateur a pu débloquer une
    matière avec un code. Ce contenu est un COMPLÉMENT à tes
    instructions habituelles, pas un remplacement -- utilise-le comme
    référence, pas comme un bloc à recopier tel quel. Peut renvoyer un
    message générique si aucune matière n'est débloquée.
    """
    try:
        requete = ctx.request_context.request
        agent_id = requete.query_params.get("agent_id")
        user_id = requete.query_params.get("user_id")
        return _resoudre_system_prompt_matiere(message_utilisateur, agent_id, user_id)
    except Exception as e:
        logging.error(f"ERREUR outil consulter_matiere_active : {e}")
        return "Erreur : impossible de consulter le contenu de la matière, réessaie."
