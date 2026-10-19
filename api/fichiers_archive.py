"""
Route de relais des PDF Internet Archive (lot 3 du chantier Internet Archive,
09/10/2026, demande Bourama). Toute la logique est dans core/relais_pdf_archive.py.

GET/HEAD /fichiers/archive/{identifiant}.pdf : sert le PDF du document en flux,
avec les requetes partielles (Range) pour que le visionneur du chat ne charge
que les pages regardees. Le lien se termine par .pdf : le chat l'ouvre alors
dans le visionneur (origine du backend = origine de confiance du frontend).

Pas d'authentification : un lecteur PDF ne peut pas joindre le jeton de
connexion a ses requetes de pages, comme pour /fichiers/r2. La protection
contre les abus est le plafond de taille (core/relais_pdf_archive.py), la
limite de debit par adresse ci-dessous, et le fait que seuls les PDF
publics d'archive.org sont relayes.
"""

import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from core.erreurs import erreur_api
from core.limitation_debit import limiteur
from core.relais_pdf_archive import ErreurRelais, identifiant_depuis_nom, ouvrir_pdf_archive

router = APIRouter(prefix="/fichiers/archive", tags=["fichiers"])

# Un lecteur PDF fait plusieurs requetes partielles par document : la limite
# par defaut est large, et reglable sans toucher au code.
_LIMITE = os.environ.get("ARCHIVE_RELAIS_LIMITE") or "240/minute"


@router.api_route("/{nom_fichier}", methods=["GET", "HEAD"])
@limiteur.limit(_LIMITE)
def servir_pdf_archive(request: Request, nom_fichier: str):
    identifiant = identifiant_depuis_nom(nom_fichier)
    if not identifiant:
        raise erreur_api(404, "DOCUMENT_ARCHIVE_INTROUVABLE")

    try:
        relais = ouvrir_pdf_archive(identifiant, request.method, request.headers.get("range"))
    except ErreurRelais as e:
        raise erreur_api(e.statut, e.code)

    if request.method == "HEAD" or relais.statut == 416:
        return Response(status_code=relais.statut, headers=relais.entetes)

    return StreamingResponse(
        relais.flux,
        status_code=relais.statut,
        headers=relais.entetes,
        media_type="application/pdf",
        background=None,
    )
