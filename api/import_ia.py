"""Routes de l'import depuis une autre IA (27/10/2026, demande Bourama).

- GET  /api/import-ia                : prompt d'export (le même pour tous les boutons) et liste des IA à ouvrir
- POST /api/import-ia/zip?origine=   : dépose le zip, le serveur fait travailler le LLM en arrière-plan
                                       (origine : memoire, skills, configuration, chat, sert au lien de fin)
- GET  /api/import-ia/statut/{id}    : étape en cours, fin ou échec

Le travail lui-même vit dans core/import_depuis_autre_ia.py.
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter, Depends, File, Request, UploadFile

from api.auth import utilisateur_courant
from core import config_import_ia, import_depuis_autre_ia
from core.erreurs import erreur_api
from core.import_zip import est_zip
from core.restriction_mineur import acces_chat_bloque_pour_mineur
from core.zip_chat import TAILLE_MAX_ZIP_CHAT_OCTETS, demarrer_extraction_zip_chat

router = APIRouter(prefix="/api/import-ia", tags=["import-ia"])


def _langue(request: Request) -> str:
    valeur = request.headers.get("accept-language", "fr").split(",", 1)[0].strip().lower()
    return "en" if valeur == "en" or valeur.startswith("en-") else "fr"


def _verifier_origine(origine: str) -> str:
    if origine not in config_import_ia.ORIGINES:
        raise erreur_api(404, "IMPORT_IA_CIBLE_INCONNUE")
    return origine


@router.get("/statut/{import_id}")
def statut_import(import_id: str, utilisateur=Depends(utilisateur_courant)):
    etat = import_depuis_autre_ia.lire_etat(import_id, utilisateur.id)
    if etat is None:
        raise erreur_api(404, "IMPORT_IA_INTROUVABLE")
    return etat


@router.get("")
def configuration_import(request: Request, utilisateur=Depends(utilisateur_courant)):
    langue = _langue(request)
    return {"prompt": config_import_ia.prompt_export(langue), "ias": config_import_ia.ias_export(langue)}


@router.post("/zip")
async def deposer_zip(request: Request, origine: str = "chat", fichier: UploadFile = File(...), utilisateur=Depends(utilisateur_courant)):
    _verifier_origine(origine)
    langue = _langue(request)
    # Même règle que le chat : le travail passe par le chat, donc par ses restrictions.
    if acces_chat_bloque_pour_mineur(utilisateur.id):
        raise erreur_api(403, "IMPORT_IA_ACCES_BLOQUE")
    if not est_zip(fichier.filename or "", fichier.content_type):
        raise erreur_api(400, "FORMAT_NON_SUPPORTE_ZIP")
    contenu = await fichier.read()
    if len(contenu) == 0:
        raise erreur_api(400, "FICHIER_VIDE")
    if len(contenu) > TAILLE_MAX_ZIP_CHAT_OCTETS:
        raise erreur_api(400, "ZIP_TROP_LOURD_200_MO_MAX")
    deja = import_depuis_autre_ia.import_en_cours(utilisateur.id)
    if deja:
        raise erreur_api(409, "IMPORT_IA_DEJA_EN_COURS")
    job_zip = demarrer_extraction_zip_chat(contenu, fichier.filename or "archive.zip")
    return import_depuis_autre_ia.demarrer(utilisateur.id, origine, job_zip, langue)
