"""
Canal en direct sur PC : etat de l'ecran a jour au debut de chaque tour
(03/10/2026, demande Bourama : l'ecran doit etre envoye en continu des que
Classinus l'a lu une premiere fois, sans que Clovis ait a regarder a chaque
fois).

Constat dans les logs de test : a chaque nouveau message de l'etudiant, le
modele appelait lire_ecran en premier, parce que les resultats d'outils des
tours precedents ne sont pas rejoues et qu'il ne savait donc plus ce que
l'ecran affichait. Ici, si la premiere lecture a deja eu lieu dans la
conversation (voir core/lecture_ecran_continue.py), le backend lit l'ecran
lui-meme avant le tour et l'ajoute au prompt. Le modele peut agir tout de
suite, un aller-retour avec le modele en moins.
"""

import logging

# Debuts de texte renvoyes par lire_ecran quand la lecture n'a pas abouti
# (voir core/outils_action_agent_pc.py). Dans ce cas rien n'est ajoute au
# prompt : le modele garde sa regle habituelle (lire_ecran lui-meme).
_DEBUTS_ECHEC_LECTURE = (
    "Cette action n'a pas pu",
    "Erreur",
    "La lecture de l'écran n'a pas donné",
    "Action NON exécutée",
)


def bloc_etat_ecran_pc(user_id, conversation_id, table_routage) -> str:
    """Texte a ajouter au prompt, ou chaine vide si rien a ajouter."""
    if not user_id or not table_routage or "lire_ecran" not in table_routage:
        return ""
    try:
        from core.lecture_ecran_continue import a_deja_lu
        if not a_deja_lu(user_id, conversation_id):
            return ""
        from core.mcp_tools import appeler_outil
        texte = appeler_outil("lire_ecran", {}, table_routage)
    except Exception as e:
        logging.error(f"Lecture automatique de l'ecran PC impossible : {e}", exc_info=True)
        return ""
    if not texte or not isinstance(texte, str) or texte.startswith(_DEBUTS_ECHEC_LECTURE):
        return ""
    return (
        "\n\n## État actuel de l'écran du PC (lu automatiquement à l'instant)\n"
        "Cette lecture est à jour pour ce message de l'étudiant. N'appelle pas lire_ecran "
        "pour la refaire : agis directement à partir de ce qui suit.\n\n" + texte
    )
