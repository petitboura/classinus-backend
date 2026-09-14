"""
Outils MCP de la Partie 3 du chantier "confiance pedagogique" (voir
clovis-plan-travail-10-parties.md) : mise a jour de l'avancement des
notions (Partie 1) en langage naturel, et consultation de l'avancement/
regle de comportement au moment de repondre a un eleve.

Deux outils distincts (jamais un seul) : le prof et l'eleve n'ont pas le
meme role vis-a-vis de cette donnee (le prof ecrit, l'eleve declenche
juste une lecture en coulisse), meme principe de separation que les
autres paires lecture/ecriture deja en place dans ce registre.
"""

import logging

from core.avancement_notions_ia import (
    resoudre_code_par_nom,
    trouver_notion_par_nom,
    mettre_a_jour_ou_creer_avancement,
    definir_regle_comportement,
    definir_consigne_llm,
    renommer_notion_par_nom,
    deplacer_notion_par_nom,
    fusionner_notions_par_nom,
    supprimer_notion_par_nom,
    formatter_arborescence,
    toutes_notions_code,
)
from core.codes_partage import lister_mes_codes as _lister_mes_codes

from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def gerer_avancement_notions(
    action: str,
    ctx: Context,
    code_id: str = "",
    code_nom: str = "",
    nom_notion: str = "",
    notion_parent_nom: str = "",
    statut: str = "",
    regle: str = "",
    consigne: str = "",
    nouveau_nom: str = "",
    direction: str = "",
    nom_notion_cible: str = "",
) -> str:
    """
    Gère l'avancement du programme (structure de notions de la Partie 1)
    en langage naturel, pour le prof/propriétaire d'un code (voir "Mes
    codes") -- Point 1 du document de vision, briques B et C.

    Utilise cet outil dès que l'utilisateur (le propriétaire d'un code,
    pas un élève rattaché) dit dans le chat ce qui a été vu en classe
    ("on a fini les dérivées", "on attaque le chapitre sur les suites"),
    ou veut régler le comportement de l'IA face à une notion pas encore
    vue. NE DEVINE JAMAIS quel code cibler si l'utilisateur en possède
    plusieurs et n'a pas précisé lequel -- utilise "lister_mes_codes"
    pour lui demander de préciser plutôt que de choisir au hasard.

    `action` doit être l'une de :
    - "lister_mes_codes" : liste les codes (id, nom, code) de
      l'utilisateur. Utilise cette action pour retrouver `code_id` à
      partir d'un nom cité par l'utilisateur, ou dès qu'il possède
      plusieurs codes et n'a pas précisé lequel. Aucun paramètre.
    - "lister_notions" : affiche l'arborescence complète des notions
      d'un code (nom, statut, règle de comportement si définie),
      indentée par profondeur. Utilise cette action avant de mettre à
      jour un statut si tu n'es pas sûr qu'une notion existe déjà sous
      un nom précis, pour éviter d'en créer un doublon proche. Paramètre :
      `code_id` (ou `code_nom`, résolu automatiquement si non ambigu).
    - "mettre_a_jour_statut" : change le statut d'une notion
      ("a_venir", "en_cours", ou "acquis"), et la CRÉE automatiquement
      si elle n'existe pas encore sous ce nom exact dans ce code (pas
      besoin de la créer séparément d'abord). Si tu la crées et que
      l'utilisateur a mentionné un chapitre/une notion parente, passe
      `notion_parent_nom` pour la rattacher au bon endroit -- sinon
      elle est créée à la racine. Paramètres : `code_id` (ou
      `code_nom`), `nom_notion`, `statut`, `notion_parent_nom` (optionnel).
    - "definir_regle_comportement" : définit ce que doit faire l'IA
      face à une question qui toucherait cette notion si elle n'est pas
      encore vue par l'élève : "bloquer" (ne pas du tout aider sur
      cette notion), "contourner" (aider mais rester dans les notions
      déjà vues, sans utiliser celle-ci), ou "signaler" (aider
      normalement mais signaler à l'élève que ce n'est pas encore vu en
      classe). Rattachable à n'importe quel niveau de l'arborescence :
      une règle posée sur une notion "chapitre" s'applique à toutes ses
      sous-notions qui n'ont pas leur propre règle plus précise.
      Contrairement à "mettre_a_jour_statut", la notion doit DÉJÀ
      exister (une règle ne crée jamais de notion). Passe `regle` vide
      pour retirer une règle déjà posée à ce niveau précis. Paramètres :
      `code_id` (ou `code_nom`), `nom_notion`, `regle`.
    - "definir_consigne_llm" : définit (texte libre, pas une liste
      fermée comme `regle`) une consigne spécifique que tu dois
      respecter dès que cette notion (ou une de ses sous-notions, sauf
      si elle a sa propre consigne plus précise) revient dans une
      conversation -- coexiste avec `regle` (une notion peut avoir les
      deux en même temps), et s'applique quel que soit son statut
      (contrairement à `regle`, qui ne concerne que les notions pas
      encore vues). Rattachable à n'importe quel niveau de
      l'arborescence, même logique d'héritage que `regle`. La notion
      doit DÉJÀ exister. Passe `consigne` vide pour la retirer.
      Paramètres : `code_id` (ou `code_nom`), `nom_notion`, `consigne`.
    - "renommer_notion" : renomme une notion EXISTANTE. La notion doit
      DÉJÀ exister. Paramètres : `code_id` (ou `code_nom`), `nom_notion`
      (nom actuel), `nouveau_nom`.
    - "deplacer_notion" : déplace une notion d'un cran parmi ses
      frères/sœurs (même parent), vers le haut ou le bas de la liste --
      jamais de repositionnement arbitraire à une position précise,
      seulement un cran à la fois (comme les flèches monter/descendre
      côté interface). Paramètres : `code_id` (ou `code_nom`),
      `nom_notion`, `direction` ("monter" ou "descendre").
    - "fusionner_notions" : fusionne une notion source dans une notion
      cible -- les sous-notions de la source sont rattachées à la
      cible, puis la source est supprimée (nom/statut de la cible
      conservés). IRRÉVERSIBLE : demande TOUJOURS confirmation
      explicite à l'utilisateur avant d'appeler cette action, en lui
      rappelant ce que ça va faire. Les deux notions doivent DÉJÀ
      exister. Paramètres : `code_id` (ou `code_nom`), `nom_notion`
      (source), `nom_notion_cible`.
    - "supprimer_notion" : supprime une notion ET tous ses descendants
      (chapitres/parties/notions en dessous, cascade complète).
      IRRÉVERSIBLE : demande TOUJOURS confirmation explicite à
      l'utilisateur avant d'appeler cette action, en lui rappelant que
      tout ce qui est en dessous sera aussi supprimé. Paramètres :
      `code_id` (ou `code_nom`), `nom_notion`.
    """
    utilisateur_id = ctx.request_context.request.query_params.get("user_id")
    if not utilisateur_id:
        return "Erreur : impossible d'identifier l'utilisateur."

    if action == "lister_mes_codes":
        try:
            codes = _lister_mes_codes(utilisateur_id)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (lister_mes_codes) : {e}")
            return "Erreur : impossible de lister les codes, réessaie."
        if not codes:
            return "Aucun code créé pour l'instant."
        return "\n".join(f"- {c.get('nom') or c['code']} (code: {c['code']}, id: {c['id']})" for c in codes)

    code_cible_id = code_id
    if not code_cible_id and code_nom:
        code = resoudre_code_par_nom(utilisateur_id, code_nom)
        if code is None:
            return (
                f"Impossible de retrouver un unique code nommé \"{code_nom}\". "
                "Utilise l'action \"lister_mes_codes\" pour voir les codes disponibles "
                "et préciser lequel."
            )
        code_cible_id = code["id"]
    if not code_cible_id:
        return "Erreur : précise `code_id` ou `code_nom` (utilise \"lister_mes_codes\" si besoin)."

    if action == "lister_notions":
        try:
            notions = toutes_notions_code(code_cible_id)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (lister_notions) : {e}")
            return "Erreur : impossible de lister les notions, réessaie."
        return formatter_arborescence(notions)

    if action == "mettre_a_jour_statut":
        if not nom_notion or not statut:
            return "Erreur : `nom_notion` et `statut` sont requis pour cette action."
        try:
            resultat = mettre_a_jour_ou_creer_avancement(
                utilisateur_id, code_cible_id, nom_notion, statut, notion_parent_nom or None
            )
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (mettre_a_jour_statut) : {e}")
            return "Erreur : impossible de mettre à jour cette notion, réessaie."
        if resultat is None:
            return (
                "Impossible de mettre à jour cette notion : statut invalide (utilise "
                "\"a_venir\", \"en_cours\" ou \"acquis\"), code introuvable, ou notion "
                "parente introuvable/ambiguë."
            )
        return f"Notion \"{resultat['nom']}\" mise à jour : statut \"{resultat['statut']}\"."

    if action == "definir_regle_comportement":
        if not nom_notion:
            return "Erreur : `nom_notion` est requis pour cette action."
        try:
            resultat = definir_regle_comportement(
                utilisateur_id, code_cible_id, nom_notion, regle or None
            )
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (definir_regle_comportement) : {e}")
            return "Erreur : impossible de définir cette règle, réessaie."
        if resultat is None:
            return (
                "Impossible de définir cette règle : notion introuvable/ambiguë dans ce "
                "code, ou règle invalide (utilise \"bloquer\", \"contourner\", \"signaler\", "
                "ou laisse vide pour retirer la règle)."
            )
        if resultat.get("regle_comportement"):
            return f"Règle sur \"{resultat['nom']}\" : \"{resultat['regle_comportement']}\"."
        return f"Règle retirée sur \"{resultat['nom']}\"."

    if action == "definir_consigne_llm":
        if not nom_notion:
            return "Erreur : `nom_notion` est requis pour cette action."
        try:
            resultat = definir_consigne_llm(
                utilisateur_id, code_cible_id, nom_notion, consigne or None
            )
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (definir_consigne_llm) : {e}")
            return "Erreur : impossible de définir cette consigne, réessaie."
        if resultat is None:
            return "Impossible de définir cette consigne : notion introuvable/ambiguë dans ce code."
        if resultat.get("consigne_llm"):
            return f"Consigne sur \"{resultat['nom']}\" : \"{resultat['consigne_llm']}\"."
        return f"Consigne retirée sur \"{resultat['nom']}\"."

    if action == "renommer_notion":
        if not nom_notion or not nouveau_nom:
            return "Erreur : `nom_notion` et `nouveau_nom` sont requis pour cette action."
        try:
            resultat = renommer_notion_par_nom(utilisateur_id, code_cible_id, nom_notion, nouveau_nom)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (renommer_notion) : {e}")
            return "Erreur : impossible de renommer cette notion, réessaie."
        if resultat is None:
            return "Impossible de renommer cette notion : introuvable/ambiguë dans ce code, ou nouveau nom vide."
        return f"Notion renommée en \"{resultat['nom']}\"."

    if action == "deplacer_notion":
        if not nom_notion or direction not in ("monter", "descendre"):
            return "Erreur : `nom_notion` requis, et `direction` doit être \"monter\" ou \"descendre\"."
        try:
            resultat = deplacer_notion_par_nom(utilisateur_id, code_cible_id, nom_notion, direction)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (deplacer_notion) : {e}")
            return "Erreur : impossible de déplacer cette notion, réessaie."
        if resultat is None:
            return (
                f"Impossible de déplacer \"{nom_notion}\" : notion introuvable/ambiguë, ou déjà en "
                "première/dernière position parmi ses frères/sœurs."
            )
        return f"Notion \"{resultat['nom']}\" déplacée ({direction})."

    if action == "fusionner_notions":
        if not nom_notion or not nom_notion_cible:
            return "Erreur : `nom_notion` (source) et `nom_notion_cible` sont requis pour cette action."
        try:
            resultat = fusionner_notions_par_nom(utilisateur_id, code_cible_id, nom_notion, nom_notion_cible)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (fusionner_notions) : {e}")
            return "Erreur : impossible de fusionner ces notions, réessaie."
        if resultat is None:
            return (
                f"Impossible de fusionner \"{nom_notion}\" dans \"{nom_notion_cible}\" : une des deux "
                "notions est introuvable/ambiguë, source et cible identiques, ou cible descendante de source."
            )
        return f"\"{nom_notion}\" fusionnée dans \"{resultat['nom']}\"."

    if action == "supprimer_notion":
        if not nom_notion:
            return "Erreur : `nom_notion` est requis pour cette action."
        try:
            resultat = supprimer_notion_par_nom(utilisateur_id, code_cible_id, nom_notion)
        except Exception as e:
            logging.error(f"ERREUR gerer_avancement_notions (supprimer_notion) : {e}")
            return "Erreur : impossible de supprimer cette notion, réessaie."
        if resultat is None:
            return f"Impossible de supprimer \"{nom_notion}\" : introuvable/ambiguë dans ce code."
        return f"\"{resultat['nom']}\" supprimée (avec tout ce qui était en dessous)."

    return (
        f"Erreur : action '{action}' inconnue. Actions valides : lister_mes_codes, "
        "lister_notions, mettre_a_jour_statut, definir_regle_comportement, "
        "definir_consigne_llm, renommer_notion, deplacer_notion, fusionner_notions, "
        "supprimer_notion."
    )

# consulter_avancement_notion (09/09/2026) retirée le 12/09/2026 :
# absorbée dans core/outils_verification_code_actif.py::
# verifier_consignes_code_actif (action="programme"), demande explicite
# Bourama d'un seul outil avec plusieurs actions plutôt que plusieurs
# outils de vérification séparés.

