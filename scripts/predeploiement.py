"""Commande de pré-déploiement Railway : synchronise les skills officiels, puis lance le test Gemini Live.

À mettre dans Railway, Settings, Deploy, Pre-deploy Command, en UNE SEULE commande. Le dépôt a un
Dockerfile : Railway n'évalue alors pas les "&&" avec un shell, la seconde commande ne tournerait pas.

    python scripts/predeploiement.py

Étape 1, skills officiels (dossier skills_plateforme/) : ne bloque JAMAIS un déploiement. Toute erreur
est consignée dans les logs de pré-déploiement et le déploiement continue. Sans effet quand le contenu
n'a pas changé. La variable SKILLS_PLATEFORME_SYNCHRO=non la désactive.

Étape 2, test Gemini Live (scripts/verifier_gemini_live.py) : comme avant, son code de sortie décide
du déploiement. Si ce fichier n'existe plus, l'étape est simplement sautée.

Chaque service Railway utilise ses propres variables : staging écrit dans le Supabase et le R2 de
staging, production dans ceux de production.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

logging.basicConfig(level=logging.INFO, format="%(message)s")


def synchroniser_skills() -> None:
    """Envoie les skills officiels vers la base et R2. Ne lève jamais d'exception."""
    if (os.environ.get("SKILLS_PLATEFORME_SYNCHRO") or "").strip().lower() in ("non", "0", "false", "off"):
        logging.info("Synchronisation des skills officiels désactivée (SKILLS_PLATEFORME_SYNCHRO).")
        return
    try:
        from scripts import synchroniser_skills_plateforme as sync

        bilan = sync.synchroniser(True)
        sync.afficher(bilan, True)
    except Exception as e:
        logging.error(f"Synchronisation des skills officiels impossible, le déploiement continue : {type(e).__name__} : {e}")


def verifier_gemini_live() -> int:
    """Lance le test Gemini Live et renvoie son code de sortie (0 si le script n'existe plus)."""
    script = RACINE / "scripts" / "verifier_gemini_live.py"
    if not script.is_file():
        logging.info("scripts/verifier_gemini_live.py absent : test Gemini Live sauté.")
        return 0
    return subprocess.run([sys.executable, str(script)], cwd=str(RACINE)).returncode


def main() -> int:
    synchroniser_skills()
    return verifier_gemini_live()


if __name__ == "__main__":
    sys.exit(main())
