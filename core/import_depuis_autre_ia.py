"""Import depuis une autre IA, exécuté côté serveur (27/10/2026, demande Bourama).

Le zip exporté par l'autre IA est déposé par l'utilisateur depuis un bouton de la page Mémoire,
Skills ou Configuration, ou du bandeau du chat : tous font le même import. Ici, le serveur fait travailler le LLM de Classinus EXACTEMENT
comme si l'utilisateur avait joint ce zip dans le chat avec la consigne de config_import_ia.py :
même moteur (core/main.py:chat), mêmes outils (gerer_skill, mémoire, gerer_configuration),
même historique. Le travail continue si l'utilisateur ferme la page.

L'utilisateur est informé de deux façons : un état interrogeable (étape en cours, fin, échec)
et une notification à la fin. La conversation est rangée dans son historique.

Limites assumées :
- l'état est en mémoire du processus (comme core/zip_chat.py), perdu si le serveur redémarre ;
  l'historique et la notification, eux, sont en base ;
- une confirmation demandée par un outil ne peut pas être donnée en tâche de fond : l'import
  s'arrête proprement et le dit, rien n'est approuvé à la place de l'utilisateur.
"""
import logging
import sys
import os
import threading
import time
import uuid

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))

from core import config_import_ia
from core.arret_tour import fermer_arret, ouvrir_arret
from core.notifications import creer_notification
from core.plafond_outils_tour import retirer_plafond_tour

# Nombre maximum de reprises quand le plafond d'outils d'un tour est atteint (gros exports).
REPRISES_MAX = 6
# Les états terminés sont gardés ce temps, pour que la page puisse encore les lire.
DUREE_GARDE_SECONDES = 6 * 3600

_ETATS: dict[str, dict] = {}
_VERROU = threading.Lock()


def _nettoyer(maintenant: float) -> None:
    for cle in [c for c, e in _ETATS.items() if e["fin"] and maintenant - e["fin"] > DUREE_GARDE_SECONDES]:
        _ETATS.pop(cle, None)


def import_en_cours(user_id: str) -> str | None:
    """Identifiant d'un import encore actif pour cet utilisateur, sinon None.

    Tous les boutons font le même import : un seul à la fois par utilisateur, d'où qu'il soit lancé.
    """
    with _VERROU:
        for cle, etat in _ETATS.items():
            if etat["user_id"] == user_id and not etat["fin"]:
                return cle
    return None


def lire_etat(import_id: str, user_id: str) -> dict | None:
    """Etat public d'un import. None s'il n'existe pas ou n'appartient pas à cet utilisateur."""
    with _VERROU:
        etat = _ETATS.get(import_id)
        if etat is None or etat["user_id"] != user_id:
            return None
        return {
            "import_id": import_id,
            "cible": etat["cible"],
            "statut": etat["statut"],
            "etape": etat["etape"],
            "reponse": etat["reponse"],
            "conversation_id": etat["conversation_id"],
        }


def demarrer(user_id: str, origine: str, job_zip: str, langue: str | None, chat_generateur=None) -> dict:
    """Crée l'import et lance le travail en arrière-plan. Renvoie tout de suite l'identifiant.

    `chat_generateur` n'est passé que par les tests ; en vrai, c'est core/main.py:chat.
    """
    if chat_generateur is None:
        from main import chat as chat_generateur  # même import que api/chat.py
    import_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    with _VERROU:
        _nettoyer(time.time())
        _ETATS[import_id] = {
            "user_id": user_id, "cible": origine, "statut": "en_cours", "etape": "",
            "reponse": "", "conversation_id": conversation_id, "fin": None,
        }
    threading.Thread(
        target=_executer,
        args=(import_id, user_id, origine, job_zip, langue, conversation_id, chat_generateur),
        daemon=True,
    ).start()
    return {"import_id": import_id, "conversation_id": conversation_id}


def _maj(import_id: str, **champs) -> None:
    with _VERROU:
        etat = _ETATS.get(import_id)
        if etat is not None:
            etat.update(champs)


def _terminer(import_id: str, user_id: str, origine: str, langue: str | None, statut: str, **champs) -> None:
    _maj(import_id, statut=statut, fin=time.time(), **champs)
    titre, corps = config_import_ia.textes_notification("termine" if statut == "termine" else "echec", langue)
    creer_notification(user_id, "action_ia_terminee", titre, corps, lien=config_import_ia.PAGES_RESULTAT[origine])


def _executer(import_id, user_id, origine, job_zip, langue, conversation_id, chat_generateur) -> None:
    arret = ouvrir_arret(user_id)
    try:
        consigne = config_import_ia.consigne_llm(langue)
        libelle = config_import_ia.libelle_historique(langue)
        reprise = None
        reponses: list[str] = []
        for tentative in range(REPRISES_MAX + 1):
            if reprise is None:
                generateur = chat_generateur(
                    message_utilisateur=consigne, historique=[], user_id=user_id,
                    conversation_id=conversation_id, zips_en_attente=[job_zip],
                    message_enregistre=libelle, langue_interface=langue or "fr", arret_tour=arret,
                )
            else:
                generateur = chat_generateur(reprise=reprise, arret_tour=arret, langue_interface=langue or "fr")
            reprise = None
            for evenement in generateur:
                if not isinstance(evenement, dict):
                    continue
                genre = evenement.get("type")
                if genre in ("statut", "statut_termine") and evenement.get("texte"):
                    _maj(import_id, etape=str(evenement["texte"]))
                elif genre == "reponse" and evenement.get("texte"):
                    reponses.append(str(evenement["texte"]))
                elif genre == "confirmation_requise":
                    _terminer(import_id, user_id, origine, langue, "echec", etape="confirmation")
                    return
                elif genre == "limite_outils_atteinte" and evenement.get("etat_reprise"):
                    reprise = {"etat_reprise": evenement["etat_reprise"], "type": "continuer_agent"}
            if reprise is None:
                break
        texte = "".join(reponses).strip()
        _terminer(import_id, user_id, origine, langue, "termine", reponse=texte)
    except Exception as e:
        logging.error(f"ERREUR import depuis une autre IA (utilisateur {user_id}, origine {origine}) : {e}")
        _terminer(import_id, user_id, origine, langue, "echec")
    finally:
        fermer_arret(arret)
        retirer_plafond_tour(user_id)
