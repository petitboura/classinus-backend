"""Outil MCP gerer_skill : lecture, création et modification des skills avec dossier et fichiers.

La logique est dans core/skills_actions.py (testable sans serveur MCP).
"""
from core import skills_actions
from core.outils_generation_commun import mcp_generation, Context


@mcp_generation.tool()
def gerer_skill(
    action: str,
    ctx: Context,
    skill_id: str = "",
    nom: str = "",
    description: str = "",
    contenu: str = "",
    chemin: str = "",
    ancien: str = "",
    nouveau: str = "",
    actif: str = "",
    reference: str = "",
) -> str:
    """
    Gère les skills de l'utilisateur (page "Skills" de l'interface) : un skill est un
    dossier avec un fichier SKILL.md obligatoire et d'autres fichiers texte (scripts/,
    references/, assets/). Le SKILL.md commence par un en-tête avec name et description.

    Lecture progressive : le prompt ne donne que le nom et la description de chaque skill.
    Quand une demande correspond à la description d'un skill, lis son SKILL.md AVANT de
    répondre (action "consulter"), puis lis un autre fichier (action "consulter" avec
    `chemin`) seulement si le SKILL.md le demande. Ne devine jamais le contenu d'un skill
    à partir de sa description. Si tu as déjà lu un fichier plus tôt dans la conversation,
    ne le relis pas.

    N'écris, ne modifie et ne supprime JAMAIS sans demande claire et explicite de
    l'utilisateur. Si la demande est vague, demande-lui d'abord ce qu'il veut. Ne montre
    jamais les id à l'utilisateur, ce sont des détails techniques.

    `action` doit être l'une de :
    - "lister" : tous les skills (actifs ou non) avec nom et description. Aucun paramètre.
    - "consulter" : lit un fichier. Paramètres : `skill_id`, et `chemin` (vide : lit le
      SKILL.md et donne la liste des autres fichiers).
    - "creer" : crée un skill. Paramètres : `nom`, `description` (quand l'utiliser, c'est
      ce que lira l'IA pour décider d'ouvrir le skill), `contenu` (le texte du SKILL.md,
      instructions et workflow). L'en-tête est ajouté tout seul. Ensuite, ajoute les autres
      fichiers avec "ecrire_fichier".
    - "modifier_infos" : change le nom, la description ou l'état. Paramètres : `skill_id`
      et au moins un parmi `nom`, `description`, `actif` ("oui" ou "non"). L'en-tête du
      SKILL.md suit tout seul. C'est le SEUL moyen de changer le nom ou la description :
      modifier l'en-tête dans le SKILL.md n'a aucun effet.
    - "ecrire_fichier" : crée un fichier ou remplace entièrement son contenu. Paramètres :
      `skill_id`, `chemin` (par exemple references/guide.md), `contenu`. Uniquement du
      texte : les fichiers non texte ne sont pas pris en charge.
    - "remplacer_texte" : remplace un passage précis d'un fichier, utile pour une petite
      correction dans un long fichier. Paramètres : `skill_id`, `chemin`, `ancien` (texte
      exact, présent une seule fois), `nouveau`.
    - "supprimer_fichier" : supprime un fichier (jamais le SKILL.md). Paramètres :
      `skill_id`, `chemin`. SENSIBLE : demande confirmation avant.
    - "importer_zip" : importe d'un coup TOUS les skills d'un zip joint au chat (un ou
      plusieurs dossiers de skill, zips rangés dans le zip compris), sans rien lire ni
      réécrire. Paramètre : `reference` (la référence du zip donnée dans le sommaire du zip).
      Ne lis pas les fichiers un par un pour recréer les skills : cette action le fait.
    - "exporter_zip" : fabrique un zip téléchargeable, un dossier par skill, comme un skill
      de Claude. Paramètre : `skill_id` (vide : tous les skills de l'utilisateur).
    - "supprimer" : supprime définitivement un skill et tous ses fichiers. Paramètre :
      `skill_id`. SENSIBLE : demande toujours confirmation avant.

    Après une écriture, dis en une phrase ce qui a été fait.
    """
    requete = ctx.request_context.request
    user_id = requete.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'utilisateur."
    return skills_actions.executer(
        user_id, action, skill_id=skill_id, nom=nom, description=description,
        contenu=contenu, chemin=chemin, ancien=ancien, nouveau=nouveau, actif=actif, reference=reference,
    )
