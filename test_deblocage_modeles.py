"""
Verifie le deblocage d'un modele pour tout le monde ou pour une liste d'adresses (26/11/2026, demande de
Bourama) : validation, ecriture, revocation, lecture dans la configuration, et surtout ce que la liste des
modeles choisissables fait avec : malgre le palier et le Bientot, mais jamais sans cle API, jamais pour une
autre adresse, et sans ouvrir le palier d'acces anticipe. Sans appel reseau.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from core import deblocage_modeles as dm
from core import fournisseurs_llm as f
from core.deblocage_paliers import ErreurDeblocage

MODELES = {"deepseek-v4-flash", "deepseek-v4-pro", "claude-haiku-5-5", "claude-opus-5-5"}


def dans(jours):
    return (datetime.now(timezone.utc) + timedelta(days=jours)).isoformat()


class FauxClient:
    """Faux client Supabase qui enregistre les appels et sert des lignes toutes faites."""

    def __init__(self, lignes=None):
        self.lignes = lignes or []
        self.appels = []
        self.inseres = []
        self.refuse = False

    def table(self, nom):
        self.appels.append(("table", nom))
        return self

    def _noter(self, nom, *args):
        self.appels.append((nom,) + args)
        return self

    def select(self, *a): return self._noter("select", *a)
    def eq(self, *a): return self._noter("eq", *a)
    def is_(self, *a): return self._noter("is_", *a)
    def in_(self, *a): return self._noter("in_", *a)
    def delete(self): return self._noter("delete")
    def update(self, valeurs): return self._noter("update", valeurs)

    def insert(self, lignes):
        self.inseres.extend(lignes)
        return self._noter("insert", lignes)

    def execute(self):
        if self.refuse:
            raise Exception("boom")
        return SimpleNamespace(data=list(self.lignes))


class TestEcriture(unittest.TestCase):
    def setUp(self):
        p = patch("core.deblocage_modeles.ids_des_modeles", return_value=MODELES)
        p.start()
        self.addCleanup(p.stop)
        q = patch("core.deblocage_modeles.reinitialiser_cache_config_modeles")
        q.start()
        self.addCleanup(q.stop)

    def code(self, fonction, *a, **kw):
        with self.assertRaises(ErreurDeblocage) as c:
            fonction(*a, **kw)
        return c.exception.code

    def test_modele_inconnu(self):
        with patch("core.deblocage_modeles.supabase", FauxClient()):
            self.assertEqual(self.code(dm.debloquer_modele, "modele-fantome", tous=True), "DEBLOCAGE_MODELE_INCONNU")

    def test_une_seule_cible_exigee(self):
        with patch("core.deblocage_modeles.supabase", FauxClient()):
            self.assertEqual(self.code(dm.debloquer_modele, "claude-opus-5-5"), "DEBLOCAGE_MODELE_CIBLE_INVALIDE")
            self.assertEqual(
                self.code(dm.debloquer_modele, "claude-opus-5-5", tous=True, adresses=["a@b.co"]),
                "DEBLOCAGE_MODELE_CIBLE_INVALIDE",
            )

    def test_adresses_normalisees_sans_doublon(self):
        self.assertEqual(dm.normaliser_adresses([" A@B.co ", "a@b.co", "C@D.fr"]), ["a@b.co", "c@d.fr"])

    def test_adresse_mal_formee_refuse_tout(self):
        for mauvaise in ("pas-une-adresse", "a@b", "", "a b@c.d", "x" * 260 + "@b.co"):
            with self.subTest(mauvaise=mauvaise):
                self.assertEqual(self.code(dm.normaliser_adresses, ["ok@b.co", mauvaise]), "DEBLOCAGE_MODELE_EMAIL_INVALIDE")

    def test_trop_d_adresses(self):
        beaucoup = [f"p{i}@b.co" for i in range(dm.ADRESSES_MAX_PAR_APPEL + 1)]
        self.assertEqual(self.code(dm.normaliser_adresses, beaucoup), "DEBLOCAGE_MODELE_TROP_ADRESSES")

    def test_date_de_fin_passee(self):
        with patch("core.deblocage_modeles.supabase", FauxClient()):
            passe = datetime.now(timezone.utc) - timedelta(minutes=1)
            self.assertEqual(self.code(dm.debloquer_modele, "claude-opus-5-5", tous=True, expire_le=passe), "DEBLOCAGE_DATE_INVALIDE")

    def test_pour_tout_le_monde_une_ligne_sans_adresse(self):
        client = FauxClient(lignes=[])
        with patch("core.deblocage_modeles.supabase", client):
            res = dm.debloquer_modele("claude-opus-5-5", tous=True, accorde_par="admin-1", motif=" promo ")
        self.assertEqual(res, {"modele_id": "claude-opus-5-5", "ajoutes": 1, "deja_actifs": []})
        self.assertEqual(len(client.inseres), 1)
        self.assertIsNone(client.inseres[0]["email"])
        self.assertEqual(client.inseres[0]["motif"], "promo")
        self.assertEqual(client.inseres[0]["accorde_par"], "admin-1")

    def test_une_ligne_par_adresse_en_minuscules(self):
        client = FauxClient(lignes=[])
        with patch("core.deblocage_modeles.supabase", client):
            res = dm.debloquer_modele("claude-opus-5-5", adresses=["A@B.co", "c@d.fr"])
        self.assertEqual(res["ajoutes"], 2)
        self.assertEqual([l["email"] for l in client.inseres], ["a@b.co", "c@d.fr"])

    def test_pas_de_doublon_quand_deja_actif(self):
        client = FauxClient(lignes=[
            {"id": "1", "modele_id": "claude-opus-5-5", "email": "a@b.co", "expire_le": None},
            {"id": "2", "modele_id": "claude-opus-5-5", "email": None, "expire_le": dans(2)},
        ])
        with patch("core.deblocage_modeles.supabase", client):
            res = dm.debloquer_modele("claude-opus-5-5", adresses=["a@b.co", "z@y.fr"])
            res_tous = dm.debloquer_modele("claude-opus-5-5", tous=True)
        self.assertEqual(res["ajoutes"], 1)
        self.assertEqual(res["deja_actifs"], ["a@b.co"])
        self.assertEqual(res_tous["ajoutes"], 0)
        self.assertEqual(res_tous["deja_actifs"], ["tous"])

    def test_un_deblocage_expire_ne_compte_pas_comme_actif(self):
        client = FauxClient(lignes=[{"id": "1", "modele_id": "claude-opus-5-5", "email": None, "expire_le": dans(-1)}])
        with patch("core.deblocage_modeles.supabase", client):
            res = dm.debloquer_modele("claude-opus-5-5", tous=True)
        self.assertEqual(res["ajoutes"], 1)

    def test_revocation_tout_le_monde_et_par_adresse(self):
        client = FauxClient(lignes=[{"id": "1"}, {"id": "2"}])
        with patch("core.deblocage_modeles.supabase", client):
            self.assertEqual(dm.revoquer_modele("claude-opus-5-5", tous=True)["revoques"], 2)
            self.assertIn(("is_", "email", "null"), client.appels)
            client.appels.clear()
            dm.revoquer_modele("claude-opus-5-5", adresses=["A@b.co"])
            self.assertIn(("in_", "email", ["a@b.co"]), client.appels)

    def test_revocation_exige_une_cible(self):
        with patch("core.deblocage_modeles.supabase", FauxClient()):
            self.assertEqual(self.code(dm.revoquer_modele, "claude-opus-5-5"), "DEBLOCAGE_MODELE_CIBLE_INVALIDE")

    def test_lister_regroupe_par_modele(self):
        client = FauxClient(lignes=[
            {"id": "1", "modele_id": "m2", "email": "b@b.co", "expire_le": None},
            {"id": "2", "modele_id": "m2", "email": "a@b.co", "expire_le": dans(3)},
            {"id": "3", "modele_id": "m1", "email": None, "expire_le": None},
            {"id": "4", "modele_id": "m1", "email": "x@b.co", "expire_le": dans(-2)},
        ])
        with patch("core.deblocage_modeles.supabase", client):
            res = dm.lister()
        self.assertEqual(res["deblocages"], [
            {"modele_id": "m1", "tous": True, "adresses": []},
            {"modele_id": "m2", "tous": False, "adresses": ["a@b.co", "b@b.co"]},
        ])

    def test_erreur_supabase_devient_un_code_stable(self):
        client = FauxClient()
        client.refuse = True
        with patch("core.deblocage_modeles.supabase", client):
            self.assertEqual(self.code(dm.lister), "DEBLOCAGE_ECHEC")
            self.assertEqual(self.code(dm.revoquer_modele, "m", tous=True), "DEBLOCAGE_ECHEC")


class TestLectureConfiguration(unittest.TestCase):
    def test_actifs_seulement_et_adresses_normalisees(self):
        client = FauxClient(lignes=[
            {"modele_id": "m1", "email": None, "expire_le": None},
            {"modele_id": "m2", "email": "A@B.co", "expire_le": dans(1)},
            {"modele_id": "m3", "email": "a@b.co", "expire_le": dans(-1)},  # expire : ignore
            {"modele_id": "", "email": None, "expire_le": None},            # sans modele : ignore
        ])
        res = f._lire_deblocages_modeles(client)
        self.assertEqual(res["tous"], {"m1"})
        self.assertEqual(res["emails"], {"a@b.co": {"m2"}})

    def test_table_absente_rien_n_est_debloque(self):
        client = FauxClient()
        client.refuse = True
        self.assertEqual(f._lire_deblocages_modeles(client), {"tous": set(), "emails": {}})


class TestListeDesModeles(unittest.TestCase):
    """Le point important : ce que la liste choisissable fait des deblocages a la main."""

    def setUp(self):
        # Sans reseau : la configuration vient des valeurs de repli du code, pas de Supabase.
        p = patch("core.fournisseurs_llm._lire_config_modeles_supabase", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        f.reinitialiser_cache_config_modeles()
        self.addCleanup(f.reinitialiser_cache_config_modeles)

    def config(self, tous=(), emails=None, extra=None):
        base = f._config_modeles()
        cfg = {**base, "deblocages_modeles": {"tous": set(tous), "emails": {k: set(v) for k, v in (emails or {}).items()}}}
        if extra:
            cfg = extra(cfg)
        return cfg

    def ids(self, cfg, palier="pro", email=None, env=None, bientot=False):
        env = {"DEEPSEEK_API_KEY": "x"} if env is None else env
        with patch("core.fournisseurs_llm._config_modeles", return_value=cfg), patch.dict(os.environ, env, clear=True):
            dispo = f.modeles_disponibles_pour_agent("claude", palier, email)
            grises = f.modeles_bientot_pour_agent("claude", palier, email, avec_verrous_palier=True) if bientot else []
        return {m["modele_id"] for m in dispo}, {m["modele_id"] for m in grises}

    def test_sans_deblocage_le_modele_du_palier_superieur_est_ferme(self):
        dispo, _ = self.ids(self.config())
        self.assertIn("deepseek-v4-flash", dispo)
        self.assertNotIn("deepseek-v4-pro", dispo)

    def test_debloque_pour_tout_le_monde_malgre_le_palier(self):
        cfg = self.config(tous={"deepseek-v4-pro"})
        for email in (None, "n-importe-qui@b.co"):
            with self.subTest(email=email):
                self.assertIn("deepseek-v4-pro", self.ids(cfg, email=email)[0])

    def test_debloque_pour_une_adresse_seulement(self):
        cfg = self.config(emails={"a@b.co": {"deepseek-v4-pro"}})
        self.assertIn("deepseek-v4-pro", self.ids(cfg, email="A@B.co")[0])
        self.assertNotIn("deepseek-v4-pro", self.ids(cfg, email="autre@b.co")[0])
        self.assertNotIn("deepseek-v4-pro", self.ids(cfg, email=None)[0])

    def test_un_modele_debloque_n_est_plus_grise(self):
        cfg = self.config(tous={"deepseek-v4-pro"})
        dispo, grises = self.ids(cfg, bientot=True)
        self.assertIn("deepseek-v4-pro", dispo)
        self.assertNotIn("deepseek-v4-pro", grises)

    def test_debloque_malgre_le_bientot_du_fournisseur_si_la_cle_existe(self):
        # Claude est marque Bientot pour tout le monde ; un modele debloque l'ouvre, mais pas sans cle.
        cfg = self.config(tous={"claude-opus-5-5"})
        avec_cle = self.ids(cfg, palier="ultra", env={"ANTHROPIC_API_KEY": "x"})[0]
        sans_cle = self.ids(cfg, palier="ultra", env={})[0]
        sans_deblocage = self.ids(self.config(), palier="ultra", env={"ANTHROPIC_API_KEY": "x"})[0]
        self.assertIn("claude-opus-5-5", avec_cle)
        self.assertNotIn("claude-opus-5-5", sans_cle)
        self.assertNotIn("claude-opus-5-5", sans_deblocage)
        # Un seul modele est ouvert : les autres modeles Claude restent fermes.
        self.assertNotIn("claude-haiku-5-5", avec_cle)

    def test_ne_contourne_pas_le_fournisseur_ouvert_par_l_agent(self):
        # L'agent n'ouvre que les fournisseurs a partir de "deepseek" dans l'ordre : Claude reste hors de portee.
        cfg = self.config(tous={"claude-opus-5-5"})
        with patch("core.fournisseurs_llm._config_modeles", return_value=cfg), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}, clear=True):
            dispo = {m["modele_id"] for m in f.modeles_disponibles_pour_agent("deepseek", "ultra", None)}
        self.assertNotIn("claude-opus-5-5", dispo)

    def test_le_palier_d_acces_anticipe_reste_ferme(self):
        def avec_modele_specialise(cfg):
            modeles = {d: dict(p) for d, p in cfg["modeles"].items()}
            modeles["deepseek"]["specialise"] = {"id": "ds-secret", "label": "Secret"}
            return {**cfg, "modeles": modeles}

        cfg = self.config(tous={"deepseek-v4-pro"}, extra=avec_modele_specialise)
        dispo, _ = self.ids(cfg, email="n-importe-qui@b.co")
        self.assertIn("deepseek-v4-pro", dispo)       # le deblocage fonctionne
        self.assertNotIn("ds-secret", dispo)          # mais n'ouvre pas le palier specialise

    def test_modele_id_est_autorise_suit_les_deblocages(self):
        cfg = self.config(emails={"a@b.co": {"deepseek-v4-pro"}})
        with patch("core.fournisseurs_llm._config_modeles", return_value=cfg), patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            self.assertTrue(f.modele_id_est_autorise("deepseek-v4-pro", "claude", "pro", "a@b.co"))
            self.assertFalse(f.modele_id_est_autorise("deepseek-v4-pro", "claude", "pro", "autre@b.co"))
            self.assertFalse(f.modele_id_est_autorise("deepseek-v4-pro", "claude", "pro", None))


class TestRoutesAdmin(unittest.TestCase):
    def test_un_non_admin_est_refuse(self):
        from fastapi import HTTPException
        from api import deblocage_modeles as routes

        with patch("api.deblocage_modeles._est_admin", return_value=False):
            with self.assertRaises(HTTPException) as c:
                routes._exige_admin(SimpleNamespace(id="u"))
        self.assertEqual(c.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
