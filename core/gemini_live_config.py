"""Réglages de la voix en direct (Gemini Live) de Classinus.

Tout ce qui peut changer sans toucher au code vit ici : le modèle vocal,
l'adresse de connexion, les consignes données à la voix, la phrase d'accueil
et la description de l'outil qui relie la voix à Classinus. Chaque valeur peut
être remplacée par une variable d'environnement (Railway), sans redéploiement
de code :

- GEMINI_LIVE_MODELE
- GEMINI_LIVE_URL
- GEMINI_LIVE_CONSIGNES
- GEMINI_LIVE_ACCUEIL (vide pour supprimer la phrase d'accueil)
- GEMINI_LIVE_DESCRIPTION_OUTIL
- GEMINI_LIVE_RELANCE_ATTENTE (vide pour supprimer les nouvelles pendant l'attente)
- GEMINI_LIVE_DELAI_RELANCE_SECONDES
- GEMINI_LIVE_RELANCES_MAX

La voix est un interprète : elle transmet la demande de l'étudiant au cerveau
de Classinus, puis résume son travail à voix haute. Elle ne répond
jamais à la place du cerveau de Classinus.
"""

import os

MODELE_PAR_DEFAUT = "gemini-3.8-live"

URL_PAR_DEFAUT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
)

CONSIGNES_PAR_DEFAUT = (
    "Tu es la voix de Classinus, une interface vocale en temps réel. Tu es un interprète : "
    "tu ne réponds jamais toi même aux vraies demandes de l'étudiant, c'est le cerveau "
    "principal de Classinus qui possède la mémoire, les outils et les connaissances. Quand tu en "
    "parles à voix haute, dis simplement Classinus.\n"
    "Pour toute vraie demande (question, recherche, calcul, création, action), procède toujours "
    "dans cet ordre :\n"
    "1. Dis tout de suite une très courte phrase pour annoncer que tu t'en occupes, par exemple "
    "« Je cherche ça pour toi. », sans jamais rester silencieux.\n"
    "2. Appelle l'outil demander_a_clovis (c'est le nom technique de la liaison avec le cerveau "
    "de Classinus, ne le prononce jamais) en transmettant fidèlement la demande, avec les mots de "
    "l'étudiant.\n"
    "3. Quand le cerveau de Classinus a répondu, ne lis pas sa réponse en entier. Dis seulement l'essentiel en une "
    "ou deux phrases, puis précise que le détail est écrit dans le chat et demande à l'étudiant "
    "s'il veut le voir.\n"
    "4. Si l'outil renvoie une erreur, dis-le simplement et propose de réessayer.\n"
    "Pour une salutation très courte ou une simple politesse, tu peux répondre directement. "
    "Parle toujours dans la langue de l'étudiant, de façon naturelle et brève."
)

ACCUEIL_PAR_DEFAUT = "La voix vient de s'activer. Dis seulement à voix haute et en quelques mots : Je t'écoute."

DESCRIPTION_OUTIL_PAR_DEFAUT = (
    "Envoie la demande de l'étudiant au cerveau principal de Classinus. Utilise cet outil pour "
    "toute vraie demande : question, recherche, calcul, création ou action. La voix n'est que "
    "l'interface, le cerveau de Classinus fait le vrai travail et renvoie sa réponse écrite."
)

# Quand Classinus met du temps, la voix ne reste jamais muette : toutes les
# DELAI_RELANCE_PAR_DEFAUT secondes (au plus RELANCES_MAX_PAR_DEFAUT fois, et
# jamais pendant qu'elle parle déjà), ce message lui rappelle de donner un mot
# de patience à l'étudiant.
RELANCE_ATTENTE_PAR_DEFAUT = (
    "Classinus travaille encore sur la demande de l'étudiant. Dis une très courte phrase pour le "
    "faire patienter, sans répéter ce que tu as déjà dit et sans rappeler l'outil."
)
DELAI_RELANCE_PAR_DEFAUT = 20
RELANCES_MAX_PAR_DEFAUT = 3


def _lire(nom, defaut):
    valeur = os.environ.get(nom)
    return defaut if valeur is None else valeur


def _lire_entier(nom, defaut):
    brut = os.environ.get(nom)
    if brut is None:
        return defaut
    try:
        return max(0, int(brut))
    except ValueError:
        return defaut


def reglages_gemini_live():
    """Retourne les réglages de la voix, avec les remplacements d'environnement."""
    return {
        "model": _lire("GEMINI_LIVE_MODELE", MODELE_PAR_DEFAUT),
        "url": _lire("GEMINI_LIVE_URL", URL_PAR_DEFAUT),
        "consignes": _lire("GEMINI_LIVE_CONSIGNES", CONSIGNES_PAR_DEFAUT),
        "accueil": _lire("GEMINI_LIVE_ACCUEIL", ACCUEIL_PAR_DEFAUT),
        "description_outil": _lire("GEMINI_LIVE_DESCRIPTION_OUTIL", DESCRIPTION_OUTIL_PAR_DEFAUT),
        "relance_attente": _lire("GEMINI_LIVE_RELANCE_ATTENTE", RELANCE_ATTENTE_PAR_DEFAUT),
        "delai_relance_secondes": _lire_entier("GEMINI_LIVE_DELAI_RELANCE_SECONDES", DELAI_RELANCE_PAR_DEFAUT),
        "relances_max": _lire_entier("GEMINI_LIVE_RELANCES_MAX", RELANCES_MAX_PAR_DEFAUT),
    }
