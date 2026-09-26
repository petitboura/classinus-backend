"""
Outil MCP de changement de mode par Clovis lui-même (25/09/2026, demande
explicite Bourama).

Contexte : jusqu'ici, le mode source (Aucun/Recherche/Sur pieces) et le
mode pedagogique (Socratique/Professeur/Tuteur/Examinateur) etaient
TOUJOURS un choix explicite de l'eleve via le selecteur (bouton ou
raccourci "/", voir SelecteurPersonaPedagogique.tsx) -- jamais l'IA
elle-meme (voir core/mode_source_conversation.py, core/persona_pedagogique_conversation.py,
et REGLE_BASCULE_MODE_PEDAGOGIQUE dans core/profils_agents.py). Cette
regle ne change pas par defaut : ce nouvel outil ouvre deux exceptions
PRECISES, rien de plus.

Expose cote CHAT SEULEMENT (decision explicite Bourama, meme principe que
core/outils_minuteurs.py) : jamais sur le serveur MCP public
(core/serveur_mcp_espace.py).

DEUX CAS AUTORISES, ET SEULEMENT CEUX-LA (voir docstring de l'outil
ci-dessous pour le detail complet donne au modele) :
1. Un code est actif sur la conversation -> Clovis peut changer de mode
   de sa propre initiative, en suivant les consignes ecrites dans un
   skill attache a ce code (raison="consigne_prof").
2. N'importe quel eleve, code actif ou non -> si l'eleve demande lui-meme
   et explicitement de changer de mode dans son message, Clovis peut le
   faire (raison="demande_eleve") -- AVANT ce chantier, meme une demande
   explicite etait refusee.

REGLE DU CHECKBOX ENSEIGNANT (25/09/2026, migration
2026_09_25_codes_eleve_choisit_mode.sql, codes_partage.eleve_choisit_mode,
coche par defaut) : si un code est actif et que ce reglage est decoche
par l'enseignant --
- le selecteur cote eleve est deja cache par le frontend (voir
  SelecteurPersonaPedagogique.tsx / SelecteurModeActif.tsx) ;
- la demande EXPLICITE de l'eleve (raison="demande_eleve") est refusee
  ICI AUSSI par cet outil (l'enseignant garde la main, aucun contournement
  oral possible) ;
- MAIS le changement autonome pilote par le skill (raison="consigne_prof")
  reste toujours autorise -- ce reglage ne restreint QUE l'agentivite de
  l'eleve, jamais celle du skill de l'enseignant (c'est tout l'objet de
  ce reglage : l'enseignant reprend la main, il ne se la retire pas a
  lui-meme).

REGLE ABSOLUE, sans exception, dans les deux cas autorises (voir aussi la
docstring de l'outil) : Clovis ne doit JAMAIS suggerer ni proposer un
changement de mode de lui-meme, meme s'il pense que ce serait utile. Il
agit seulement silencieusement (skill, code actif) ou sur demande
explicite de l'eleve -- il n'en parle jamais de lui-meme.

PRIORITE EN CAS DE CONFLIT (25/09/2026, demande explicite Bourama) : si
un code est actif avec une consigne de skill contraire a ce que demande
l'eleve (ex : skill dit "reste en Socratique", eleve demande "mets-moi en
Tuteur"), la consigne du skill l'emporte -- Clovis refuse poliment la
demande de l'eleve, sans appeler cet outil pour l'honorer.
"""

import logging

from core.mode_source_conversation import (
    MODES_SOURCE_VALIDES,
    obtenir_mode_source as _obtenir_mode_source,
    definir_mode_source as _definir_mode_source,
)
from core.persona_pedagogique_conversation import (
    PERSONAS_VALIDES,
    obtenir_persona_pedagogique as _obtenir_persona_pedagogique,
    definir_persona_pedagogique as _definir_persona_pedagogique,
)
from core.mode_actif_conversation import rattachement_actif_pour_prompt as _rattachement_actif_pour_prompt
from core.avancement_notions_ia import resoudre_code_actif_eleve as _resoudre_code_actif_eleve
from core.outils_generation_commun import mcp_generation, Context

_LABELS_SOURCE = {"recherche": "Recherche", "sur_pieces": "Sur pièces"}
_LABELS_PERSONA = {"socratique": "Socratique", "professeur": "Professeur", "tuteur": "Tuteur", "examinateur": "Examinateur"}


def _libelle_source(v: str | None) -> str:
    return _LABELS_SOURCE.get(v, "Aucun") if v else "Aucun"


def _libelle_persona(v: str | None) -> str:
    return _LABELS_PERSONA.get(v, "Aucun mode") if v else "Aucun mode"


@mcp_generation.tool()
def changer_mode_conversation(
    action: str,
    ctx: Context,
    raison: str = "",
    mode_source: str = "",
    persona_pedagogique: str = "",
) -> str:
    """
    Lit ou change, pour CETTE conversation, le mode source (Aucun /
    Recherche / Sur pièces) et/ou le mode pédagogique (Aucun / Socratique /
    Professeur / Tuteur / Examinateur). Normalement l'élève choisit ces
    deux modes lui-même via son sélecteur -- cet outil t'ouvre deux
    exceptions précises, rien de plus :

    1. Un code (enseignant) est actif sur cette conversation, ET un skill
       attaché à ce code te donne une consigne sur le mode à utiliser
       (ex : "reste toujours en mode Socratique") -> tu peux appliquer
       cette consigne toi-même, de ta propre initiative, silencieusement.
       Utilise `raison="consigne_prof"`.
    2. L'élève te demande LUI-MÊME et EXPLICITEMENT, dans son message, de
       changer de mode (ex : "mets-moi en mode Tuteur", "passe en mode
       source Sur pièces") -> tu peux le faire. Utilise
       `raison="demande_eleve"`.

    En dehors de ces deux cas précis, n'appelle JAMAIS cet outil pour
    changer un mode -- en particulier, ne réinterprète jamais le ton ou le
    contenu d'un message comme une demande implicite de changement, et
    n'agis jamais de ta propre initiative sans code actif.

    RÈGLE ABSOLUE, sans aucune exception : ne suggère et ne propose JAMAIS
    toi-même un changement de mode à l'élève, même si tu penses que ce
    serait utile. Tu agis seulement dans les deux cas ci-dessus, jamais en
    le proposant d'abord.

    PRIORITÉ EN CAS DE CONFLIT : si un skill du code actif donne une
    consigne sur le mode ET que l'élève demande explicitement un mode
    différent, la consigne du skill l'emporte -- explique-lui poliment que
    ce n'est pas modifiable pour ce cours, n'appelle PAS cet outil pour
    honorer sa demande.

    Cet outil peut être refusé (message d'erreur explicite renvoyé) si
    l'enseignant du code actif a désactivé le choix de mode pour l'élève
    -- dans ce cas, explique-le simplement à l'élève, toujours sans
    suggérer d'alternative de ta part.

    `action` :
    - "lire" : renvoie les modes actuellement actifs, aucun paramètre
      supplémentaire requis.
    - "changer" : applique `mode_source` et/ou `persona_pedagogique`
      (au moins un des deux). `raison` est alors OBLIGATOIRE
      ("consigne_prof" ou "demande_eleve").

    `mode_source` (optionnel) : "recherche", "sur_pieces", ou "aucun"
    pour revenir à Aucun. Vide = ne touche pas au mode source.

    `persona_pedagogique` (optionnel) : "socratique", "professeur",
    "tuteur", "examinateur", ou "aucun" pour revenir à Aucun mode. Vide =
    ne touche pas au mode pédagogique.
    """
    user_id = ctx.request_context.request.query_params.get("user_id")
    if not user_id:
        return "Erreur : impossible d'identifier l'élève."
    conversation_id = ctx.request_context.request.query_params.get("conversation_id")
    if not conversation_id:
        return "Erreur : impossible d'identifier la conversation."

    if action == "lire":
        try:
            ms = _obtenir_mode_source(conversation_id, user_id)
            pp = _obtenir_persona_pedagogique(conversation_id, user_id)
        except Exception as e:
            logging.error(f"ERREUR changer_mode_conversation (lire) : {e}")
            return "Erreur : impossible de lire les modes actuels, réessaie."
        return f"Mode source actuel : {_libelle_source(ms)}. Mode pédagogique actuel : {_libelle_persona(pp)}."

    if action != "changer":
        return "Erreur : action inconnue, utilise \"lire\" ou \"changer\"."

    if raison not in ("consigne_prof", "demande_eleve"):
        return "Erreur : `raison` doit être \"consigne_prof\" ou \"demande_eleve\" pour changer un mode."

    mode_source = (mode_source or "").strip().lower()
    persona_pedagogique = (persona_pedagogique or "").strip().lower()
    if not mode_source and not persona_pedagogique:
        return "Erreur : fournis au moins mode_source ou persona_pedagogique."
    if mode_source and mode_source != "aucun" and mode_source not in MODES_SOURCE_VALIDES:
        return "Erreur : mode_source invalide, utilise \"recherche\", \"sur_pieces\" ou \"aucun\"."
    if persona_pedagogique and persona_pedagogique != "aucun" and persona_pedagogique not in PERSONAS_VALIDES:
        return "Erreur : persona_pedagogique invalide, utilise \"socratique\", \"professeur\", \"tuteur\", \"examinateur\" ou \"aucun\"."

    # Réglage enseignant "l'élève peut choisir lui-même" (25/09/2026) : ne
    # restreint QUE raison="demande_eleve", jamais raison="consigne_prof"
    # (voir docstring de ce fichier). rattachement_id_actif=None ou
    # MODE_DESACTIVE -> resoudre_code_actif_eleve renvoie None -> aucune
    # restriction (comportement inchangé sans code actif).
    if raison == "demande_eleve":
        rattachement_id_actif = _rattachement_actif_pour_prompt(conversation_id, user_id)
        code_actif = _resoudre_code_actif_eleve(user_id, rattachement_id_actif)
        if code_actif and code_actif.get("eleve_choisit_mode") is False:
            return (
                "Refusé : l'enseignant de ce code a désactivé le choix du mode pour cette conversation. "
                "Explique-le simplement à l'élève, sans proposer d'alternative de ta part."
            )

    resultats = []
    try:
        if mode_source:
            valeur = None if mode_source == "aucun" else mode_source
            _definir_mode_source(conversation_id, user_id, valeur)
            resultats.append(f"mode source -> {_libelle_source(valeur)}")
        if persona_pedagogique:
            valeur = None if persona_pedagogique == "aucun" else persona_pedagogique
            _definir_persona_pedagogique(conversation_id, user_id, valeur)
            resultats.append(f"mode pédagogique -> {_libelle_persona(valeur)}")
    except Exception as e:
        logging.error(f"ERREUR changer_mode_conversation (changer) : {e}")
        return "Erreur : impossible d'appliquer ce changement, réessaie."

    return "Changement appliqué : " + ", ".join(resultats) + "."
