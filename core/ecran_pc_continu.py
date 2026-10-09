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

import concurrent.futures
import logging
import time

# Debuts de texte renvoyes par lire_ecran quand la lecture n'a pas abouti
# (voir core/outils_action_agent_pc.py). Dans ce cas rien n'est ajoute au
# prompt : le modele garde sa regle habituelle (lire_ecran lui-meme).
_DEBUTS_ECHEC_LECTURE = (
    "Cette action n'a pas pu",
    "Erreur",
    "La lecture de l'écran n'a pas donné",
    "Action NON exécutée",
)


# Lecture lancee des l'arrivee du message, en parallele de la preparation du tour
# (04/10/2026, demande Bourama : accelerer la lecture). Avant, le serveur attendait la fin
# de la lecture (plusieurs secondes) AVANT d'appeler le modele, alors que la preparation
# du tour (outils, consignes) prend elle aussi du temps : les deux sont maintenant faites
# en meme temps.
_executeur_lectures = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ecran-pc")


def lancer_lecture_anticipee(user_id, conversation_id, table_routage_complet):
    """Demarre la lecture en arriere-plan. Renvoie un futur a donner a bloc_etat_ecran_pc_anticipe."""
    if not user_id or not table_routage_complet or "lire_ecran" not in table_routage_complet:
        return None
    return _executeur_lectures.submit(bloc_etat_ecran_pc, user_id, conversation_id, table_routage_complet)


def bloc_etat_ecran_pc_anticipe(futur, user_id, conversation_id, table_routage) -> str:
    """Meme resultat que bloc_etat_ecran_pc, en reprenant la lecture deja lancee si elle existe."""
    if futur is None:
        return bloc_etat_ecran_pc(user_id, conversation_id, table_routage)
    if not user_id or not table_routage or "lire_ecran" not in table_routage:
        return ""
    try:
        return futur.result()
    except Exception as e:
        logging.error(f"Lecture anticipee de l'ecran PC impossible : {e}", exc_info=True)
        return ""


def bloc_etat_ecran_pc(user_id, conversation_id, table_routage) -> str:
    """Texte a ajouter au prompt, ou chaine vide si rien a ajouter."""
    if not user_id or not table_routage or "lire_ecran" not in table_routage:
        return ""
    debut = time.monotonic()
    try:
        from core.lecture_ecran_continue import a_deja_lu
        if not a_deja_lu(user_id, conversation_id):
            return ""
        from core.mcp_tools import appeler_outil
        # Lecture decidee par le serveur : signalee dans l'URL (l'IA ne peut pas
        # la modifier) pour que l'application PC ne l'affiche pas comme une
        # action de l'IA.
        route = table_routage["lire_ecran"]
        separateur = "&" if "?" in route["url"] else "?"
        table_auto = {**table_routage, "lire_ecran": {**route, "url": f"{route['url']}{separateur}automatique=1"}}
        texte = appeler_outil("lire_ecran", {}, table_auto)
        logging.info(f"Lecture automatique de l'ecran PC : {time.monotonic() - debut:.1f} s")
    except Exception as e:
        logging.error(f"Lecture automatique de l'ecran PC impossible : {e}", exc_info=True)
        return ""
    if not texte or not isinstance(texte, str) or texte.startswith(_DEBUTS_ECHEC_LECTURE):
        return ""
    return (
        "\n\n## État actuel de l'écran du PC (lu automatiquement à l'instant)\n"
        "Cette lecture est complète et à jour pour ce message de l'étudiant (fenêtre au premier plan et "
        "menus ouverts), et chaque action que tu fais te renvoie l'écran qui suit. N'appelle pas lire_ecran "
        "parce que tu penses que l'écran a changé, ni pour la refaire : agis directement à partir de ce qui suit. Elle ne montre que la "
        "fenêtre au premier plan : pour voir la barre des tâches ou le bureau, appelle "
        "lire_ecran avec zone=\"barre_des_taches\" ou zone=\"bureau\". Sur le PC, n'appelle lire_page que si "
        "l'étudiant te demande explicitement de faire quelque chose dans l'application Classinus : jamais de ta "
        "propre initiative.\n\n" + texte
    )
