"""Synchronisation des skills officiels au démarrage du serveur.

Avant, elle tournait dans la commande de pré-déploiement de Railway. Le serveur est maintenant sur
Vultr (Coolify) et plus rien ne la lançait : la base gardait d'anciennes versions des skills officiels,
et un environnement neuf (staging) n'en avait aucun. Elle est donc lancée ici, en arrière-plan, à
chaque démarrage.

Elle ne bloque JAMAIS le démarrage ni les requêtes : toute erreur est consignée dans les logs et le
serveur continue. Relançable sans risque : un skill dont le contenu n'a pas changé est laissé tel quel.
La variable SKILLS_PLATEFORME_SYNCHRO=non la désactive (la même que pour scripts/predeploiement.py).
"""
import asyncio
import logging
import os

from anyio import to_thread

VALEURS_DESACTIVATION = ("non", "0", "false", "off")


def synchro_desactivee() -> bool:
    return (os.environ.get("SKILLS_PLATEFORME_SYNCHRO") or "").strip().lower() in VALEURS_DESACTIVATION


def _synchroniser_maintenant() -> None:
    from scripts import synchroniser_skills_plateforme as sync

    bilan = sync.synchroniser(True)
    sync.afficher(bilan, True)


async def synchroniser_au_demarrage() -> None:
    """Envoie les skills officiels vers la base et R2 sans jamais lever d'exception."""
    if synchro_desactivee():
        logging.info("Synchronisation des skills officiels désactivée (SKILLS_PLATEFORME_SYNCHRO).")
        return
    try:
        await to_thread.run_sync(_synchroniser_maintenant)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.error(f"Synchronisation des skills officiels impossible, le serveur continue : {type(e).__name__} : {e}")
