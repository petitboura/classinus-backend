"""
Import de skills depuis un zip joint au chat (26/10/2026, demande de
Bourama). L'IA n'a rien à relire ni à réécrire : elle donne la
référence du zip, le serveur repère les skills, les valide avec les
mêmes règles que l'éditeur et les crée. Chaque skill est traité
séparément : l'échec de l'un n'empêche jamais les autres.
"""
import logging
import zipfile
from types import SimpleNamespace

from fastapi import HTTPException

from api import skills as _api
from core import zip_chat
from core.skills_entete import lire_entete
from core.skills_zip import lire_zip_skill
from core.skills_zip_multiple import trouver_skills


def _raison(e: Exception) -> str:
    if isinstance(e, HTTPException):
        detail = e.detail
        return (detail.get("message") if isinstance(detail, dict) else str(detail)) or "refusé"
    return "erreur inattendue"


def _importer_un(user_id: str, trouve: dict) -> str:
    membres = lire_zip_skill(trouve["contenu_zip"])
    entete = lire_entete(dict(membres)["SKILL.md"])
    nom = (entete.get("name") or "").strip() or trouve["nom_par_defaut"]
    description = (entete.get("description") or "").strip()
    payload = _api.SkillPayload(
        nom=nom, description=description, actif=True,
        fichiers=[_api.Fichier(chemin=c, contenu=t) for c, t in membres],
    )
    cree = _api._creer_skill(payload, SimpleNamespace(id=user_id))
    return f"{cree['nom']} (id {cree['id']}, {len(membres)} fichier(s))"


def importer_depuis_zip_chat(user_id: str, reference: str) -> str:
    job = zip_chat.obtenir_etat((reference or "").split("::", 1)[0].strip())
    if job is None:
        return "Erreur : ce zip n'est plus disponible, demande à l'utilisateur de le renvoyer."
    contenu = job.get("contenu_zip")
    if contenu is None:
        return "Erreur : ce zip est trop gros ou illisible pour être importé comme skill."
    try:
        trouves = trouver_skills(contenu, job["nom_zip"])
    except zipfile.BadZipFile:
        return "Erreur : ce zip est illisible."
    if not trouves:
        return "Aucun skill trouvé dans ce zip (il faut un dossier avec un fichier SKILL.md)."

    reussis, echecs = [], []
    for trouve in trouves:
        try:
            reussis.append(_importer_un(user_id, trouve))
        except Exception as e:
            if not isinstance(e, HTTPException):
                logging.error(f"ERREUR import skill depuis zip chat ({trouve['origine']}) : {e}")
            echecs.append(f"{trouve['origine']} : {_raison(e)}")
    lignes = [f"{len(reussis)} skill(s) importé(s) sur {len(trouves)}."]
    lignes += [f"- {r}" for r in reussis]
    if echecs:
        lignes.append("Non importés :")
        lignes += [f"- {r}" for r in echecs]
    return "\n".join(lignes)
