"""Réglages de l'avatar Napster du mode vocal (16/11/2026, demande de Bourama).

L'avatar remplace seulement l'onde du mode vocal (plein écran et mini). Comme la voix Gemini
Live, il est un interprète : il écoute, parle, et transmet toute vraie demande au cerveau de
Classinus, qui garde la mémoire, les outils et les connaissances. Napster ne reçoit aucun
identifiant d'élève et ne garde donc aucune mémoire.

Tout vient de variables d'environnement (Railway), rien n'est écrit en dur :

- AVATAR_NAPSTER_ACTIF        INTERRUPTEUR. « 1 », « true » ou « oui » pour allumer. Absent ou autre
                              chose : l'avatar est éteint et le mode vocal reste exactement celui
                              d'avant (onde et voix Gemini). Se change sans toucher au code.
- NAPSTER_API_KEY             clé de l'API Napster (reste côté serveur).
- NAPSTER_AGENT_ID            identifiant de l'agent Napster.
- NAPSTER_API_URL             (facultatif) adresse de l'API, https://companion-api.napster.com par défaut.
- AVATAR_NAPSTER_MAX_PAR_MINUTE  (facultatif) nombre maximal de jetons par minute et par compte, 6 par défaut.
- AVATAR_NAPSTER_CONSIGNES, AVATAR_NAPSTER_DESCRIPTION_OUTIL, AVATAR_NAPSTER_ACCUEIL,
  AVATAR_NAPSTER_ANNONCE_REPONSE, AVATAR_NAPSTER_ANNONCE_BULLE, AVATAR_NAPSTER_ATTENTE,
  AVATAR_NAPSTER_SUITE_DEMANDE :
  textes donnés à l'avatar (facultatifs, valeurs par défaut ci dessous).
"""

import os

URL_PAR_DEFAUT = "https://companion-api.napster.com"
DEMARRAGES_MAX_PAR_MINUTE_PAR_DEFAUT = 6

NOM_OUTIL = "demander_a_classinus"

CONSIGNES_PAR_DEFAUT = (
    "Tu es la voix et le visage de Classinus. Tu es un interprète : tu ne réponds jamais toi même "
    "aux vraies demandes de l'utilisateur, c'est le cerveau principal de Classinus qui possède la "
    "mémoire, les outils et les connaissances. Quand tu en parles à voix haute, dis simplement Classinus.\n"
    "Pour toute vraie demande (question, recherche, calcul, création, action), appelle toujours "
    f"l'outil {NOM_OUTIL} avec la demande de l'utilisateur, avec ses propres mots, puis dis à voix "
    "haute l'essentiel de la réponse reçue, sans rien inventer ni ajouter.\n"
    "Tu peux répondre toi même seulement aux simples politesses (bonjour, merci). Tu n'as aucun droit "
    "de refuser une demande : au moindre doute sur ce que Classinus peut faire, transmets la demande.\n"
    "Réponds dans la langue de l'utilisateur."
)

DESCRIPTION_OUTIL_PAR_DEFAUT = (
    "Transmet la demande de l'utilisateur à Classinus, qui a la mémoire, les outils et les "
    "connaissances, et renvoie sa réponse écrite à dire à voix haute."
)

ACCUEIL_PAR_DEFAUT = "La session vient de commencer. Salue brièvement l'utilisateur et demande ce dont il a besoin."

ANNONCE_REPONSE_PAR_DEFAUT = (
    "Classinus vient de répondre à un message tapé par l'utilisateur. Dis à voix haute l'essentiel "
    "de cette réponse, en quelques phrases, sans rien ajouter. Réponse : "
)

ANNONCE_BULLE_PAR_DEFAUT = "Classinus a un message pour l'utilisateur. Dis le à voix haute tel quel : "

ATTENTE_PAR_DEFAUT = "Classinus travaille sur la demande. Dis brièvement à l'utilisateur de patienter, sans rien inventer."

SUITE_DEMANDE_PAR_DEFAUT = (
    "Classinus a terminé la demande en cours. Dis à voix haute l'essentiel de sa réponse, "
    "en quelques phrases, sans rien ajouter. Réponse : "
)


def _texte(nom: str, defaut: str) -> str:
    valeur = os.environ.get(nom)
    # Une variable présente mais vide supprime le texte (comme GEMINI_LIVE_ACCUEIL).
    return defaut if valeur is None else valeur.strip()


def est_actif() -> bool:
    """Interrupteur : vrai seulement si AVATAR_NAPSTER_ACTIF vaut 1, true ou oui."""
    return (os.environ.get("AVATAR_NAPSTER_ACTIF") or "").strip().lower() in ("1", "true", "oui", "yes", "on")


def adresse_api() -> str:
    base = (os.environ.get("NAPSTER_API_URL") or "").strip().rstrip("/")
    return base if base.startswith(("http://", "https://")) else URL_PAR_DEFAUT


def cle_api() -> str:
    return (os.environ.get("NAPSTER_API_KEY") or "").strip()


def identifiant_agent() -> str:
    return (os.environ.get("NAPSTER_AGENT_ID") or "").strip()


def est_configure() -> bool:
    return bool(cle_api() and identifiant_agent())


def demarrages_max_par_minute() -> int:
    try:
        valeur = int((os.environ.get("AVATAR_NAPSTER_MAX_PAR_MINUTE") or "").strip())
    except ValueError:
        return DEMARRAGES_MAX_PAR_MINUTE_PAR_DEFAUT
    return valeur if valeur >= 1 else DEMARRAGES_MAX_PAR_MINUTE_PAR_DEFAUT


def reglages_avatar_napster() -> dict:
    """Textes donnés à l'avatar, remplaçables par variables d'environnement."""
    return {
        "nom_outil": NOM_OUTIL,
        "consignes": _texte("AVATAR_NAPSTER_CONSIGNES", CONSIGNES_PAR_DEFAUT),
        "description_outil": _texte("AVATAR_NAPSTER_DESCRIPTION_OUTIL", DESCRIPTION_OUTIL_PAR_DEFAUT),
        "accueil": _texte("AVATAR_NAPSTER_ACCUEIL", ACCUEIL_PAR_DEFAUT),
        "annonce_reponse": _texte("AVATAR_NAPSTER_ANNONCE_REPONSE", ANNONCE_REPONSE_PAR_DEFAUT),
        "annonce_bulle": _texte("AVATAR_NAPSTER_ANNONCE_BULLE", ANNONCE_BULLE_PAR_DEFAUT),
        "attente": _texte("AVATAR_NAPSTER_ATTENTE", ATTENTE_PAR_DEFAUT),
        "suite_demande": _texte("AVATAR_NAPSTER_SUITE_DEMANDE", SUITE_DEMANDE_PAR_DEFAUT),
    }
