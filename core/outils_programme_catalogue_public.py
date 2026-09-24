"""
Outil MCP pour gérer le catalogue public du Programme au nom de
l'utilisateur -- 22/09/2026, demande Bourama : même genre de catalogue
public que la bibliothèque et les skills, transposé au Programme (voir
core/programme_catalogue_public.py pour toute la logique métier, ce
fichier n'est qu'un fin wrapper MCP).

UN SEUL outil avec plusieurs actions internes (convention Bourama pour
ce genre de fonctionnalité, voir gerer_entree_catalogue_public et
gerer_comportement_public), plutôt que plusieurs outils séparés.

Noter (étoile) et commenter une entrée de type "programme" passent par
les outils génériques déjà existants (basculer_etoile_catalogue_public,
ajouter_commentaire_catalogue_public) -- pas dupliqués ici.
"""

import logging

from core.outils_generation_commun import mcp_generation, Context
from core.programme_catalogue_public import (
    publier_programme_public as _publier_programme_public,
    modifier_programme_public as _modifier_programme_public,
    supprimer_programme_public as _supprimer_programme_public,
    lire_programme_public as _lire_programme_public,
    lister_programmes_catalogue_public as _lister_programmes_catalogue_public,
    chercher_programmes_catalogue_public as _chercher_programmes_catalogue_public,
    copier_programme_vers_perso as _copier_programme_vers_perso,
)


@mcp_generation.tool()
def gerer_programme_catalogue_public(
    action: str,
    ctx: Context,
    entree_id: str = "",
    code_id: str = "",
    nom: str = "",
    description: str = "",
    inclure_regles_consignes: bool = False,
    question: str = "",
    nombre: int = 5,
    pays: str = "",
    niveau: str = "",
    categorie: str = "",
    classe: str = "",
    specialite: str = "",
) -> str:
    """
    Gère le CATALOGUE PUBLIC DU PROGRAMME (une copie figée d'un
    Programme entier -- arborescence de notions -- que d'autres profs
    peuvent trouver et récupérer). Pour le Programme PERSONNEL d'un
    prof (jamais publié), voir gerer_avancement_notions /
    verifier_consignes_code_actif, pas cet outil.

    `action` doit être l'une de :
    - "publier" : publie le Programme ENTIER d'un code dans le
      catalogue public (jamais une branche partielle). Paramètres :
      `code_id` (obligatoire, doit appartenir à l'utilisateur), `nom`
      (obligatoire), `description` optionnelle, `inclure_regles_consignes`
      (inclut ou non les règles de comportement et consignes IA de
      chaque notion dans la copie publiée, décidé par le publieur),
      `pays`/`niveau`/`categorie`/`classe`/`specialite` optionnels (à
      ne remplir que si le prof les mentionne clairement).
    - "modifier" : modifie le nom, la description et/ou les filtres
      d'une entrée déjà publiée. Réservé au contributeur d'origine.
      Paramètre : `entree_id` ; `nom`, `description`, `pays`, `niveau`,
      `categorie`, `classe`, `specialite` tous optionnels -- seuls ceux
      fournis sont changés.
    - "supprimer" : supprime DÉFINITIVEMENT une entrée du catalogue
      public. Réservé au contributeur d'origine. Paramètre :
      `entree_id`. SENSIBLE : demande toujours confirmation avant
      d'être exécuté.
    - "lire" : affiche le contenu (structure de notions) d'une entrée
      publiée, pour que le prof puisse la consulter avant de la
      récupérer. Paramètre : `entree_id`.
    - "lister" : liste les entrées les plus récentes du catalogue,
      pour une demande vague ("qu'est-ce qu'il y a comme programmes
      publics ?"). Paramètres optionnels : `nombre` (défaut 5, max 15),
      `pays`/`niveau`/`categorie`/`classe`/`specialite`.
    - "chercher" : recherche par mot clé (nom + description) dans le
      catalogue. Paramètres : `question` (obligatoire), `nombre`
      (défaut 5, max 20), mêmes filtres optionnels que "lister".
    - "copier_vers_perso" : récupère une entrée déjà publiée (n'importe
      laquelle, pas seulement les siennes) vers l'espace personnel de
      cet utilisateur, comme un nouveau Programme. Paramètre :
      `entree_id` ; puis SOIT `code_id` (un de ses codes existants,
      remplace le Programme de ce code) SOIT rien (crée un nouveau code
      portant le nom de l'entrée, sauf si `nom` est fourni) --
      toujours demander au prof lequel il préfère s'il ne l'a pas
      précisé. `inclure_regles_consignes` : reprend ou non les règles
      et consignes dans SA copie (uniquement possible si le publieur
      les avait lui-même incluses).

    Pour noter (étoile) ou commenter une entrée déjà publiée, utilise
    basculer_etoile_catalogue_public / ajouter_commentaire_catalogue_public
    avec type_element="programme".
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : utilisateur non authentifié."

    if action == "publier":
        if not (code_id or "").strip():
            return "Erreur : code_id manquant."
        resultat = _publier_programme_public(
            code_id.strip(), user_id, nom, description, inclure_regles_consignes,
            pays, niveau, categorie, classe, specialite,
        )
        if resultat == "CODE_INTROUVABLE":
            return "Erreur : ce code n'existe pas ou ne t'appartient pas."
        if resultat == "NOM_REQUIS":
            return "Erreur : un nom est requis pour publier."
        if resultat == "PROGRAMME_VIDE":
            return "Erreur : ce Programme est vide, rien à publier."
        return f"Programme publié dans le catalogue public [id: {resultat['id']}]."

    if action == "modifier":
        if not (entree_id or "").strip():
            return "Erreur : entree_id manquant."
        erreur = _modifier_programme_public(
            entree_id, user_id,
            nom=nom.strip() or None if nom else None,
            description=description.strip() or None if description else None,
            pays=pays.strip() or None if pays else None,
            niveau=niveau.strip() or None if niveau else None,
            categorie=categorie.strip() or None if categorie else None,
            classe=classe.strip() or None if classe else None,
            specialite=specialite.strip() or None if specialite else None,
        )
        if erreur == "ENTREE_INTROUVABLE":
            return "Cette entrée du catalogue public est introuvable."
        if erreur == "CETTE_ENTREE_NE_T_APPARTIENT_PAS":
            return "Erreur : tu ne peux modifier que les Programmes que tu as toi-même publiés."
        if erreur == "NOM_REQUIS":
            return "Erreur : le nom ne peut pas être vidé."
        if erreur == "AUCUNE_MODIFICATION_FOURNIE":
            return "Erreur : indique au moins une chose à modifier."
        return "Entrée du catalogue public modifiée."

    if action == "supprimer":
        if not (entree_id or "").strip():
            return "Erreur : entree_id manquant."
        if not _supprimer_programme_public(entree_id, user_id):
            return "Erreur : cette entrée est introuvable, ou tu n'en es pas l'auteur."
        return "Programme supprimé du catalogue public."

    if action == "lire":
        if not (entree_id or "").strip():
            return "Erreur : entree_id manquant."
        entree = _lire_programme_public(entree_id)
        if not entree:
            return "Cette entrée du catalogue public est introuvable."
        lignes = "\n".join(f"- {n['nom']}" for n in entree["notions"])
        return (
            f"« {entree['nom']} »\n{entree.get('description') or ''}\n\n"
            f"Contient les règles/consignes : {'oui' if entree['inclut_regles_consignes'] else 'non'}\n"
            f"Étoiles : {entree['etoiles_count']}\n\nNotions :\n{lignes}"
        )

    if action == "lister":
        resultat = _lister_programmes_catalogue_public(
            limite=nombre or 5, pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
        )
        if not resultat["programmes"]:
            return "Aucun Programme public trouvé."
        lignes = "\n".join(f"- {p['nom']} [id: {p['id']}]" for p in resultat["programmes"])
        return f"{len(resultat['programmes'])} Programme(s) sur {resultat['total']} au total :\n{lignes}"

    if action == "chercher":
        if not (question or "").strip():
            return "Erreur : question manquante."
        resultats = _chercher_programmes_catalogue_public(
            question, match_count=nombre or 5, pays=pays, niveau=niveau, categorie=categorie, classe=classe, specialite=specialite,
        )
        if not resultats:
            return "Aucun Programme public ne correspond à cette recherche."
        lignes = "\n".join(f"- {p['nom']} [id: {p['id']}]" for p in resultats)
        return f"Programmes trouvés :\n{lignes}"

    if action == "copier_vers_perso":
        if not (entree_id or "").strip():
            return "Erreur : entree_id manquant."
        try:
            resultat = _copier_programme_vers_perso(
                entree_id, user_id, code_id=(code_id or "").strip() or None,
                nouveau_code_nom=nom or None, inclure_regles_consignes=inclure_regles_consignes,
            )
        except Exception as e:
            logging.error(f"ERREUR gerer_programme_catalogue_public (copier_vers_perso) : {e}")
            return "Erreur : impossible de copier ce Programme, réessaie."
        if resultat == "ENTREE_INTROUVABLE":
            return "Cette entrée du catalogue public est introuvable."
        if resultat == "CODE_INTROUVABLE":
            return "Erreur : ce code n'existe pas ou ne t'appartient pas."
        if resultat == "PROGRAMME_VIDE":
            return "Erreur : ce Programme public est vide."
        return f"Programme copié ({resultat['nb_notions']} notion(s)) vers le code [id: {resultat['code_id']}]."

    return (
        f"Erreur : action '{action}' inconnue. Actions valides : publier, modifier, supprimer, "
        "lire, lister, chercher, copier_vers_perso."
    )
