"""
Pont téléphone (29/10/2026) : les outils téléphone s'exécutent via l'appli
PC (canal agent applicatif), jamais sur le cloud. Sans appel réseau : le
pont est simulé.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "dummy")

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "core"))

import mcp_tools
from registre_outils import SERVEURS_MCP


def _route_telephone(**extra):
    route = {"url": "https://class-tech-outils.onrender.com/mcp/diagnostic",
             "headers": None, "via_app_telephone": True, "user_id": "u1"}
    route.update(extra)
    return route


def test_registre_marque_outils_telephone_via_app():
    entrees = [s for s in SERVEURS_MCP if s.get("nom") == "diagnostic_classtech"]
    assert len(entrees) == 1
    assert entrees[0].get("via_app_telephone") is True


def test_sans_user_id_erreur_identification():
    texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone(user_id="")})
    assert texte == "Erreur : impossible d'identifier l'utilisateur."


def test_sans_app_message_ouverture_appli():
    with patch("canal_agent_applicatif.a_app_systeme_connecte", new=AsyncMock(return_value=False)):
        texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone()})
    assert texte == mcp_tools.MESSAGE_TELEPHONE_SANS_APP


def test_sans_reponse_message_mise_a_jour():
    with patch("canal_agent_applicatif.a_app_systeme_connecte", new=AsyncMock(return_value=True)), \
         patch("canal_agent_applicatif.demander_action_systeme", new=AsyncMock(return_value=None)):
        texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone()})
    assert texte == mcp_tools.MESSAGE_TELEPHONE_SANS_REPONSE


def test_pont_renvoie_texte_du_relais_sans_cloud():
    def exploser(*args, **kwargs):
        raise AssertionError("le cloud ne doit jamais être appelé pour un outil téléphone")

    with patch("canal_agent_applicatif.a_app_systeme_connecte", new=AsyncMock(return_value=True)), \
         patch("canal_agent_applicatif.demander_action_systeme",
               new=AsyncMock(return_value={"texte": "Téléphone détecté (TEST)."})) as pont, \
         patch("mcp_tools._appeler_outil_async", new=exploser):
        texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone()})
    assert texte == "Téléphone détecté (TEST)."
    args_pont = pont.await_args.args
    assert args_pont[0] == "u1"
    assert args_pont[1] == "outil_telephone"
    assert args_pont[2] == {"nom": "detecter_telephone", "args": {}}


def test_pont_erreur_remontee_en_erreur():
    with patch("canal_agent_applicatif.a_app_systeme_connecte", new=AsyncMock(return_value=True)), \
         patch("canal_agent_applicatif.demander_action_systeme",
               new=AsyncMock(return_value={"erreur": "relais arrêté"})):
        texte = mcp_tools.appeler_outil("lire_batterie", {}, {"lire_batterie": _route_telephone()})
    assert texte == "Erreur : relais arrêté"


def test_connexion_systeme_lit_le_registre():
    import canal_agent_applicatif as canal
    canal._relais_systeme.discard(("u9", "a9"))
    assert asyncio.run(canal.a_app_systeme_connecte("u9")) is False
    canal._relais_systeme.add(("u9", "a9"))
    try:
        assert asyncio.run(canal.a_app_systeme_connecte("u9")) is True
    finally:
        canal._relais_systeme.discard(("u9", "a9"))
