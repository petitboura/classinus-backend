"""
Questions posées à l'utilisateur pendant que Classinus travaille (chat normal).

Chantier "messages et questions pendant que Classinus travaille" (25/11/2026,
demande de Bourama). Un seul outil, `poser_question`, avec un réglage
"bloquante" oui ou non :

- non bloquante : l'outil rend la main tout de suite, la tâche continue, la
  réponse arrive plus tard dans la file de messages du tour (la même que celle
  du canal en direct, voir core/canal_agent_applicatif.py) ;
- bloquante : l'appel reste en attente de la réponse DANS LE MÊME TOUR, sans
  que Classinus s'arrête pour écrire sa question dans un message.

Ce module est volontairement léger (aucun import de serveur MCP) : il est lu à
la fois par l'outil (core/outils_question.py), par l'exécution des outils
(core/execution_outils.py) et par l'appel MCP (core/mcp_tools.py), qui ne
doivent pas se retrouver en import circulaire.
"""

import json
import logging
import os

NOM_OUTIL_QUESTION = "poser_question"

# Réglage du délai d'attente d'une question bloquante, en secondes : ligne de la
# table Supabase parametres_outils (même table que le budget d'appels d'outils,
# voir core/mcp_tools.py::parametres_outils). Valeur de départ : 10 minutes.
CLE_DELAI_QUESTION = "delai_reponse_question_secondes"
DELAI_QUESTION_DEFAUT_SECONDES = 600
DELAI_QUESTION_MIN_SECONDES = 30
# Railway coupe une requête HTTP au bout de 15 minutes (900 s) : le flux du chat
# doit rester sous cette limite. Réglable par variable d'environnement si Railway
# change sa limite, sans toucher au code.
try:
    DELAI_QUESTION_MAX_SECONDES = int(os.getenv("QUESTION_DELAI_MAX_SECONDES", "840"))
except ValueError:
    DELAI_QUESTION_MAX_SECONDES = 840
if DELAI_QUESTION_MAX_SECONDES < DELAI_QUESTION_MIN_SECONDES:
    DELAI_QUESTION_MAX_SECONDES = 840
# Ajoutée au délai de l'appel MCP pour que l'outil rende lui-même "pas de réponse"
# avant que l'appel ne soit coupé par le délai général des outils.
MARGE_APPEL_QUESTION_SECONDES = 20

LONGUEUR_MAX_REPONSE_QUESTION = 4000
TYPES_AVEC_CHOIX = ("choix_unique", "choix_multiple")


def est_bloquante(valeur) -> bool:
    """Lit le réglage "bloquante" tel que le modèle l'a envoyé (booléen ou texte)."""
    if isinstance(valeur, bool):
        return valeur
    return isinstance(valeur, str) and valeur.strip().lower() == "true"


def delai_question_secondes() -> int:
    """Délai d'attente d'une question bloquante, borné entre le minimum et le maximum."""
    from core.mcp_tools import parametres_outils

    try:
        valeur = int(parametres_outils().get(CLE_DELAI_QUESTION, DELAI_QUESTION_DEFAUT_SECONDES))
    except (TypeError, ValueError):
        logging.error(f"Réglage '{CLE_DELAI_QUESTION}' illisible, valeur de départ utilisée.")
        valeur = DELAI_QUESTION_DEFAUT_SECONDES
    return max(DELAI_QUESTION_MIN_SECONDES, min(valeur, DELAI_QUESTION_MAX_SECONDES))


def lire_question(brut):
    """
    Question envoyée par le modèle (texte JSON ou dictionnaire), ramenée à un
    dictionnaire prêt pour la carte du chat, ou None si elle est inutilisable.

    Même schéma que le bloc ```question``` du chat (voir la consigne des
    questions dans core/profils_agents.py). Sur les choix, "Autre" est ajouté
    par défaut (décision de Bourama) : seul un `autre: false` explicite le retire.
    """
    if isinstance(brut, str):
        try:
            brut = json.loads(brut)
        except ValueError:
            return None
    if not isinstance(brut, dict):
        return None
    type_question = brut.get("type")
    if not isinstance(type_question, str) or not type_question.strip():
        return None
    if type_question == "multi_champs":
        if not isinstance(brut.get("champs"), list) or not brut["champs"]:
            return None
    elif not isinstance(brut.get("question"), str) or not brut["question"].strip():
        return None
    question = dict(brut)
    if type_question in TYPES_AVEC_CHOIX and "autre" not in question:
        question["autre"] = True
    return question


def evenement_question_depuis_appel(appel):
    """
    Événement de flux "question_en_direct" pour un appel de poser_question, émis
    par core/execution_outils.py AVANT que l'outil ne commence à attendre : la
    carte s'affiche ainsi tout de suite. L'identifiant de la question est celui de
    l'appel d'outil, que le frontend connaît déjà. None si la question est
    inutilisable (l'outil renverra alors lui-même l'erreur au modèle).
    """
    try:
        arguments = json.loads(appel.get("arguments") or "{}")
    except ValueError:
        return None
    if not isinstance(arguments, dict):
        return None
    question = lire_question(arguments.get("question"))
    if question is None:
        return None
    return {
        "type": "question_en_direct",
        "id_question": appel["id"],
        "id_appel": appel["id"],
        "bloquante": est_bloquante(arguments.get("bloquante")),
        "question": question,
    }
