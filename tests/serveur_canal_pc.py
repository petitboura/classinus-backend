"""Serveur de régression local : vraie route WS et vrais outils, sans compte réel.

Les seuls remplacements sont l'authentification et l'enregistrement MCP.
Jamais importé par l'application déployée.
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

auth = types.ModuleType("api.auth")
auth.supabase = SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:
    SimpleNamespace(user=SimpleNamespace(id="test-pc")) if token == "session-test" else None))
sys.modules["api.auth"] = auth

temps_reel = types.ModuleType("core.canal_temps_reel")
async def fermer(websocket, code):
    await websocket.close(code=code)
temps_reel.fermer_websocket_sans_erreur = fermer
sys.modules["core.canal_temps_reel"] = temps_reel

commun = types.ModuleType("core.outils_generation_commun")
commun.mcp_generation = SimpleNamespace(tool=lambda: lambda fonction: fonction)
commun.Context = SimpleNamespace
sys.modules["core.outils_generation_commun"] = commun

from fastapi import FastAPI
from api.canal_agent_applicatif import router
from core import canal_agent_applicatif as canal
from core.outils_action_agent_pc import lire_ecran, taper_clavier, ouvrir_application

app = FastAPI()
app.include_router(router)
ctx = SimpleNamespace(request_context=SimpleNamespace(
    request=SimpleNamespace(query_params={"user_id": "test-pc"})))

@app.get("/test/etat")
async def etat():
    return {"actions": canal.obtenir_actions_disponibles("test-pc"),
            "appareils": [a for u, a in canal._connexions if u == "test-pc"]}

@app.get("/test/lire-page")
async def page():
    return await canal.demander_lecture_page("test-pc")

@app.get("/test/lire-ecran")
async def ecran():
    return {"texte": await lire_ecran(ctx)}

@app.get("/test/taper")
async def taper():
    return {"texte": await taper_clavier("Texte test", ctx)}

@app.get("/test/ouvrir")
async def ouvrir():
    return {"texte": await ouvrir_application("notepad", ctx)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
