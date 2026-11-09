"""Tests du parrainage (09/11/2026).

Règles verrouillées : le parrain n'est crédité qu'après confirmation de l'email, jamais pour un email
jetable, une variante d'un email connu ou un auto-parrainage ; le motif d'un refus n'est jamais donné
à la personne ; rien n'est écrit en dur (gain, solde de départ et fenêtre se règlent en base) ; les
messages existent en français et en anglais. Aucun appel réseau ni base : un faux client Supabase
suffit (la logique SQL est vérifiée séparément sur la base de test).
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.erreurs import MESSAGES_EN, MESSAGES_FR
from core.parrainage import (
    ErreurParrainage,
    LONGUEUR_MAX_CODE,
    enregistrer_parrainage,
    resume_parrainage,
)

RACINE = Path(__file__).parent


class _Reponse:
    def __init__(self, data):
        self.data = data


class _Appel:
    def __init__(self, client, nom, parametres):
        self.client, self.nom, self.parametres = client, nom, parametres

    def execute(self):
        self.client.appels.append((self.nom, self.parametres))
        if self.client.erreur is not None:
            raise self.client.erreur
        return _Reponse(self.client.reponse)


class FauxClient:
    def __init__(self, reponse=None, erreur=None):
        self.reponse, self.erreur, self.appels = reponse, erreur, []

    def rpc(self, nom, parametres):
        return _Appel(self, nom, parametres)


class TestEnregistrer(unittest.TestCase):
    def test_appelle_la_fonction_sql_avec_le_filleul_et_le_code(self):
        client = FauxClient({"statut": "valide", "motif": None})
        resultat = enregistrer_parrainage(client, "user-1", "  ab12cd34 ")
        self.assertEqual(resultat, {"statut": "valide"})
        self.assertEqual(client.appels, [("parrainage_enregistrer", {"p_filleul": "user-1", "p_code": "ab12cd34"})])

    def test_les_quatre_statuts_sont_transmis(self):
        for statut in ("valide", "en_attente", "refuse", "ignore"):
            client = FauxClient({"statut": statut, "motif": "x"})
            self.assertEqual(enregistrer_parrainage(client, "u", "CODE"), {"statut": statut})

    def test_le_motif_du_refus_n_est_jamais_donne_a_la_personne(self):
        for motif in ("email_jetable", "email_deja_connu", "auto_parrainage", "code_inconnu"):
            client = FauxClient({"statut": "refuse", "motif": motif})
            self.assertNotIn("motif", enregistrer_parrainage(client, "u", "CODE"))

    def test_code_vide_ou_trop_long_refuse_sans_toucher_la_base(self):
        for code in ("", "   ", None, "A" * (LONGUEUR_MAX_CODE + 1)):
            client = FauxClient({"statut": "valide"})
            with self.assertRaises(ErreurParrainage) as ctx:
                enregistrer_parrainage(client, "u", code)
            self.assertEqual(ctx.exception.code, "PARRAINAGE_CODE_INVALIDE")
            self.assertEqual(client.appels, [])

    def test_sans_utilisateur_refuse_sans_toucher_la_base(self):
        client = FauxClient({"statut": "valide"})
        with self.assertRaises(ErreurParrainage) as ctx:
            enregistrer_parrainage(client, None, "CODE")
        self.assertEqual(ctx.exception.code, "PARRAINAGE_INDISPONIBLE")
        self.assertEqual(client.appels, [])

    def test_base_en_panne_donne_une_erreur_claire(self):
        client = FauxClient(erreur=RuntimeError("boom"))
        with self.assertRaises(ErreurParrainage) as ctx:
            enregistrer_parrainage(client, "u", "CODE")
        self.assertEqual(ctx.exception.code, "PARRAINAGE_INDISPONIBLE")

    def test_reponse_inattendue_refusee(self):
        for reponse in (None, True, "valide", {}, {"statut": "inconnu"}):
            with self.assertRaises(ErreurParrainage):
                enregistrer_parrainage(FauxClient(reponse), "u", "CODE")


class TestResume(unittest.TestCase):
    def test_renvoie_code_solde_et_filleuls(self):
        client = FauxClient({"code": "ABCD2345", "solde": 20, "filleuls_valides": 2, "filleuls_en_attente": 1})
        self.assertEqual(
            resume_parrainage(client, "u"),
            {"code": "ABCD2345", "solde": 20, "filleuls_valides": 2, "filleuls_en_attente": 1},
        )
        self.assertEqual(client.appels, [("parrainage_resume", {"p_user": "u"})])

    def test_base_en_panne_donne_une_erreur_claire(self):
        with self.assertRaises(ErreurParrainage) as ctx:
            resume_parrainage(FauxClient(erreur=RuntimeError("boom")), "u")
        self.assertEqual(ctx.exception.code, "PARRAINAGE_INDISPONIBLE")

    def test_reponse_sans_code_refusee(self):
        for reponse in (None, {}, {"solde": 10}):
            with self.assertRaises(ErreurParrainage):
                resume_parrainage(FauxClient(reponse), "u")

    def test_sans_utilisateur_refuse(self):
        with self.assertRaises(ErreurParrainage):
            resume_parrainage(FauxClient({"code": "X"}), None)


class TestMessages(unittest.TestCase):
    CODES = ("PARRAINAGE_CODE_INVALIDE", "PARRAINAGE_INDISPONIBLE")

    def test_chaque_code_a_un_texte_francais_et_anglais(self):
        for code in self.CODES:
            self.assertTrue(MESSAGES_FR.get(code), f"{code} sans texte français")
            self.assertTrue(MESSAGES_EN.get(code), f"{code} sans texte anglais")

    def test_aucun_chiffre_ecrit_en_dur(self):
        # Le gain par filleul se règle en base : jamais écrit dans un message.
        for code in self.CODES:
            self.assertNotRegex(MESSAGES_FR[code], r"\d")
            self.assertNotRegex(MESSAGES_EN[code], r"\d")


class TestCablage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = (RACINE / "api" / "parrainage.py").read_text(encoding="utf-8")
        cls.main = (RACINE / "api" / "main.py").read_text(encoding="utf-8")
        cls.sql = (RACINE / "migrations" / "2026_11_09_parrainage_fonctions.sql").read_text(encoding="utf-8")

    def test_le_routeur_est_enregistre(self):
        self.assertIn("from api.parrainage import router as parrainage_router", self.main)
        self.assertIn("app.include_router(parrainage_router)", self.main)

    def test_les_routes_exigent_un_utilisateur_connecte_et_sont_limitees(self):
        self.assertEqual(self.api.count("Depends(utilisateur_courant)"), 2)
        self.assertEqual(self.api.count("@limiteur.limit("), 2)

    def test_les_codes_d_erreur_du_routeur_ont_un_message(self):
        for code in re.findall(r'"(PARRAINAGE_[A-Z_]+)"', self.api):
            self.assertIn(code, MESSAGES_FR)
            self.assertIn(code, MESSAGES_EN)

    def test_les_fonctions_sql_sont_reservees_au_backend(self):
        for fonction in ("parrainage_generer_code()", "parrainage_profil_assurer(uuid)", "parrainage_enregistrer(uuid, text)", "parrainage_resume(uuid)"):
            self.assertIn(f"revoke all on function public.{fonction} from public, anon, authenticated;", self.sql)
            self.assertIn(f"grant execute on function public.{fonction} to service_role;", self.sql)

    def test_le_gain_et_le_depart_se_lisent_en_base(self):
        self.assertIn("'credits_par_filleul'", self.sql)
        self.assertIn("'credits_depart'", self.sql)

    def test_le_parrain_n_est_credite_qu_apres_confirmation_de_l_email(self):
        confirmation = self.sql.index("if v_confirme is null then")
        credit = self.sql.index("'parrainage', p_filleul::text")
        self.assertLess(confirmation, credit)

    def test_un_parrain_n_est_credite_qu_une_fois_par_filleul(self):
        self.assertIn("uq_credits_parrainage_reference", self.sql)


if __name__ == "__main__":
    unittest.main()
