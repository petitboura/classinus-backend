"""
Erreur en plein tour de conversation, vue par le chat du site.

Quand le fournisseur du modele echoue, le serveur n'envoie plus seulement une phrase
d'excuse : il dit de quelle sorte d'erreur il s'agit (code) et, si des outils ont deja
tourne, il joint l'etat de reprise. Le chat peut alors proposer "Continuer" (la reprise
garde tous les resultats d'outils deja obtenus) au lieu d'un "Reessayer" qui repart de zero.

Le client qui n'a pas demande ces erreurs typees (erreurs_typees=False : plugin Thonny,
serveur MCP, import depuis une autre IA) recoit exactement l'ancienne phrase d'excuse.
"""
from boucle_agent import _evenement_reprise_agent, messages_reprenables
from constantes_agent import MESSAGE_ERREUR

CODE_DELAI = "delai"
CODE_FORTE_DEMANDE = "forte_demande"
CODE_SERVEUR = "serveur"

_STATUTS_FORTE_DEMANDE = {413, 429, 503, 529}
_MOTS_FORTE_DEMANDE = (
    "rate limit", "rate_limit", "ratelimit", "too many requests", "quota", "overloaded",
    "capacity", "resource_exhausted", "resource exhausted", "tokens per minute", "request too large",
)


def classer_erreur(erreur):
    """Code de l'erreur : delai, forte_demande ou serveur (jamais le texte technique)."""
    statut = getattr(erreur, "status_code", None)
    texte = str(erreur).lower() if erreur is not None else ""
    if statut in _STATUTS_FORTE_DEMANDE:
        return CODE_FORTE_DEMANDE
    if "timeout" in texte or "timed out" in texte:
        return CODE_DELAI
    if any(mot in texte for mot in _MOTS_FORTE_DEMANDE):
        return CODE_FORTE_DEMANDE
    return CODE_SERVEUR


def _texte_excuse(langue_interface):
    return "Something went wrong. Please try again shortly." if langue_interface == "en" else MESSAGE_ERREUR


def evenement_echec(
    erreur, langue_interface, erreurs_typees, avec_texte=True,
    messages_agent=None, nb_messages_depart=0, outils_mcp=None, table_routage=None,
    modele=None, reasoning_effort=None, agent_nom=None,
):
    """
    Evenement a envoyer quand le tour echoue, ou None s'il n'y a rien a envoyer.

    - erreurs_typees faux : l'ancienne phrase d'excuse (evenement "reponse"), seulement si
      avec_texte (elle n'etait jamais envoyee par dessus un texte deja ecrit).
    - erreurs_typees vrai : evenement "erreur_tour" avec le code et, si au moins un outil a
      tourne depuis nb_messages_depart, l'etat de reprise (sinon None : seul Reessayer a du sens).
    """
    if not erreurs_typees:
        return {"type": "reponse", "texte": _texte_excuse(langue_interface)} if avec_texte else None

    etat_reprise = None
    if messages_agent is not None and outils_mcp is not None:
        messages = messages_reprenables(messages_agent)
        if any(isinstance(m, dict) and m.get("role") == "tool" for m in messages[nb_messages_depart:]):
            etat_reprise = _evenement_reprise_agent(
                "erreur_tour", messages, outils_mcp, table_routage, modele, reasoning_effort, agent_nom
            )["etat_reprise"]
    return {"type": "erreur_tour", "code": classer_erreur(erreur), "etat_reprise": etat_reprise}
