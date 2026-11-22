"""
Verifie la liste d'attente des modeles Bientot (16/11/2026, demande de Bourama) : validation de
l'inscription (palier, profil, consentement), une seule ligne par utilisateur (liste unique), desinscription
et evenements de l'entonnoir. Sans appel reseau : Supabase est remplace par un faux client.
"""

import unittest
from unittest.mock import MagicMock, patch

from core import liste_attente


def faux_supabase(paliers=None, existant=None, moyens=None):
    """Faux client Supabase : memorise les ecritures par table et sert les paliers demandes."""
    paliers = paliers if paliers is not None else [{"prix_usd": 10, "credit_usd": 8, "ordre": 1},
                                                    {"prix_usd": 17, "credit_usd": 15, "ordre": 2},
                                                    {"prix_usd": 20, "credit_usd": 17, "ordre": 3}]
    ecritures = {}
    client = MagicMock()

    def table(nom):
        t = MagicMock()
        chaine = t.select.return_value.eq.return_value.order.return_value
        chaine.execute.return_value = MagicMock(
            data=(moyens if moyens is not None else [{"id": "carte", "ordre": 1}])
            if nom == "moyens_paiement_liste_attente"
            else paliers
        )
        # Inscription deja presente de l'utilisateur (liste d'attente unique).
        t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=existant or []
        )

        def upsert(ligne, **kw):
            ecritures.setdefault((nom, "upsert"), []).append((ligne, kw))
            return MagicMock()

        def insert(ligne):
            ecritures.setdefault((nom, "insert"), []).append(ligne)
            return MagicMock()

        def update(ligne):
            ecritures.setdefault((nom, "update"), []).append(ligne)
            return MagicMock()

        t.upsert.side_effect = upsert
        t.insert.side_effect = insert
        t.update.side_effect = update
        return t

    client.table.side_effect = table
    return client, ecritures


class TestInscription(unittest.TestCase):
    def inscrire(self, client, **surcharge):
        args = dict(
            user_id="u1", email="a@example.com", modele_id="claude-opus-5-5", palier_prix=17,
            profil="etudiant", consentement=True, pays="TN", whatsapp=" +216000 ", langue="fr", source="web",
        )
        args.update(surcharge)
        with patch.object(liste_attente, "supabase", client):
            return liste_attente.inscrire(**args)

    def test_premiere_inscription_ecrit_une_ligne_et_l_evenement(self):
        client, ecritures = faux_supabase()
        res = self.inscrire(client)
        self.assertEqual(res["statut"], "actif")
        self.assertEqual(res["modele_id"], "claude-opus-5-5")
        ligne = ecritures[("liste_attente_modeles", "insert")][0]
        self.assertEqual(ligne["modele_id"], "claude-opus-5-5")
        self.assertEqual(ligne["whatsapp"], "+216000")
        self.assertEqual(ecritures[("evenements_liste_attente", "insert")][0]["etape"], "inscription_validee")

    def test_deuxieme_inscription_met_a_jour_sans_changer_le_modele_d_origine(self):
        client, ecritures = faux_supabase(existant=[{"modele_id": "gpt-6-astra"}])
        res = self.inscrire(client, modele_id="claude-opus-5-5", palier_prix=20)
        self.assertEqual(res["modele_id"], "gpt-6-astra")
        self.assertNotIn(("liste_attente_modeles", "insert"), ecritures)
        mise_a_jour = ecritures[("liste_attente_modeles", "update")][0]
        self.assertEqual(mise_a_jour["palier_prix"], 20)
        self.assertNotIn("modele_id", mise_a_jour)

    def test_palier_inconnu_refuse(self):
        client, _ = faux_supabase()
        with self.assertRaises(liste_attente.ErreurListeAttente) as c:
            self.inscrire(client, palier_prix=15)
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_PALIER_INVALIDE")

    def test_profil_inconnu_refuse(self):
        client, _ = faux_supabase()
        with self.assertRaises(liste_attente.ErreurListeAttente) as c:
            self.inscrire(client, profil="autre")
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_PROFIL_INVALIDE")

    def test_profil_facultatif_et_moyen_de_paiement_enregistre(self):
        client, ecritures = faux_supabase()
        self.inscrire(client, profil=None, moyen_paiement=" carte ")
        ligne = ecritures[("liste_attente_modeles", "insert")][0]
        self.assertIsNone(ligne["profil"])
        self.assertEqual(ligne["moyen_paiement"], "carte")

    def test_moyen_de_paiement_inconnu_refuse(self):
        client, ecritures = faux_supabase()
        with self.assertRaises(liste_attente.ErreurListeAttente) as c:
            self.inscrire(client, profil=None, moyen_paiement="troc")
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_MOYEN_PAIEMENT_INVALIDE")
        self.assertNotIn(("liste_attente_modeles", "insert"), ecritures)

    def test_sans_consentement_refuse(self):
        client, ecritures = faux_supabase()
        with self.assertRaises(liste_attente.ErreurListeAttente) as c:
            self.inscrire(client, consentement=False)
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_CONSENTEMENT_REQUIS")
        self.assertNotIn(("liste_attente_modeles", "insert"), ecritures)
        self.assertNotIn(("liste_attente_modeles", "update"), ecritures)

    def test_modele_vide_refuse(self):
        client, _ = faux_supabase()
        with self.assertRaises(liste_attente.ErreurListeAttente) as c:
            self.inscrire(client, modele_id="   ")
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_MODELE_INVALIDE")

    def test_langue_et_source_inconnues_deviennent_vides(self):
        client, ecritures = faux_supabase()
        self.inscrire(client, langue="de", source="tv")
        ligne = ecritures[("liste_attente_modeles", "insert")][0]
        self.assertIsNone(ligne["langue"])
        self.assertIsNone(ligne["source"])


class TestDesinscriptionEtEvenements(unittest.TestCase):
    def test_desinscription_efface_le_whatsapp(self):
        client, ecritures = faux_supabase()
        with patch.object(liste_attente, "supabase", client):
            res = liste_attente.desinscrire("u1")
        self.assertEqual(res["statut"], "desinscrit")
        mise_a_jour = ecritures[("liste_attente_modeles", "update")][0]
        self.assertEqual(mise_a_jour["statut"], "desinscrit")
        self.assertIsNone(mise_a_jour["whatsapp"])

    def test_etape_inconnue_refusee(self):
        client, _ = faux_supabase()
        with patch.object(liste_attente, "supabase", client):
            with self.assertRaises(liste_attente.ErreurListeAttente) as c:
                liste_attente.enregistrer_evenement("u1", "autre")
        self.assertEqual(c.exception.code, "LISTE_ATTENTE_ETAPE_INVALIDE")

    def test_echec_d_ecriture_d_un_evenement_ne_leve_rien(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("base indisponible")
        with patch.object(liste_attente, "supabase", client):
            liste_attente.enregistrer_evenement("u1", "formulaire_ouvert", "m")


class TestRoutes(unittest.TestCase):
    def test_le_client_ne_peut_pas_ecrire_l_etape_inscription_validee(self):
        from fastapi import HTTPException
        from api import liste_attente as routes

        payload = routes.EvenementPayload(etape="inscription_validee")
        utilisateur = MagicMock(id="u1")
        with self.assertRaises(HTTPException) as c:
            routes.noter_evenement.__wrapped__(MagicMock(), payload, utilisateur)
        self.assertEqual(c.exception.detail["code"], "LISTE_ATTENTE_ETAPE_INVALIDE")


class TestReperesModeles(unittest.TestCase):
    """Les listes de modeles des textes de la page des abonnements viennent de la vraie table (19/11/2026)."""

    CONFIG = {
        "distributeurs": ["claude", "gpt"],
        "paliers": ["essentiel", "pro", "ultra"],
        "modeles": {
            "claude": {
                "pro": {"id": "c-petit", "label": "Claude Petit"},
                "ultra": {"id": "c-grand", "label": "Claude Grand"},
            },
            "gpt": {"pro": {"id": "g-1", "label": "GPT Un"}, "ultra": {"id": "c-grand", "label": "doublon"}},
        },
    }

    def test_noms_par_palier_dans_l_ordre_des_fournisseurs_sans_doublon(self):
        from core import fournisseurs_llm

        with patch.object(fournisseurs_llm, "_config_modeles", return_value=self.CONFIG):
            par_palier = liste_attente.noms_modeles_par_palier()
        self.assertEqual(par_palier, {"essentiel": [], "pro": ["Claude Petit", "GPT Un"], "ultra": ["Claude Grand"]})

    def test_reperes_remplaces_par_les_noms_du_palier(self):
        par_palier = {"pro": ["A", "B"], "ultra": ["C"]}
        texte = "Legers ({modeles:pro}) et frontiere : {modeles:ultra}"
        self.assertEqual(liste_attente.remplir_reperes_modeles(texte, par_palier), "Legers (A, B) et frontiere : C")

    def test_palier_inconnu_ou_lecture_en_panne_retire_le_repere_et_ses_parentheses(self):
        self.assertEqual(liste_attente.remplir_reperes_modeles("Frontiere ({modeles:ultra}) oui", {}), "Frontiere oui")

    def test_texte_sans_repere_inchange(self):
        self.assertEqual(liste_attente.remplir_reperes_modeles("Rien (a, b)", {}), "Rien (a, b)")

    def test_lire_textes_remplit_les_reperes(self):
        from core import fournisseurs_llm

        res = MagicMock()
        res.data = [{"cle": "attente_comp_x", "langue": "fr", "texte": "Haut ({modeles:ultra})"}]
        client = MagicMock()
        client.table.return_value.select.return_value.like.return_value.execute.return_value = res
        with patch.object(liste_attente, "supabase", client), patch.object(
            fournisseurs_llm, "_config_modeles", return_value=self.CONFIG
        ):
            textes = liste_attente.lire_textes()
        self.assertEqual(textes["fr"]["attente_comp_x"], "Haut (Claude Grand)")


if __name__ == "__main__":
    unittest.main()


class TestModelesPublics(unittest.TestCase):
    """Liste des modeles de la page des abonnements (19/11/2026) : meme source que le selecteur."""

    CONFIG = {
        "distributeurs": ["claude", "gpt", "vide"],
        "fournisseurs": {
            "claude": {"nom_affiche": "Anthropic"},
            "gpt": {"nom_affiche": None},
            "vide": {"nom_affiche": "Sans modele"},
        },
        "paliers": ["essentiel", "pro", "premium"],
        "modeles": {
            "claude": {
                "essentiel": {"id": "c-petit", "label": "Claude Petit", "groupe": 4},
                "premium": {"id": "c-grand", "label": "Claude Grand", "groupe": 1},
            },
            "gpt": {"essentiel": {"id": "g-1", "label": "GPT Un"}},
        },
        "textes": {"badge_groupe_1": {"fr": "Max", "en": "Max"}},
    }

    def test_groupes_par_entreprise_du_plus_puissant_au_moins_puissant(self):
        from core import fournisseurs_llm

        with patch.object(fournisseurs_llm, "_config_modeles", return_value=self.CONFIG):
            groupes = liste_attente.lister_modeles_publics()
        self.assertEqual([g["distributeur"] for g in groupes], ["claude", "gpt"])
        self.assertEqual(groupes[0]["nom"], "Anthropic")
        self.assertEqual([m["label"] for m in groupes[0]["modeles"]], ["Claude Grand", "Claude Petit"])
        self.assertEqual(groupes[0]["modeles"][0]["badge"], {"fr": "Max", "en": "Max"})
        self.assertEqual(groupes[0]["modeles"][1]["badge"], {})

    def test_nom_de_repli_et_entreprise_sans_modele_ignoree(self):
        from core import fournisseurs_llm

        with patch.object(fournisseurs_llm, "_config_modeles", return_value=self.CONFIG):
            groupes = liste_attente.lister_modeles_publics()
        self.assertEqual(groupes[1]["nom"], "gpt")
        self.assertNotIn("vide", [g["distributeur"] for g in groupes])

    def test_une_lecture_qui_echoue_donne_une_liste_vide(self):
        from core import fournisseurs_llm

        with patch.object(fournisseurs_llm, "_config_modeles", side_effect=RuntimeError("panne")):
            self.assertEqual(liste_attente.lister_modeles_publics(), [])
