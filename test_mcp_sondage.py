"""Tests sans réseau du sondage des serveurs MCP proposés par l'IA (27/10/2026)."""

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SECRET", "test-only-secret")


class FauxClient:
    def table(self, *_args, **_kwargs):
        raise AssertionError("Ce test ne doit pas appeler Supabase")


supabase = types.ModuleType("supabase")
supabase.create_client = lambda *_args, **_kwargs: FauxClient()
supabase.ClientOptions = lambda **_kwargs: object()
sys.modules["supabase"] = supabase

from fastapi import HTTPException  # noqa: E402
from connexions import mcp_personnalises as mcp  # noqa: E402
from connexions.mcp_site_officiel import adresse_du_site_officiel, hote_de  # noqa: E402


class TestSiteOfficiel(unittest.TestCase):
    def test_meme_domaine_et_sous_domaine(self):
        self.assertTrue(adresse_du_site_officiel("https://mcp.linear.app/mcp", "https://linear.app"))
        self.assertTrue(adresse_du_site_officiel("https://linear.app/mcp", "https://www.linear.app/docs"))
        self.assertTrue(adresse_du_site_officiel("https://linear.app/mcp", "https://docs.linear.app"))

    def test_domaine_ressemblant_refuse(self):
        self.assertFalse(adresse_du_site_officiel("https://evil-linear.app/mcp", "https://linear.app"))
        self.assertFalse(adresse_du_site_officiel("https://linear.app.evil.com/mcp", "https://linear.app"))

    def test_hebergeur_partage_refuse(self):
        self.assertFalse(adresse_du_site_officiel("https://linear-mcp.vercel.app/mcp", "https://linear.app"))
        self.assertFalse(adresse_du_site_officiel("https://a.vercel.app/mcp", "https://b.vercel.app"))

    def test_site_absent_ou_inutilisable(self):
        self.assertFalse(adresse_du_site_officiel("https://mcp.linear.app/mcp", None))
        self.assertFalse(adresse_du_site_officiel("https://mcp.linear.app/mcp", ""))
        self.assertFalse(adresse_du_site_officiel("https://mcp.linear.app/mcp", "https://app"))
        self.assertFalse(adresse_du_site_officiel("https://mcp.exemple.co.uk/mcp", "https://co.uk"))
        self.assertFalse(adresse_du_site_officiel("https://1.2.3.4/mcp", "https://1.2.3.4"))

    def test_hote_de(self):
        self.assertEqual(hote_de("https://WWW.Linear.app./x"), "linear.app")
        self.assertEqual(hote_de("linear.app"), "linear.app")
        self.assertIsNone(hote_de(""))
        self.assertIsNone(hote_de(None))


class TestSondage(unittest.TestCase):
    def setUp(self):
        mcp._CACHE_SONDAGES.clear()
        mcp._SONDAGES_PAR_COMPTE.clear()
        # Pas de résolution DNS pendant les tests : l'adresse est rendue telle quelle.
        self._valider = patch.object(mcp, "valider_url_mcp", side_effect=lambda u: u)
        self._valider.start()
        self.addCleanup(self._valider.stop)

    def _sonder(self, *, liste_ok=False, statut=None, oauth=False):
        liste = patch.object(mcp, "_lister_outils_reseau", return_value=[]) if liste_ok else patch.object(
            mcp, "_lister_outils_reseau", side_effect=ValueError("Impossible de joindre ce serveur MCP."))
        with liste, \
                patch.object(mcp, "_statut_sans_authentification", return_value=statut), \
                patch.object(mcp, "_autorisation_en_un_clic_possible", return_value=oauth):
            return mcp._sonder_reseau("https://mcp.exemple.com/mcp")

    def test_serveur_libre(self):
        self.assertEqual(self._sonder(liste_ok=True), {"joignable": True, "acces": "none"})

    def test_autorisation_en_un_clic(self):
        self.assertEqual(self._sonder(statut=401, oauth=True), {"joignable": True, "acces": "oauth"})

    def test_jeton_quand_pas_d_autorisation_en_un_clic(self):
        self.assertEqual(self._sonder(statut=401, oauth=False), {"joignable": True, "acces": "bearer"})
        self.assertEqual(self._sonder(statut=403, oauth=False), {"joignable": True, "acces": "bearer"})

    def test_serveur_muet(self):
        self.assertEqual(self._sonder(statut=None), {"joignable": False, "acces": "inconnu"})

    def test_reponse_qui_n_est_pas_celle_d_un_serveur_mcp(self):
        self.assertEqual(self._sonder(statut=404), {"joignable": True, "acces": "inconnu"})

    def test_resultat_complet_avec_site_officiel(self):
        with patch.object(mcp, "_sonder_reseau", return_value={"joignable": True, "acces": "oauth"}):
            res = mcp.sonder_serveur("https://mcp.linear.app/mcp", "https://linear.app", "u1")
        self.assertEqual(res["domaine"], "mcp.linear.app")
        self.assertTrue(res["officiel"])
        self.assertEqual(res["acces"], "oauth")
        with patch.object(mcp, "_sonder_reseau", return_value={"joignable": True, "acces": "oauth"}):
            res = mcp.sonder_serveur("https://mcp.autre.com/mcp", "https://linear.app", "u1")
        self.assertFalse(res["officiel"])

    def test_lien_du_jeton_officiel_ou_non(self):
        with patch.object(mcp, "_sonder_reseau", return_value={"joignable": True, "acces": "bearer"}):
            res = mcp.sonder_serveur("https://mcp.linear.app/mcp", "https://linear.app", "u1", "https://linear.app/settings/api")
            self.assertTrue(res["lien_jeton_officiel"])
            res = mcp.sonder_serveur("https://mcp.linear.app/mcp", "https://linear.app", "u1", "https://linear-faux.com/settings/api")
            self.assertFalse(res["lien_jeton_officiel"])
            res = mcp.sonder_serveur("https://mcp.linear.app/mcp", "https://linear.app", "u1")
            self.assertFalse(res["lien_jeton_officiel"])

    def test_resultat_garde_en_memoire_seulement_si_joignable(self):
        with patch.object(mcp, "_sonder_reseau", return_value={"joignable": True, "acces": "none"}) as sonde:
            mcp.sonder_serveur("https://mcp.exemple.com/mcp", None, "u1")
            mcp.sonder_serveur("https://mcp.exemple.com/mcp", None, "u1")
        self.assertEqual(sonde.call_count, 1)
        with patch.object(mcp, "_sonder_reseau", return_value={"joignable": False, "acces": "inconnu"}) as sonde:
            mcp.sonder_serveur("https://muet.exemple.com/mcp", None, "u1")
            mcp.sonder_serveur("https://muet.exemple.com/mcp", None, "u1")
        self.assertEqual(sonde.call_count, 2)

    def test_limite_par_compte(self):
        with patch.object(mcp, "SONDAGES_MAX_PAR_FENETRE", 2), \
                patch.object(mcp, "_sonder_reseau", return_value={"joignable": False, "acces": "inconnu"}):
            mcp.sonder_serveur("https://a.exemple.com/mcp", None, "u1")
            mcp.sonder_serveur("https://b.exemple.com/mcp", None, "u1")
            with self.assertRaises(HTTPException) as erreur:
                mcp.sonder_serveur("https://c.exemple.com/mcp", None, "u1")
            self.assertEqual(erreur.exception.status_code, 429)
            # Un autre compte n'est pas touché.
            mcp.sonder_serveur("https://c.exemple.com/mcp", None, "u2")

    def test_adresse_refusee_remonte_en_valeur_erreur(self):
        self._valider.stop()
        try:
            with self.assertRaises(ValueError):
                mcp.sonder_serveur("http://exemple.com/mcp", None, "u1")
        finally:
            self._valider.start()


if __name__ == "__main__":
    unittest.main()
