"""Régressions des fermetures avant authentification, sans réseau ni secrets."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import WebSocketDisconnect


def charger_route():
    # L'authentification externe est isolée ; la route et son helper de
    # fermeture sont ceux du code réel.
    auth = types.ModuleType("api.auth")
    auth.supabase = None
    auth.utilisateur_courant = lambda: None
    chemin = Path(__file__).parent / "api" / "canal_temps_reel.py"
    spec = importlib.util.spec_from_file_location("route_canal_test", chemin)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"api.auth": auth}):
        spec.loader.exec_module(module)
    return module


class FermetureAuthentification(unittest.IsolatedAsyncioTestCase):
    async def test_deconnexion_avant_auth_et_socket_deja_fermee(self):
        route = charger_route()
        socket = types.SimpleNamespace(
            accept=AsyncMock(),
            receive_json=AsyncMock(side_effect=WebSocketDisconnect(1001)),
            close=AsyncMock(side_effect=RuntimeError("socket déjà fermée")),
        )
        await route.canal_temps_reel(socket)
        socket.close.assert_awaited_once_with(code=4401)

    async def test_delai_auth_expire(self):
        route = charger_route()
        socket = types.SimpleNamespace(
            accept=AsyncMock(),
            receive_json=AsyncMock(side_effect=TimeoutError()),
            close=AsyncMock(),
        )
        await route.canal_temps_reel(socket)
        socket.close.assert_awaited_once_with(code=4401)

    async def test_token_absent(self):
        route = charger_route()
        socket = types.SimpleNamespace(
            accept=AsyncMock(), receive_json=AsyncMock(return_value={}),
            close=AsyncMock(),
        )
        await route.canal_temps_reel(socket)
        socket.close.assert_awaited_once_with(code=4401)


if __name__ == "__main__":
    unittest.main()
