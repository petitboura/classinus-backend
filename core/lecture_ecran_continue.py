"""
Canal en direct sur PC : verrou "premiere lecture" (30/09/2026, decision
Bourama).

Regle : dans une conversation, l'IA ne peut pas agir sur le PC (clic, frappe,
raccourci, ouverture d'application) tant qu'elle n'a pas lu l'ecran au moins
une fois. Une fois cette premiere lecture faite, le mode continu s'active :
chaque action PC renvoie d'elle-meme l'etat de l'ecran qui suit (voir
core/outils_action_agent_pc.py), donc l'IA n'a plus a rappeler lire_ecran
apres chaque action. Une nouvelle conversation repart de zero.

L'etat est garde en memoire du processus, par (utilisateur, conversation).
Consequence assumee : si le service redemarre (redeploiement Railway) en
cours de conversation, l'etat est perdu et l'IA relit simplement une fois.
Sans danger : le verrou se remet en place, rien n'est execute a l'aveugle.

Sans identifiant de conversation (cas non attendu : le serveur MCP recoit
normalement conversation_id en parametre d'URL), l'etat est partage par
toutes les conversations du meme utilisateur. A surveiller si ce cas apparait.
"""

import os
import threading
import time

# Duree de vie d'un etat de lecture. Au-dela, la conversation est consideree
# comme reprise a zero (une relecture est alors redemandee).
DUREE_VIE_ETAT_SECONDES = int(os.environ.get("CLASSINUS_LECTURE_ECRAN_DUREE_VIE_S", str(6 * 3600)))
# Garde-fou memoire : au-dela, les etats expires sont purges d'abord, puis les
# plus anciens.
NB_MAX_CONVERSATIONS_SUIVIES = int(os.environ.get("CLASSINUS_LECTURE_ECRAN_NB_MAX", "5000"))

_lectures_faites: dict[tuple[str, str], float] = {}
_verrou = threading.Lock()


def _cle(user_id: str, conversation_id: str | None) -> tuple[str, str]:
    return (str(user_id), str(conversation_id or ""))


def a_deja_lu(user_id: str, conversation_id: str | None) -> bool:
    """Vrai si l'IA a deja lu l'ecran du PC dans cette conversation (etat non expire)."""
    cle = _cle(user_id, conversation_id)
    with _verrou:
        instant = _lectures_faites.get(cle)
        if instant is None:
            return False
        if time.monotonic() - instant > DUREE_VIE_ETAT_SECONDES:
            del _lectures_faites[cle]
            return False
        return True


def marquer_lu(user_id: str, conversation_id: str | None) -> None:
    """Enregistre qu'une lecture de l'ecran a abouti dans cette conversation."""
    maintenant = time.monotonic()
    with _verrou:
        _lectures_faites[_cle(user_id, conversation_id)] = maintenant
        if len(_lectures_faites) <= NB_MAX_CONVERSATIONS_SUIVIES:
            return
        for cle in [c for c, t in _lectures_faites.items() if maintenant - t > DUREE_VIE_ETAT_SECONDES]:
            del _lectures_faites[cle]
        if len(_lectures_faites) > NB_MAX_CONVERSATIONS_SUIVIES:
            plus_anciens = sorted(_lectures_faites, key=_lectures_faites.get)
            for cle in plus_anciens[: len(_lectures_faites) - NB_MAX_CONVERSATIONS_SUIVIES]:
                del _lectures_faites[cle]
