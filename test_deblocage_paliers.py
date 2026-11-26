"""
Verifie le deblocage de palier par personne (25/11/2026, demande de Bourama) : validation du palier, de la date
de fin et de la personne, calcul du plus haut palier actif (non revoque, non expire), revocation et reserve
aux administrateurs. Sans appel reseau : Supabase est remplace par un faux client.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from core import deblocage_paliers as d
from core import fournisseurs_llm
from core.fournisseurs_llm import (
    modele_id_est_autorise,
    modeles_bientot_pour_agent,
    modeles_disponibles_pour_agent,
    reinitialiser_cache_config_modeles,
)

ORDRE = ["essentiel", "pro", "premium", "max", "ultra"]
ORDRE_AVEC_ACCES_ANTICIPE = ORDRE + ["specialise"]
UUID_A = "11111111-1111-4111-8111-111111111111"
UUID_ADMIN = "22222222-2222-4222-8222-222222222222"


def dans(jours):
    return (datetime.now(timezone.utc) + timedelta(days=jours)).isoformat()


def faux_supabase(lignes=None, compte_existe=True, utilisateurs=None, lignes_revoquees=None):
    """Faux client Supabase : sert les deblocages demandes et memorise les ecritures."""
    ecritures = {"insert": [], "update": []}
    client = MagicMock()

    def table(nom):
        t = MagicMock()
        t.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=lignes or [])

        def insert(ligne):
            ecritures["insert"].append(ligne)
            return MagicMock(execute=MagicMock(return_value=MagicMock(data=[{**ligne, "id": "id-1"}])))

        def update(ligne):
            ecritures["update"].append(ligne)
            chaine = MagicMock()
            chaine.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=lignes_revoquees or [])
            return chaine

        t.insert.side_effect = insert
        t.update.side_effect = update
        return t

    client.table.side_effect = table
    if compte_existe:
        client.auth.admin.get_user_by_id.return_value = SimpleNamespace(user=SimpleNamespace(id=UUID_A))
    else:
        client.auth.admin.get_user_by_id.side_effect = Exception("User not found")
    client.auth.admin.list_users.return_value = utilisateurs or []
    return client, ecritures


class TestDeblocagePaliers(unittest.TestCase):
    def setUp(self):
        p = patch("core.deblocage_paliers.ordre_des_paliers", return_value=ORDRE)
        p.start()
        self.addCleanup(p.stop)

    def lancer(self, client, fonction, *args, **kw):
        with patch("core.deblocage_paliers.supabase", client):
            return fonction(*args, **kw)

    def code(self, client, fonction, *args, **kw):
        with self.assertRaises(d.ErreurDeblocage) as c:
            self.lancer(client, fonction, *args, **kw)
        return c.exception.code

    def test_palier_inconnu_refuse(self):
        client, ecr = faux_supabase()
        self.assertEqual(self.code(client, d.debloquer, UUID_A, "diamant"), "DEBLOCAGE_PALIER_INVALIDE")
        self.assertEqual(ecr["insert"], [])

    def test_date_de_fin_passee_refusee(self):
        client, ecr = faux_supabase()
        passe = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.assertEqual(self.code(client, d.debloquer, UUID_A, "pro", expire_le=passe), "DEBLOCAGE_DATE_INVALIDE")
        self.assertEqual(ecr["insert"], [])

    def test_source_inconnue_refusee(self):
        client, _ = faux_supabase()
        self.assertEqual(self.code(client, d.debloquer, UUID_A, "pro", source="cadeau"), "DEBLOCAGE_SOURCE_INVALIDE")

    def test_compte_introuvable(self):
        client, ecr = faux_supabase(compte_existe=False)
        self.assertEqual(self.code(client, d.debloquer, UUID_A, "pro"), "DEBLOCAGE_UTILISATEUR_INTROUVABLE")
        self.assertEqual(ecr["insert"], [])

    def test_identifiant_mal_forme(self):
        client, _ = faux_supabase()
        self.assertEqual(self.code(client, d.debloquer, "pas-un-uuid", "pro"), "DEBLOCAGE_UTILISATEUR_INVALIDE")

    def test_deblocage_ecrit_la_bonne_ligne(self):
        client, ecr = faux_supabase()
        fin = datetime.now(timezone.utc) + timedelta(days=30)
        res = self.lancer(client, d.debloquer, UUID_A, "max", UUID_ADMIN, "  test pilote  " + "x" * 600, fin)
        ligne = ecr["insert"][0]
        self.assertEqual(ligne["user_id"], UUID_A)
        self.assertEqual(ligne["palier"], "max")
        self.assertEqual(ligne["source"], "manuel")
        self.assertEqual(ligne["accorde_par"], UUID_ADMIN)
        self.assertEqual(len(ligne["motif"]), d.LONGUEUR_MAX_MOTIF)
        self.assertTrue(ligne["motif"].startswith("test pilote"))
        self.assertEqual(res["palier"], "max")

    def test_date_sans_fuseau_lue_en_utc(self):
        client, ecr = faux_supabase()
        naive = datetime.now() + timedelta(days=2)
        self.lancer(client, d.debloquer, UUID_A, "pro", expire_le=naive.replace(tzinfo=None))
        self.assertTrue(ecr["insert"][0]["expire_le"].endswith("+00:00"))

    def test_sans_date_de_fin_le_deblocage_dure(self):
        client, ecr = faux_supabase()
        self.lancer(client, d.debloquer, UUID_A, "pro")
        self.assertIsNone(ecr["insert"][0]["expire_le"])

    def test_plus_haut_palier_actif(self):
        lignes = [
            {"id": "1", "palier": "pro", "expire_le": None},
            {"id": "2", "palier": "max", "expire_le": dans(5)},
            {"id": "3", "palier": "ultra", "expire_le": dans(-1)},  # expire : ne compte pas
        ]
        client, _ = faux_supabase(lignes=lignes)
        self.assertEqual(self.lancer(client, d.palier_debloque_de, UUID_A), "max")

    def test_aucun_deblocage_actif(self):
        client, _ = faux_supabase(lignes=[{"id": "1", "palier": "ultra", "expire_le": dans(-3)}])
        self.assertIsNone(self.lancer(client, d.palier_debloque_de, UUID_A))
        client, _ = faux_supabase(lignes=[])
        self.assertIsNone(self.lancer(client, d.palier_debloque_de, UUID_A))

    def test_palier_retire_de_la_configuration_ignore(self):
        client, _ = faux_supabase(lignes=[{"id": "1", "palier": "ancien", "expire_le": None},
                                          {"id": "2", "palier": "pro", "expire_le": None}])
        self.assertEqual(self.lancer(client, d.palier_debloque_de, UUID_A), "pro")

    def test_etat_liste_les_actifs_sans_requete_en_double(self):
        client, _ = faux_supabase(lignes=[{"id": "1", "palier": "premium", "expire_le": None}])
        res = self.lancer(client, d.etat, UUID_A)
        self.assertEqual(res["palier_debloque"], "premium")
        self.assertEqual(len(res["deblocages"]), 1)
        # Une seule lecture de la table pour tout l'etat.
        self.assertEqual(client.table.call_count, 1)

    def test_revocation_compte_et_garde_les_lignes(self):
        client, ecr = faux_supabase(lignes_revoquees=[{"id": "1"}, {"id": "2"}])
        res = self.lancer(client, d.revoquer, UUID_A)
        self.assertEqual(res, {"revoques": 2})
        self.assertIn("revoque_le", ecr["update"][0])

    def test_resoudre_utilisateur_exige_exactement_un_des_deux(self):
        client, _ = faux_supabase()
        self.assertEqual(self.code(client, d.resoudre_utilisateur, None, None), "DEBLOCAGE_UTILISATEUR_INVALIDE")
        self.assertEqual(self.code(client, d.resoudre_utilisateur, UUID_A, "a@b.c"), "DEBLOCAGE_UTILISATEUR_INVALIDE")
        self.assertEqual(self.lancer(client, d.resoudre_utilisateur, UUID_A, None), UUID_A)

    def test_recherche_par_email_sans_casse(self):
        compte = SimpleNamespace(id=UUID_A, email="Boumi@Exemple.COM")
        client, _ = faux_supabase(utilisateurs=[compte])
        self.assertEqual(self.lancer(client, d.resoudre_utilisateur, None, "  boumi@exemple.com "), UUID_A)

    def test_email_inconnu(self):
        client, _ = faux_supabase(utilisateurs=[SimpleNamespace(id=UUID_A, email="autre@exemple.com")])
        self.assertEqual(self.code(client, d.resoudre_utilisateur, None, "x@exemple.com"), "DEBLOCAGE_UTILISATEUR_INTROUVABLE")

    def test_erreur_supabase_devient_un_code_stable(self):
        client = MagicMock()
        client.table.side_effect = Exception("boom")
        self.assertEqual(self.code(client, d.deblocages_actifs, UUID_A), "DEBLOCAGE_ECHEC")


class TestPalierPourModeles(unittest.TestCase):
    """Le palier qui decide des modeles qu'une personne peut choisir dans le chat."""

    def setUp(self):
        p = patch("core.deblocage_paliers.ordre_des_paliers", return_value=ORDRE_AVEC_ACCES_ANTICIPE)
        p.start()
        self.addCleanup(p.stop)

    def test_un_visiteur_sans_compte_a_le_palier_le_plus_bas(self):
        # None veut dire "le plus bas" pour modeles_disponibles_pour_agent.
        self.assertIsNone(d.palier_pour_modeles(None))
        self.assertIsNone(d.palier_pour_modeles(""))

    def test_sans_deblocage_le_palier_le_plus_bas(self):
        client, _ = faux_supabase(lignes=[])
        with patch("core.deblocage_paliers.supabase", client):
            self.assertIsNone(d.palier_pour_modeles(UUID_A))

    def test_avec_deblocage_le_plus_haut_palier(self):
        client, _ = faux_supabase(lignes=[{"id": "1", "palier": "pro", "expire_le": None},
                                          {"id": "2", "palier": "max", "expire_le": dans(3)}])
        with patch("core.deblocage_paliers.supabase", client):
            self.assertEqual(d.palier_pour_modeles(UUID_A), "max")

    def test_base_en_panne_on_ne_donne_jamais_plus(self):
        client = MagicMock()
        client.table.side_effect = Exception("boom")
        with patch("core.deblocage_paliers.supabase", client):
            self.assertIsNone(d.palier_pour_modeles(UUID_A))

    def test_le_palier_d_acces_anticipe_ne_s_accorde_pas(self):
        client, ecr = faux_supabase()
        with patch("core.deblocage_paliers.supabase", client):
            with self.assertRaises(d.ErreurDeblocage) as c:
                d.debloquer(UUID_A, "specialise")
        self.assertEqual(c.exception.code, "DEBLOCAGE_PALIER_INVALIDE")
        self.assertEqual(ecr["insert"], [])

    def test_une_ligne_specialise_deja_en_base_ne_donne_rien(self):
        client, _ = faux_supabase(lignes=[{"id": "1", "palier": "specialise", "expire_le": None}])
        with patch("core.deblocage_paliers.supabase", client):
            self.assertIsNone(d.palier_pour_modeles(UUID_A))


CLES_DEEPSEEK_SEULE = {"DEEPSEEK_API_KEY": "x"}


class TestVerrousParPalier(unittest.TestCase):
    """Tout le monde voit tous les modeles ; ceux au-dessus de son palier sont grises avec le verrou."""

    def setUp(self):
        reinitialiser_cache_config_modeles()

    def tearDown(self):
        reinitialiser_cache_config_modeles()

    def listes(self, palier, avec_verrous=True):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            dispo = modeles_disponibles_pour_agent("claude", palier)
            grises = modeles_bientot_pour_agent("claude", palier, avec_verrous_palier=avec_verrous)
        return dispo, grises

    def test_les_modeles_au_dessus_du_palier_sont_grises(self):
        dispo, grises = self.listes("pro")
        sans_verrous = self.listes("pro", avec_verrous=False)[1]
        ids_dispo = {m["modele_id"] for m in dispo}
        en_plus = [m for m in grises if m not in sans_verrous]
        self.assertTrue(en_plus, "un modele de palier superieur doit apparaitre grise")
        self.assertTrue(all(m["modele_id"] not in ids_dispo for m in en_plus))
        self.assertTrue(all(m["palier"] != "pro" for m in en_plus))
        # Meme forme que les autres modeles grises : le frontend les montre avec le verrou sans changement.
        self.assertTrue(all("libelles_bientot" in m and "label" in m and "distributeur" in m for m in en_plus))

    def test_sans_la_demande_la_liste_ne_change_pas(self):
        _, sans = self.listes("pro", avec_verrous=False)
        _, defaut = self.listes("pro", avec_verrous=False)
        self.assertEqual(sans, defaut)

    def test_au_palier_le_plus_haut_rien_de_plus_n_est_verrouille(self):
        _, avec = self.listes("ultra", avec_verrous=True)
        _, sans = self.listes("ultra", avec_verrous=False)
        self.assertEqual(avec, sans)

    def test_aucun_modele_n_apparait_deux_fois(self):
        dispo, grises = self.listes("pro")
        ids = [m["modele_id"] for m in dispo] + [m["modele_id"] for m in grises]
        self.assertEqual(len(ids), len(set(ids)))

    def test_le_palier_specialise_n_est_jamais_montre_ni_verrouille(self):
        _, grises = self.listes("pro")
        self.assertNotIn("specialise", {m["palier"] for m in grises})

    def test_un_modele_grise_ne_peut_pas_etre_impose(self):
        _, grises = self.listes("pro")
        verrouille = next(m for m in grises if m["distributeur"] == "deepseek" and m["palier"] == "max")
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            self.assertFalse(modele_id_est_autorise(verrouille["modele_id"], "claude", "pro"))
            self.assertTrue(modele_id_est_autorise(verrouille["modele_id"], "claude", "max"))


class TestVerificationDuChat(unittest.TestCase):
    """api/chat.py : le modele force par le client est revalide avec le palier de la PERSONNE."""

    def setUp(self):
        reinitialiser_cache_config_modeles()
        self.addCleanup(reinitialiser_cache_config_modeles)

    def resoudre(self, palier_personne, modele_id):
        from api import chat

        agent = MagicMock()
        agent.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"distributeur_debloque": "claude"}
        )
        with patch.object(chat, "supabase", agent), patch.object(chat, "palier_pour_modeles", return_value=palier_personne), \
                patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            return chat._resoudre_modele_force("agent-unique", modele_id, "a@b.c", UUID_A)

    def test_un_modele_de_son_palier_est_accepte_pas_un_modele_plus_haut(self):
        with patch.dict(os.environ, CLES_DEEPSEEK_SEULE, clear=True):
            haut = next(m for m in modeles_disponibles_pour_agent("claude", "max") if m["palier"] == "max")["modele_id"]
            bas = next(m for m in modeles_disponibles_pour_agent("claude", "pro") if m["palier"] == "pro")["modele_id"]
        self.assertEqual(self.resoudre("pro", bas), bas)
        self.assertIsNone(self.resoudre("pro", haut))
        self.assertEqual(self.resoudre("max", haut), haut)


class TestRoutesAdmin(unittest.TestCase):
    def test_un_non_admin_est_refuse(self):
        from api import deblocage_paliers as routes

        with patch("api.deblocage_paliers._est_admin", return_value=False):
            with self.assertRaises(HTTPException) as c:
                routes._exige_admin(SimpleNamespace(id=UUID_A))
        self.assertEqual(c.exception.status_code, 403)

    def test_un_admin_passe(self):
        from api import deblocage_paliers as routes

        with patch("api.deblocage_paliers._est_admin", return_value=True):
            routes._exige_admin(SimpleNamespace(id=UUID_ADMIN))


if __name__ == "__main__":
    unittest.main()
