"""
Route de service des fichiers stockés sur Cloudflare R2.

Le bucket R2 reste privé. Cette route sert les objets au travers du backend.
Elle prend en charge GET/HEAD et les requêtes HTTP Range nécessaires aux
lecteurs audio/vidéo et aux aperçus de fichiers.

Le fichier est transmis au navigateur au fur et à mesure qu'il arrive de R2,
sans jamais être chargé en entier en mémoire : le premier octet part dès que
R2 répond, et le pourcentage de téléchargement affiché côté appli avance dès
le début. La route est synchrone (def et non async def) : FastAPI l'exécute
alors dans un fil séparé, ce qui évite que la lecture bloquante de R2 ne fige
le reste du backend (chat compris) pendant un téléchargement.
"""

import mimetypes
import re

from botocore.exceptions import ClientError
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from core import stockage_r2
from core.erreurs import erreur_api

router = APIRouter(prefix="/fichiers/r2", tags=["fichiers"])

# Taille des morceaux lus sur R2 puis envoyés au navigateur.
_TAILLE_MORCEAU = 256 * 1024

_MOTIF_PLAGE = re.compile(r"^(\d*)-(\d*)$")


def _type_mime(chemin: str, resultat: dict | None = None) -> str:
    return (
        (resultat or {}).get("ContentType")
        or mimetypes.guess_type(chemin)[0]
        or "application/octet-stream"
    )


def _plage_demandee(value: str | None) -> str | None:
    """Renvoie la première plage de l'en-tête Range, sous la forme attendue
    par R2 ("bytes=debut-fin"), ou None si l'en-tête est absent ou invalide."""
    if not value or not value.startswith("bytes="):
        return None
    spec = value[6:].split(",", 1)[0].strip()
    morceaux = _MOTIF_PLAGE.match(spec)
    if not morceaux or (morceaux.group(1) == "" and morceaux.group(2) == ""):
        return None
    return f"bytes={spec}"


def _flux(corps):
    try:
        for morceau in corps.iter_chunks(chunk_size=_TAILLE_MORCEAU):
            yield morceau
    finally:
        corps.close()


def _cle(bucket_logique: str, chemin: str) -> str:
    return stockage_r2._cle_objet(bucket_logique, chemin)


def _meta(bucket_logique: str, chemin: str) -> dict:
    try:
        return stockage_r2._client.head_object(
            Bucket=stockage_r2.R2_BUCKET_NAME,
            Key=_cle(bucket_logique, chemin),
        )
    except Exception:
        raise erreur_api(404, "FICHIER_INTROUVABLE")


def _reponse_plage_invalide(bucket_logique: str, chemin: str) -> Response:
    taille = int(_meta(bucket_logique, chemin).get("ContentLength") or 0)
    return Response(
        status_code=416,
        headers={
            "Content-Range": f"bytes */{taille}",
            "Accept-Ranges": "bytes",
        },
    )


@router.api_route("/{bucket_logique}/{chemin:path}", methods=["GET", "HEAD"])
def servir_fichier_r2(bucket_logique: str, chemin: str, request: Request):
    if request.method == "HEAD":
        meta = _meta(bucket_logique, chemin)
        return Response(
            status_code=200,
            headers={
                "Content-Type": _type_mime(chemin, meta),
                "Content-Length": str(int(meta.get("ContentLength") or 0)),
                "Accept-Ranges": "bytes",
            },
        )

    range_value = request.headers.get("range")
    plage = _plage_demandee(range_value)
    if range_value and plage is None:
        return _reponse_plage_invalide(bucket_logique, chemin)

    parametres = {
        "Bucket": stockage_r2.R2_BUCKET_NAME,
        "Key": _cle(bucket_logique, chemin),
    }
    if plage:
        parametres["Range"] = plage

    try:
        resultat = stockage_r2._client.get_object(**parametres)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "InvalidRange":
            return _reponse_plage_invalide(bucket_logique, chemin)
        raise erreur_api(404, "FICHIER_INTROUVABLE")
    except Exception:
        raise erreur_api(404, "FICHIER_INTROUVABLE")

    en_tetes = {
        "Content-Length": str(int(resultat.get("ContentLength") or 0)),
        "Accept-Ranges": "bytes",
    }
    statut = 200
    if plage:
        statut = 206
        en_tetes["Content-Range"] = resultat.get("ContentRange", "")

    return StreamingResponse(
        _flux(resultat["Body"]),
        status_code=statut,
        headers=en_tetes,
        media_type=_type_mime(chemin, resultat),
    )
