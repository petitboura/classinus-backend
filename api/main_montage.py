"""Serveur de montage vidéo séparé (demande de Bourama, 03/11/2026).

Même dépôt, même code de montage (core/serveur_mcp_video.py), mais un service
Coolify indépendant, construit par Dockerfile.montage avec tout déjà installé. Il ne
fait que le montage : le chat principal n'est plus ralenti par ffmpeg ni Remotion.

Le service principal l'appelle quand sa variable MONTAGE_VIDEO_URL est définie
(voir core/registre_outils.py). Même jeton interne qu'avant : l'en-tête
Authorization doit contenir SUPABASE_SECRET, vérifié dans la passerelle.
Les vidéos restent sur R2, rien ne dépend du disque de ce serveur.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from core.serveur_mcp_video import mcp_video


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp_video.session_manager.run():
        yield


app = FastAPI(title="Classinus montage vidéo", lifespan=lifespan)


@app.get("/sante")
def sante() -> dict:
    return {"ok": True, "service": "montage-video"}


# La protection anti DNS rebinding de la bibliothèque MCP n'accepte par défaut que
# localhost : un appel venant du chat par le réseau Railway serait refusé (421).
# Elle est désactivée ici car ce serveur n'est pas un serveur local : chaque appel
# doit porter le jeton interne (SUPABASE_SECRET), vérifié dans la passerelle.
app.mount(
    "/mcp/video",
    mcp_video.streamable_http_app(
        stateless_http=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    ),
)
