"""
Route de service des fichiers stockés sur Cloudflare R2 (voir
core/stockage_r2.py). Le bucket R2 est privé par défaut, sans accès
public direct : cette route est le point d'accès public unique aux
objets, en relais via ce backend. Elle remplace le rôle que jouait
l'URL publique directe renvoyée par Supabase Storage.
"""

import mimetypes

from fastapi import APIRouter, Request, Response

from core import stockage_r2
from core.erreurs import erreur_api

router = APIRouter(prefix="/fichiers/r2", tags=["fichiers"])


@router.api_route("/{bucket_logique}/{chemin:path}", methods=["GET", "HEAD"])
async def servir_fichier_r2(bucket_logique: str, chemin: str, request: Request):
    try:
        if request.method == "HEAD":
            # Pré-vérification légère : HEAD demande uniquement les
            # métadonnées à R2, sans télécharger le contenu du fichier.
            resultat = stockage_r2._client.head_object(
                Bucket=stockage_r2.R2_BUCKET_NAME,
                Key=stockage_r2._cle_objet(bucket_logique, chemin),
            )
            type_mime = resultat.get("ContentType") or mimetypes.guess_type(chemin)[0] or "application/octet-stream"
            headers = {"Content-Type": type_mime}
            if resultat.get("ContentLength") is not None:
                headers["Content-Length"] = str(resultat["ContentLength"])
            return Response(status_code=200, headers=headers)

        contenu = stockage_r2.from_(bucket_logique).download(chemin)
    except Exception:
        raise erreur_api(404, "FICHIER_INTROUVABLE")

    type_mime = mimetypes.guess_type(chemin)[0] or "application/octet-stream"
    return Response(content=contenu, media_type=type_mime)
