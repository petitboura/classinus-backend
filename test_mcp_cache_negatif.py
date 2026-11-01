"""
Cache negatif MCP + reveil a la demande (31/10/2026, diagnostic memoire
Render) : un serveur MCP en echec (service endormi) ne doit plus etre
retente a chaque message, et le serveur diagnostic doit etre reveille
avant le listing plutot que recevoir l'erreur de l'hebergeur.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "dummy")

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "core"))

import mcp_tools


def _reinitialiser_caches():
    mcp_tools._cache_catalogue_outils.clear()
    mcp_tools._cache_echecs_catalogue.clear()
    mcp_tools._derniers_reveils.clear()


def test_echec_mis_en_cache_negatif_pas_de_seconde_tentative():
    _reinitialiser_caches()
    faux = AsyncMock(side_effect=RuntimeError("serveur endormi"))
    with patch.object(mcp_tools, "_lister_outils_async", faux):
        try:
            mcp_tools._lister_outils_serveur_avec_cache("srv_test", "http://x", None)
            assert False, "le premier echec doit remonter pour les journaux"
        except RuntimeError:
            pass
        # Deuxieme appel dans la fenetre : aucun reseau, liste vide.
        assert mcp_tools._lister_outils_serveur_avec_cache("srv_test", "http://x", None) == []
    assert faux.await_count == 1


def test_succes_apres_echec_expire_redevient_possible():
    _reinitialiser_caches()
    outil = object()
    faux = AsyncMock(side_effect=[RuntimeError("panne"), [outil]])
    with patch.object(mcp_tools, "_lister_outils_async", faux):
        try:
            mcp_tools._lister_outils_serveur_avec_cache("srv_test", "http://x", None)
        except RuntimeError:
            pass
        # Fenetre passee : on simule son expiration, la tentative repart.
        mcp_tools._cache_echecs_catalogue["srv_test"] = 0
        assert mcp_tools._lister_outils_serveur_avec_cache("srv_test", "http://x", None) == [outil]
        # Succes mis en cache : plus aucun appel reseau ensuite.
        assert mcp_tools._lister_outils_serveur_avec_cache("srv_test", "http://x", None) == [outil]
    assert faux.await_count == 2


def test_reveil_appele_avant_listing_avec_url_declaree():
    _reinitialiser_caches()
    faux = AsyncMock(return_value=[])
    with patch.object(mcp_tools, "_lister_outils_async", faux), \
         patch.object(mcp_tools, "_reveiller_serveur") as reveil:
        mcp_tools._lister_outils_serveur_avec_cache(
            "srv_test", "http://x", None, reveil_url="http://x/health")
    reveil.assert_called_once_with("http://x/health")


def test_reveil_borne_a_une_fois_par_fenetre():
    _reinitialiser_caches()
    with patch.object(mcp_tools, "_reveiller_serveur") as reveil:
        mcp_tools._reveiller_si_recent_non_tente("http://x/health")
        mcp_tools._reveiller_si_recent_non_tente("http://x/health")
    # La premiere tentative passe par le vrai reveil ; on simule son
    # horodatage comme le fait _reveiller_serveur, la deuxieme est filtree.
    assert reveil.call_count == 1


def test_url_reveil_diagnostic_derivee_de_son_url_mcp():
    serveur = {"nom": "diagnostic_classtech"}
    assert mcp_tools._url_reveil(serveur, "https://hote.example/mcp/diagnostic") == "https://hote.example/health"
    assert mcp_tools._url_reveil({"nom": "autre"}, "https://hote.example/mcp") is None
