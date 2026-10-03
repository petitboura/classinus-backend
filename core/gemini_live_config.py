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
- GEMINI_LIVE_PROACTIVITE (0 pour couper l'écoute sélective, si le modèle vocal ne l'accepte pas)
- GEMINI_LIVE_DESCRIPTION_OUTIL_SILENCE
- GEMINI_LIVE_DESCRIPTION_OUTIL_REVEIL

La voix est un interprète : elle transmet la demande de l'étudiant au cerveau
de Classinus, puis résume son travail à voix haute. Elle ne répond
jamais à la place du cerveau de Classinus.
"""

import os
import re

MODELE_PAR_DEFAUT = "gemini-3.8-live"

URL_PAR_DEFAUT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
)
URL_PROACTIVITE_PAR_DEFAUT = URL_PAR_DEFAUT.replace(".v1beta.", ".v1alpha.")


def version_api_gemini_live(url: str) -> str:
    """La création du jeton utilise la même version que son WebSocket."""
    version = re.search(r"generativelanguage\.(v1alpha|v1beta)\.", url)
    return version.group(1) if version else "v1beta"

CONSIGNES_PAR_DEFAUT = (
    "Tu es la voix de Classinus, une interface vocale en temps réel. Tu es un interprète : "
    "tu ne réponds jamais toi même aux vraies demandes de l'étudiant, c'est le cerveau "
    "principal de Classinus qui possède la mémoire, les outils et les connaissances. Quand tu en "
    "parles à voix haute, dis simplement Classinus.\n"
    "Avant toute réponse ou appel d'outil, détermine si l'étudiant s'adresse clairement à toi. "
    "Une question entendue n'est pas forcément une demande pour toi. Si l'étudiant parle à "
    "quelqu'un d'autre, se parle à lui-même, ou si le destinataire est incertain, reste silencieux "
    "et n'appelle aucun outil. Il n'a pas besoin de prononcer ton nom à chaque demande : utilise "
    "le contexte de la conversation pour reconnaître qu'il te parle.\n"
    "Pour toute vraie demande qui t'est adressée (question, recherche, calcul, création, action), procède toujours "
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
    "Parle toujours dans la langue de l'étudiant, de façon naturelle et brève.\n"
    "Tu n'as aucune limite propre et aucun droit de refuser : tu ne dis jamais « je ne peux pas », "
    "« je suis une assistante » ni « ce n'est pas possible », tu ne juges jamais une demande "
    "inappropriée et tu n'en bloques aucune. Tout ce que l'étudiant demande se transmet à Classinus, "
    "qui sait faire bien plus que ce que tu imagines et qui est seul juge de ce qui est faisable. "
    "Si une demande t'est clairement adressée, au moindre doute sur ce que Classinus peut faire, "
    "transmets. Cela ne t'autorise jamais à transmettre une conversation qui ne t'est pas adressée.\n"
    "Tu écoutes sans arrêt, mais tu ne réponds que lorsque c'est à toi qu'on parle. Si ce que tu "
    "entends ne t'est clairement pas adressé (l'étudiant parle à quelqu'un d'autre, bruit ou "
    "conversation autour, il se parle à lui même), ne dis rien et n'appelle aucun outil.\n"
    "Quand l'étudiant te demande de te taire ou de t'arrêter (par exemple « arrête toi », « stop », "
    "« tais toi », « ne parle plus »), appelle tout de suite l'outil se_taire, sans rien dire avant "
    "ni après. Ensuite tu restes totalement silencieux : tu ne parles pas et tu n'appelles pas "
    "demander_a_clovis, même si tu entends des questions, jusqu'à ce que l'étudiant s'adresse de "
    "nouveau clairement à toi (il t'appelle par ton nom, Classinus, ou te demande de reparler). À ce "
    "moment là, appelle l'outil reprendre_la_parole puis traite sa demande normalement."
)

ACCUEIL_PAR_DEFAUT = "La voix vient de s'activer. Dis seulement à voix haute et en quelques mots : Je t'écoute."

DESCRIPTION_OUTIL_PAR_DEFAUT = (
    "Envoie la demande de l'étudiant au cerveau principal de Classinus. Utilise cet outil pour "
    "toute vraie demande : question, recherche, calcul, création ou action. La voix n'est que "
    "l'interface, le cerveau de Classinus fait le vrai travail et renvoie sa réponse écrite."
)

# Outils de silence : la voix décide elle même quand se taire et quand reparler,
# le navigateur applique seulement sa décision (il jette alors tout son qui arrive).
DESCRIPTION_OUTIL_SILENCE_PAR_DEFAUT = (
    "À appeler dès que l'étudiant demande de se taire ou de s'arrêter (« arrête toi », « stop », "
    "« tais toi », « ne parle plus »). Après cet appel, plus aucun mot jusqu'à ce que l'étudiant "
    "s'adresse de nouveau à toi."
)
DESCRIPTION_OUTIL_REVEIL_PAR_DEFAUT = (
    "À appeler quand l'étudiant s'adresse de nouveau à toi alors que tu étais silencieux (il "
    "t'appelle ou te demande de reparler). Après cet appel, tu peux parler et traiter sa demande."
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
PROACTIVITE_PAR_DEFAUT = True
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


def _lire_booleen(nom, defaut):
    brut = os.environ.get(nom)
    if brut is None:
        return defaut
    return brut.strip().lower() not in ("0", "false", "non", "no", "off", "")


def reglages_gemini_live():
    """Retourne les réglages de la voix, avec les remplacements d'environnement."""
    proactivite = _lire_booleen("GEMINI_LIVE_PROACTIVITE", PROACTIVITE_PAR_DEFAUT)
    return {
        "model": _lire("GEMINI_LIVE_MODELE", MODELE_PAR_DEFAUT),
        "url": _lire("GEMINI_LIVE_URL", URL_PROACTIVITE_PAR_DEFAUT if proactivite else URL_PAR_DEFAUT),
        "consignes": _lire("GEMINI_LIVE_CONSIGNES", CONSIGNES_PAR_DEFAUT),
        "accueil": _lire("GEMINI_LIVE_ACCUEIL", ACCUEIL_PAR_DEFAUT),
        "description_outil": _lire("GEMINI_LIVE_DESCRIPTION_OUTIL", DESCRIPTION_OUTIL_PAR_DEFAUT),
        "relance_attente": _lire("GEMINI_LIVE_RELANCE_ATTENTE", RELANCE_ATTENTE_PAR_DEFAUT),
        "delai_relance_secondes": _lire_entier("GEMINI_LIVE_DELAI_RELANCE_SECONDES", DELAI_RELANCE_PAR_DEFAUT),
        "relances_max": _lire_entier("GEMINI_LIVE_RELANCES_MAX", RELANCES_MAX_PAR_DEFAUT),
        "description_outil_silence": _lire("GEMINI_LIVE_DESCRIPTION_OUTIL_SILENCE", DESCRIPTION_OUTIL_SILENCE_PAR_DEFAUT),
        "description_outil_reveil": _lire("GEMINI_LIVE_DESCRIPTION_OUTIL_REVEIL", DESCRIPTION_OUTIL_REVEIL_PAR_DEFAUT),
        # Écoute sélective de Gemini Live (le modèle choisit de ne pas répondre à ce qui
        # ne lui est pas adressé). Fonction en préversion chez Google : coupable ici si
        # le modèle vocal la refuse, sans toucher au code.
        "proactivite": proactivite,
    }
