"""
Etat des connexions pour l'IA (26/10/2026, demande de Bourama) : l'IA distingue les outils de
Classinus, les services fournis par notre API, les services que l'utilisateur connecte, et ses
MCP personnels, et propose un service pas encore connecte au lieu de dire qu'il n'existe pas.
"""

import json
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.append("core")  # comme les autres tests
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SECRET", "test")

import boucle_agent  # noqa: E402
import efforts_modeles  # noqa: E402
import etat_connexions as ec  # noqa: E402
import registre_outils as r  # noqa: E402
from core.adaptateur_responses import ClientResponses  # noqa: E402

NS = types.SimpleNamespace

TOUS_NON_CONNECTES = {s["service"]: ec.NON_CONNECTE for s in r.SERVICES_CONNECTABLES if s["proposable"]}


def _etats(**connectes):
    etats = dict(TOUS_NON_CONNECTES)
    for service in connectes:
        etats[service] = ec.CONNECTE
    return etats


class RegistreDesServices(unittest.TestCase):
    def test_chaque_service_propose_a_une_categorie_connue(self):
        for entree in r.SERVICES_CONNECTABLES:
            self.assertIn(entree["categorie"], r.NOMS_CATEGORIES_OUTILS, entree["service"])

    def test_les_services_masques_dans_l_ecran_connexions_ne_sont_pas_proposables(self):
        # Meme decision que lib/outils.ts : Google Workspace en previsualisation et Drive restent masques.
        for service in ("google_drive", "google_gmail_mcp", "google_docs_mcp"):
            self.assertFalse(next(s for s in r.SERVICES_CONNECTABLES if s["service"] == service)["proposable"])

    def test_services_sans_doublon(self):
        noms = [s["service"] for s in r.SERVICES_CONNECTABLES]
        self.assertEqual(len(noms), len(set(noms)))


class RetrouverUnServiceNonConnecte(unittest.TestCase):
    def _noms(self, besoin, etats=None, **kw):
        return [e["service"] for e in ec.services_a_proposer(besoin, etats or dict(TOUS_NON_CONNECTES), **kw)]

    def test_deployer_un_site_propose_une_plateforme_de_deploiement(self):
        noms = self._noms("deployer mon site web")
        self.assertTrue({"vercel_mcp", "netlify_mcp"} & set(noms), noms)

    def test_requete_sur_une_base_de_donnees_propose_supabase(self):
        self.assertIn("supabase_mcp", self._noms("interroger ma base de données avec une requête sql"))

    def test_nom_du_service_dans_le_besoin_suffit(self):
        self.assertEqual(self._noms("regarde mon projet vercel")[0], "vercel_mcp")

    def test_un_mot_general_seul_ne_propose_rien(self):
        for besoin in ("lis ce fichier", "ouvre cette page", "fais un site", "bonjour"):
            self.assertEqual(self._noms(besoin), [], besoin)

    def test_un_service_deja_connecte_n_est_jamais_propose(self):
        noms = self._noms("deployer mon site web sur vercel", _etats(vercel_mcp=True))
        self.assertNotIn("vercel_mcp", noms)

    def test_etat_inconnu_n_est_jamais_propose(self):
        etats = dict(TOUS_NON_CONNECTES, vercel_mcp=ec.INCONNU)
        self.assertNotIn("vercel_mcp", self._noms("projet vercel", etats))

    def test_connexion_expiree_est_proposee(self):
        etats = dict(TOUS_NON_CONNECTES, vercel_mcp=ec.A_RECONNECTER)
        self.assertIn("vercel_mcp", self._noms("projet vercel", etats))

    def test_service_masque_jamais_propose(self):
        etats = dict(TOUS_NON_CONNECTES, google_gmail_mcp=ec.NON_CONNECTE)
        self.assertEqual(self._noms("envoie un mail gmail", etats), [])

    def test_maximum(self):
        self.assertLessEqual(len(self._noms("deployer site hebergement backend serveur logs", maximum=2)), 2)


class TextesPourLIA(unittest.TestCase):
    def test_la_proposition_contient_le_bloc_exact_et_dit_que_le_service_existe(self):
        entree = next(s for s in r.SERVICES_CONNECTABLES if s["service"] == "vercel_mcp")
        texte = ec.texte_proposition(entree, ec.NON_CONNECTE)
        self.assertIn('```connecteur\n{"service": "vercel_mcp"}\n```', texte)
        self.assertIn("Ne dis jamais qu'il n'existe pas", texte)
        self.assertNotIn("--", texte)

    def test_serveur_inconnu_demande_le_bloc_et_jamais_de_jeton_dans_le_chat(self):
        texte = ec.texte_serveur_inconnu()
        self.assertIn("```serveurmcp", texte)
        self.assertIn("site officiel", texte)
        self.assertIn("tu n'ajoutes jamais rien", texte)
        self.assertIn("ne demandes jamais de jeton dans le chat", texte)
        self.assertNotIn("--", texte)

    def test_quand_proposer_un_serveur_mcp(self):
        # Rien trouvé du tout : on propose de chercher un serveur.
        self.assertTrue(ec.doit_proposer_serveur_mcp(["envoyer un mail"], False, False))
        # Des outils ou un service de la liste répondent déjà : on ne propose rien de plus.
        self.assertFalse(ec.doit_proposer_serveur_mcp(["déployer un site"], True, False))
        self.assertFalse(ec.doit_proposer_serveur_mcp(["déployer un site"], False, True))
        # L'utilisateur demande lui-même d'ajouter un serveur MCP : toujours.
        self.assertTrue(ec.doit_proposer_serveur_mcp(["ajouter un serveur MCP"], True, True))

    def test_serveur_inconnu_change_de_debut_selon_le_cas(self):
        self.assertIn("Aucun outil de Classinus", ec.texte_serveur_inconnu(aucun_outil=True))
        texte = ec.texte_serveur_inconnu(aucun_outil=False)
        self.assertNotIn("Aucun outil de Classinus", texte)
        self.assertIn("Si l'utilisateur veut ajouter", texte)

    def test_le_prompt_dit_a_l_ia_de_proposer_un_serveur_sans_l_ajouter_elle_meme(self):
        texte = ec.texte_prompt_connexions(_etats(), [])
        self.assertIn("serveur MCP", texte)
        self.assertIn("c'est lui qui", texte)

    def test_la_proposition_distingue_une_connexion_expiree(self):
        entree = next(s for s in r.SERVICES_CONNECTABLES if s["service"] == "vercel_mcp")
        self.assertIn("expiré", ec.texte_proposition(entree, ec.A_RECONNECTER))

    def test_bloc_du_prompt_nomme_les_connectes_sans_lister_les_autres(self):
        texte = ec.texte_prompt_connexions(_etats(notion=True, vercel_mcp=True), [])
        self.assertIn("Notion, Vercel", texte)
        for absent in ("Railway", "Supabase", "Netlify"):
            self.assertNotIn(absent, texte.split("Les autres services")[0])
        self.assertIn("aucun pour l'instant", texte)
        self.assertNotIn("--", texte)

    def test_bloc_du_prompt_donne_l_etat_de_chaque_mcp_personnel(self):
        perso = [
            {"nom": "Mon CRM", "etat": "actif", "nb_outils": 4},
            {"nom": "Render perso", "etat": "desactive", "nb_outils": 0},
            {"nom": "Wiki", "etat": "injoignable", "nb_outils": 0},
        ]
        texte = ec.texte_prompt_connexions(_etats(), perso)
        self.assertIn("Mon CRM (actif)", texte)
        self.assertIn("Render perso (désactivé", texte)
        self.assertIn("Wiki (injoignable", texte)
        self.assertIn("serveurs_personnalises", texte)

    def test_bloc_du_prompt_annonce_une_connexion_expiree(self):
        etats = dict(TOUS_NON_CONNECTES, railway_mcp=ec.A_RECONNECTER)
        self.assertIn("Connexion expirée, à refaire : Railway", ec.texte_prompt_connexions(etats, []))

    def test_les_quatre_familles_et_la_priorite_de_l_utilisateur_sont_dites(self):
        texte = ec.texte_prompt_connexions(_etats(), [])
        for numero in ("1.", "2.", "3.", "4."):
            self.assertIn(numero, texte)
        self.assertIn("celle du compte de l'utilisateur", texte)


class VersionsDoubles(unittest.TestCase):
    NOMS_DEUX = ["higgsfield_generate_video", "lancer_video_higgsfield", "consulter_video_higgsfield"]

    def test_deux_versions_et_compte_connecte_donne_la_priorite_a_l_utilisateur(self):
        note = ec.note_versions_doubles(self.NOMS_DEUX, _etats(higgsfield_mcp=True))
        self.assertIn("deux versions", note)
        self.assertIn("Utilise d'abord celle du compte de l'utilisateur", note)

    def test_seulement_la_version_de_classinus_pas_de_note(self):
        self.assertEqual(ec.note_versions_doubles(self.NOMS_DEUX[1:], _etats(higgsfield_mcp=True)), "")

    def test_compte_pas_connecte_pas_de_note(self):
        self.assertEqual(ec.note_versions_doubles(self.NOMS_DEUX, _etats()), "")


def _outil(nom, description=""):
    return {"type": "function", "function": {"name": nom, "description": description, "parameters": {"type": "object", "properties": {}, "required": []}}}


def _element(type_element, **champs):
    return NS(type=type_element, model_dump=lambda exclude_none=True: {"type": type_element, **champs}, **champs)


def _jouer_demander_outils(recherches, catalogue, etats, user_id="u1"):
    """Joue la vraie boucle avec un faux fournisseur, renvoie (reponse de l'outil, evenements)."""
    arguments = json.dumps({"recherches": recherches})
    appels = []
    tours = [
        [
            NS(type="response.output_item.added", item=NS(type="function_call", id="fc_1", call_id="c1", name="demander_outils")),
            NS(type="response.function_call_arguments.delta", item_id="fc_1", delta=arguments),
            NS(type="response.output_item.done", item=_element("function_call", id="fc_1", call_id="c1", name="demander_outils", arguments=arguments)),
        ],
        [NS(type="response.output_text.delta", delta="Ok."), NS(type="response.completed")],
    ]

    def creer(**kwargs):
        appels.append(kwargs)
        return iter(tours[len(appels) - 1])

    client = ClientResponses("cle", "openai")
    client._client = NS(responses=NS(create=creer))
    params = {"budget_depart": 5, "palier_extension": 5, "plafond_absolu": 10, "tolerance_repetition": 3}
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "Demande"}]
    with patch.object(boucle_agent, "parametres_outils", return_value=params), \
            patch.object(efforts_modeles, "distributeur_du_modele", return_value="gpt"), \
            patch.object(boucle_agent, "retirer_messages_etudiant", return_value=[]), \
            patch.object(boucle_agent, "plafond_tour", return_value=None), \
            patch.object(ec, "etats_connexions", return_value=etats):
        evenements = list(boucle_agent._agent_groq(
            client, messages, [_outil("demander_outils")], {}, modele="gpt-6-astra", reasoning_effort="none",
            catalogue_complet=catalogue, table_routage_complet={o["function"]["name"]: {} for o in catalogue},
            user_id=user_id,
        ))
    return [m for m in messages if m["role"] == "tool"][0]["content"], evenements


CATALOGUE_SANS_VERCEL = [
    _outil("generer_image", "creer une image"),
    _outil("notion-search", "rechercher dans notion"),
    _outil("lancer_video_higgsfield", "version Classinus de higgsfield : lance une video"),
    _outil("consulter_video_higgsfield", "version Classinus de higgsfield : suit une video"),
]


class DansLaBoucleDemanderOutils(unittest.TestCase):
    def test_categorie_d_un_service_non_connecte_propose_la_connexion_au_lieu_de_dire_que_rien_n_existe(self):
        reponse, evenements = _jouer_demander_outils(
            [{"besoin": "voir mes deploiements", "categorie": "vercel"}], CATALOGUE_SANS_VERCEL, _etats())
        self.assertIn('```connecteur\n{"service": "vercel_mcp"}\n```', reponse)
        self.assertNotIn("n'existe dans le catalogue", reponse)
        detail = [e for e in evenements if e.get("type") == "outil_resultat" and e.get("nom_outil") == "demander_outils"][0]["resultat"]
        self.assertIn("Vercel : pas connecté", detail)

    def test_besoin_libre_sans_categorie_retrouve_le_service_non_connecte(self):
        reponse, _ = _jouer_demander_outils([{"besoin": "deployer mon site sur internet"}], CATALOGUE_SANS_VERCEL, _etats())
        self.assertIn('"service": "vercel_mcp"', reponse)

    def test_service_connecte_n_est_pas_propose(self):
        catalogue = CATALOGUE_SANS_VERCEL + [_outil("vercel_list_projects", "liste les projets vercel")]
        reponse, _ = _jouer_demander_outils(
            [{"besoin": "voir mes projets", "categorie": "vercel"}], catalogue, _etats(vercel_mcp=True))
        self.assertIn("vercel_list_projects", reponse)
        self.assertNotIn("connecteur", reponse)

    def test_la_version_de_classinus_trouvee_ne_declenche_pas_de_proposition_pour_higgsfield(self):
        reponse, _ = _jouer_demander_outils(
            [{"besoin": "generer une video", "categorie": "higgsfield_classinus"}], CATALOGUE_SANS_VERCEL, _etats())
        self.assertIn("lancer_video_higgsfield", reponse)
        self.assertNotIn("connecteur", reponse)

    def test_categorie_higgsfield_compte_utilisateur_non_connecte_propose_la_connexion(self):
        reponse, _ = _jouer_demander_outils(
            [{"besoin": "generer une image", "categorie": "higgsfield"}], CATALOGUE_SANS_VERCEL, _etats())
        self.assertIn('"service": "higgsfield_mcp"', reponse)

    def test_les_deux_versions_trouvees_donnent_la_priorite_a_l_utilisateur(self):
        catalogue = CATALOGUE_SANS_VERCEL + [_outil("higgsfield_generate_video", "genere une video")]
        reponse, _ = _jouer_demander_outils(
            [{"besoin": "generer une video higgsfield"}], catalogue, _etats(higgsfield_mcp=True))
        self.assertIn("deux versions", reponse)
        self.assertIn("celle du compte de l'utilisateur", reponse)

    def test_visiteur_sans_compte_garde_l_ancienne_reponse(self):
        reponse, _ = _jouer_demander_outils(
            [{"besoin": "voir mes deploiements", "categorie": "vercel"}], CATALOGUE_SANS_VERCEL, {}, user_id=None)
        self.assertNotIn("connecteur", reponse)

    def test_aucune_reponse_ne_contient_de_double_tiret(self):
        reponse, _ = _jouer_demander_outils([{"besoin": "projet vercel", "categorie": "vercel"}], CATALOGUE_SANS_VERCEL, _etats())
        self.assertNotIn("--", reponse)


if __name__ == "__main__":
    unittest.main()
