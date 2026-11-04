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
    route = {"url": "https://class-tech.up.railway.app/mcp/diagnostic",
             "headers": None, "via_app_telephone": True, "user_id": "u1"}
    route.update(extra)
    return route


def test_registre_marque_outils_telephone_via_app():
    entrees = [s for s in SERVEURS_MCP if s.get("nom") == "diagnostic_classtech"]
    assert len(entrees) == 1
    assert entrees[0].get("via_app_telephone") is True


def _entree_diagnostic():
    entrees = [s for s in SERVEURS_MCP if s.get("nom") == "diagnostic_classtech"]
    assert len(entrees) == 1
    return entrees[0]


def test_sondes_sans_telephone_restent_sur_le_cloud():
    entree = _entree_diagnostic()
    for nom in ("ping_serveur", "verifier_chaine", "resumer_symptome"):
        assert mcp_tools._route_via_app_telephone(entree, nom) is False


def test_outil_telephone_passe_par_app():
    entree = _entree_diagnostic()
    assert mcp_tools._route_via_app_telephone(entree, "detecter_telephone") is True
    assert mcp_tools._route_via_app_telephone({}, "detecter_telephone") is False


def test_sans_user_id_erreur_identification():
    texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone(user_id="")})
    assert texte == "Erreur : impossible d'identifier l'utilisateur."


def test_sans_app_message_ouverture_appli():
    with patch("canal_agent_applicatif.a_app_telephone_connectee", new=AsyncMock(return_value=False)):
        texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone()})
    assert texte.startswith(mcp_tools.MESSAGE_TELEPHONE_SANS_APP)
    assert "Diagnostic" in texte and "AUCUNE connexion" in texte


def test_sans_reponse_message_mise_a_jour():
    with patch("canal_agent_applicatif.a_app_telephone_connectee", new=AsyncMock(return_value=True)), \
         patch("canal_agent_applicatif.demander_action_systeme", new=AsyncMock(return_value=None)):
        texte = mcp_tools.appeler_outil("detecter_telephone", {}, {"detecter_telephone": _route_telephone()})
    assert texte.startswith(mcp_tools.MESSAGE_TELEPHONE_SANS_REPONSE)
    assert "n'a pas répondu à temps" in texte


def test_pont_renvoie_texte_du_relais_sans_cloud():
    def exploser(*args, **kwargs):
        raise AssertionError("le cloud ne doit jamais être appelé pour un outil téléphone")

    with patch("canal_agent_applicatif.a_app_telephone_connectee", new=AsyncMock(return_value=True)), \
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
    with patch("canal_agent_applicatif.a_app_telephone_connectee", new=AsyncMock(return_value=True)), \
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


def test_connexion_native_prouve_appli_pc_pour_telephone():
    import canal_agent_applicatif as canal

    class FauxWs:
        pass

    ws = FauxWs()
    canal._connexions[("u8", "pc8-systeme")] = ws
    try:
        # Ancienne appli : pas de relais renderer déclaré, mais l'appli PC
        # tourne, donc l'outil téléphone doit être tenté, pas rejeté.
        assert asyncio.run(canal.a_app_telephone_connectee("u8")) is True
        assert asyncio.run(canal.a_app_systeme_connecte("u8")) is False
    finally:
        canal._connexions.pop(("u8", "pc8-systeme"), None)


def test_diffusion_telephone_exclut_connexion_native_sans_relais():
    import canal_agent_applicatif as canal

    recus = {}

    class FauxWs:
        def __init__(self, nom):
            self.nom = nom

        async def send_json(self, message):
            recus[self.nom] = message

    async def scenario():
        canal._connexions[("u7", "pc7-systeme")] = FauxWs("natif")
        canal._connexions[("u7", "web7")] = FauxWs("web")
        tache = asyncio.create_task(canal._diffuser_et_attendre(
            "u7",
            {"id": "test-tel-1", "action_systeme": "outil_telephone", "parametres": {"nom": "detecter_telephone", "args": {}}},
            delai_abandon_secondes=5,
        ))
        await asyncio.sleep(0.2)
        canal.recevoir_reponse("test-tel-1", {"texte": "ok"})
        return await tache

    try:
        assert asyncio.run(scenario()) == {"texte": "ok"}
        assert "web" in recus
        assert "natif" not in recus
    finally:
        canal._connexions.pop(("u7", "pc7-systeme"), None)
        canal._connexions.pop(("u7", "web7"), None)


def test_url_diagnostic_par_defaut_et_surcharge_par_variable(monkeypatch):
    """L'adresse du serveur class-tech vient de CLASSTECH_URL_MCP, sinon du defaut Railway."""
    import registre_outils
    entree = _entree_diagnostic()
    monkeypatch.delenv("CLASSTECH_URL_MCP", raising=False)
    url = entree["url_builder"](lambda nom: None, "u1", "a1")
    assert url == registre_outils.URL_DIAGNOSTIC_CLASSTECH_DEFAUT
    assert "onrender.com" not in url
    monkeypatch.setenv("CLASSTECH_URL_MCP", "  https://autre.example.com/mcp/diagnostic  ")
    assert entree["url_builder"](lambda nom: None, "u1", "a1") == "https://autre.example.com/mcp/diagnostic"
    monkeypatch.setenv("CLASSTECH_URL_MCP", "   ")
    assert entree["url_builder"](lambda nom: None, "u1", "a1") == registre_outils.URL_DIAGNOSTIC_CLASSTECH_DEFAUT


def test_reveil_derive_de_l_hote_railway():
    """Le /health de reveil suit l'hote de l'URL, jamais une adresse en dur."""
    entree = _entree_diagnostic()
    url = "https://class-tech.up.railway.app/mcp/diagnostic"
    assert mcp_tools._url_reveil(entree, url) == "https://class-tech.up.railway.app/health"


PROFONDS = (
    "lire_temperatures_internes", "lire_historique_batterie",
    "lire_trafic_par_appli", "lire_fluidite_ecran", "lire_saturation_systeme",
    "lire_reveils_planifies", "lire_journaux_systeme", "lire_carte_systeme",
    "lire_memoire_dans_le_temps", "lire_verrous_veille",
)


def test_outils_profonds_ranges_libelles_et_routes_vers_l_app():
    """Les 10 outils profonds sont dans la categorie, ont un libelle et passent par l'appli PC."""
    import registre_outils
    categorie = registre_outils.CATEGORIES_OUTILS["diagnostic_classtech"]
    entree = _entree_diagnostic()
    for nom in PROFONDS:
        assert nom in categorie, nom
        assert registre_outils.REGISTRE_AFFICHAGE_OUTILS[nom]["label"], nom
        assert registre_outils.REGISTRE_AFFICHAGE_OUTILS[nom]["icone"], nom
        assert mcp_tools._route_via_app_telephone(entree, nom) is True, nom
        assert nom not in registre_outils.OUTILS_SENSIBLES, nom
