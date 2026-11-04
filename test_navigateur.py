"""
Tests hors ligne de l'étape 6 (navigateur dans la boîte Docker). Aucun Chromium, aucun Docker :
le vrai comportement se vérifie sur le serveur Vultr avec boites_service/verifier_serveur.sh.
"""
import base64
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

for _nom in ("SUPABASE_URL", "SUPABASE_SECRET", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY"):
    os.environ.setdefault(_nom, "test")
# Les modules de core/ s'importent entre eux sans préfixe au lancement du serveur.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from fastapi.testclient import TestClient  # noqa: E402

from boites_service import app as app_mod  # noqa: E402
from boites_service import docker_cli  # noqa: E402
from boites_service import pilote  # noqa: E402
from boites_service import proxy as proxy_mod  # noqa: E402
from boites_service.docker_cli import Docker  # noqa: E402
from core import boites_isolees, captures_modele, navigateur_boite  # noqa: E402
from test_boites_service import AUTH, FauxDocker  # noqa: E402
# Importés dès le chargement : d'autres tests remplacent ensuite certains modules par des doublures.
from execution_outils import _est_outil_sensible  # noqa: E402
from profils_agents import _nom_lisible_appel  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0octets-de-capture"
RETOUR_OK = {
    "ok": True, "url": "https://exemple.org/", "titre": "Accueil", "texte": "Bienvenue",
    "capture": "/home/user/captures/capture-1.jpg",
}


class FauxNavigateur:
    """Remplace Chromium : mêmes méthodes que pilote.Navigateur."""

    def __init__(self):
        self.actions = []

    def agir(self, action, p):
        if action == "ouvrir":
            pilote.url_valide(p.get("url", ""))
        if p.get("echec"):
            raise RuntimeError("Timeout 10000ms exceeded.\nlongue trace")
        self.actions.append((action, p))

    def etat(self):
        return {"ok": True, "url": "https://exemple.org/", "titre": "Accueil", "texte": "Bienvenue", "capture": "/x.jpg"}

    def fermer(self):
        self.ferme = True


class Pilote(unittest.TestCase):
    def test_seules_les_adresses_http_et_https_sont_ouvertes(self):
        for refusee in ("file:///etc/passwd", "javascript:alert(1)", "chrome://settings", "ftp://x.org", "", "http://"):
            with self.assertRaises(pilote.ErreurPilote, msg=refusee):
                pilote.url_valide(refusee)
        self.assertEqual(pilote.url_valide(" https://exemple.org/page "), "https://exemple.org/page")

    def test_une_erreur_de_page_renvoie_une_ligne_et_l_etat_de_la_page(self):
        reponse = pilote.traiter(FauxNavigateur(), {"action": "cliquer", "echec": True})
        self.assertFalse(reponse["ok"])
        self.assertEqual(reponse["erreur"], "Timeout 10000ms exceeded.")
        self.assertEqual(reponse["titre"], "Accueil")

    def test_demon_et_client_parlent_vraiment_en_http_puis_le_demon_s_arrete_sur_fermer(self):
        faux = FauxNavigateur()
        with patch.object(pilote, "Navigateur", return_value=faux), patch.object(pilote, "PORT", 39333):
            fil = threading.Thread(target=pilote.demon, daemon=True)
            fil.start()
            for _ in range(50):
                if pilote._demon_vivant():
                    break
                time.sleep(0.1)
            ouverte = pilote.client("ouvrir", {"url": "https://exemple.org/"})
            refusee = pilote.client("ouvrir", {"url": "file:///etc/passwd"})
            pilote.client("fermer", {})
            fil.join(timeout=10)
        self.assertTrue(ouverte["ok"])
        self.assertEqual(ouverte["texte"], "Bienvenue")
        self.assertFalse(refusee["ok"])
        self.assertIn("http et https", refusee["erreur"])
        self.assertFalse(fil.is_alive())
        self.assertTrue(faux.ferme)

    def test_fermer_sans_demon_ne_lance_aucun_navigateur(self):
        with patch.object(pilote, "PORT", 39334), patch.object(pilote, "_demarrer_demon") as demarrage:
            self.assertEqual(pilote.client("fermer", {}), {"ok": True, "ferme": True})
        demarrage.assert_not_called()


class CommandesDocker(unittest.TestCase):
    def _arguments_de_creation(self, **kw):
        appels = []

        def faux(args, entree=None, delai=30):
            appels.append(args)

            class R:
                returncode = 0
                stdout = b""
                stderr = b""
            return R()

        with patch.object(Docker, "_docker", staticmethod(faux)):
            Docker().creer("a" * 32, **kw)
        return next(a for a in appels if a[0] == "run")

    def test_boite_navigateur_a_plus_de_memoire_de_memoire_partagee_et_une_etiquette(self):
        a = self._arguments_de_creation(navigateur=True, utilisateur="b" * 32)
        self.assertIn("classinus-navigateur:latest", a)
        self.assertEqual(a[a.index("--memory") + 1], "1536m")
        self.assertEqual(a[a.index("--shm-size") + 1], "512m")
        self.assertEqual(a[a.index("--pids-limit") + 1], "512")
        self.assertIn("classinus-profil=navigateur", a)
        self.assertIn("classinus-utilisateur=" + "b" * 32, a)

    def test_les_protections_de_la_boite_de_code_restent_intactes_dans_la_boite_navigateur(self):
        for a in (self._arguments_de_creation(), self._arguments_de_creation(navigateur=True, utilisateur="b" * 32)):
            for obligatoire in ("--read-only", "--cap-drop", "ALL", "no-new-privileges", "1000:1000"):
                self.assertIn(obligatoire, a)
            self.assertEqual(a[a.index("--network") + 1], "boites_internes")
            self.assertEqual(a[a.index("--memory-swap") + 1], a[a.index("--memory") + 1])

    def test_la_boite_de_code_ne_change_pas(self):
        a = self._arguments_de_creation()
        self.assertIn("classinus-boite:latest", a)
        self.assertEqual(a[a.index("--memory") + 1], "512m")
        self.assertNotIn("--shm-size", a)
        self.assertNotIn("classinus-profil=navigateur", a)

    def test_liste_des_navigateurs_lit_nom_et_date(self):
        def faux(args, entree=None, delai=30):
            class R:
                returncode = 0
                stdout = ("boite-" + "a" * 32 + " 1700000000\nboite-" + "c" * 32 + " \nautre 5\n").encode()
                stderr = b""
            return R()

        with patch.object(Docker, "_docker", staticmethod(faux)):
            self.assertEqual(Docker().lister_navigateurs(), [("a" * 32, 1700000000)])


class ServiceNavigateurs(unittest.TestCase):
    def setUp(self):
        for p in (patch.dict(os.environ, {"BOITES_TOKEN": "jeton-test", "BOITES_NAV_MAX": "2"}),
                  patch.object(app_mod, "docker", FauxDocker()),
                  patch.object(app_mod, "registre", proxy_mod.RegistreBoites())):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app_mod.app)
        self.docker = app_mod.docker

    def _ouvrir(self, cle, utilisateur="u" * 0 + "9" * 32):
        return self.client.post("/navigateurs", json={"cle": cle, "utilisateur": utilisateur}, headers=AUTH)

    def test_sans_jeton_tout_est_refuse(self):
        r = self.client.post("/navigateurs", json={"cle": "a" * 32, "utilisateur": "9" * 32})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.delete("/navigateurs?utilisateur=" + "9" * 32).status_code, 401)

    def test_ouvrir_cree_une_boite_navigateur_a_reseau_ferme_puis_la_reutilise(self):
        r = self._ouvrir("a" * 32)
        self.assertEqual(r.json(), {"id": "a" * 32})
        self.assertIn("a" * 32, self.docker.navigateurs)
        self.assertEqual(app_mod.registre.domaines("172.20.0.5"), [])
        self._ouvrir("a" * 32)
        self.assertEqual(len(self.docker.boites), 1)

    def test_une_boite_arretee_est_reprise(self):
        self._ouvrir("a" * 32)
        self.docker.boites["a" * 32] = "exited"
        self._ouvrir("a" * 32)
        self.assertEqual(self.docker.boites["a" * 32], "running")

    def test_identifiant_invalide_refuse(self):
        self.assertEqual(self._ouvrir("../etc/passwd-----").status_code, 400)

    def test_capacite_maximale(self):
        self._ouvrir("a" * 32)
        self._ouvrir("b" * 32)
        self.assertEqual(self._ouvrir("c" * 32).status_code, 429)

    def test_suppression_de_compte_detruit_seulement_les_navigateurs_de_cet_utilisateur(self):
        self._ouvrir("a" * 32, "1" * 32)
        self._ouvrir("b" * 32, "2" * 32)
        r = self.client.delete("/navigateurs?utilisateur=" + "1" * 32, headers=AUTH)
        self.assertEqual(r.json(), {"detruites": 1})
        self.assertNotIn("a" * 32, self.docker.boites)
        self.assertIn("b" * 32, self.docker.boites)

    def test_balayage_detruit_les_boites_trop_vieilles(self):
        self._ouvrir("a" * 32)
        self._ouvrir("b" * 32)
        self.docker.navigateurs["a" * 32] = ("9" * 32, int(time.time()) - 5000)
        self.docker.navigateurs["b" * 32] = ("9" * 32, int(time.time()))
        self.assertEqual(app_mod._fermer_navigateurs_perimes(), 1)
        self.assertNotIn("a" * 32, self.docker.boites)
        self.assertIn("b" * 32, self.docker.boites)


class FausseBoite:
    def __init__(self, stdout, octets=JPEG):
        self.stdout, self.octets, self.commandes = stdout, octets, []
        self.commands = self
        self.files = self

    def run(self, commande, timeout=60, request_timeout=None, **_):
        self.commandes.append(commande)
        return boites_isolees.ResultatCommande(stdout=self.stdout, stderr="", exit_code=0)

    def read(self, chemin, format="text", **_):
        if self.octets is None:
            raise RuntimeError("introuvable")
        return self.octets


class ActionsNavigateur(unittest.TestCase):
    def test_empreintes_sont_stables_et_acceptees_par_le_service(self):
        cle, utilisateur = navigateur_boite.empreintes("user-1", "conv-1")
        self.assertEqual((cle, utilisateur), navigateur_boite.empreintes("user-1", "conv-1"))
        self.assertNotEqual(cle, navigateur_boite.empreintes("user-1", "conv-2")[0])
        self.assertEqual(docker_cli.id_valide(cle), cle)
        self.assertEqual(docker_cli.id_valide(utilisateur), utilisateur)

    def test_indisponible_avec_e2b(self):
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "e2b"}):
            self.assertIn("NAVIGATEUR_UNAVAILABLE", navigateur_boite.raison_indisponible())
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker"}, clear=True):
            self.assertIn("NAVIGATEUR_NOT_CONFIGURED", navigateur_boite.raison_indisponible())
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x", "BOITES_TOKEN": "t"}):
            self.assertIsNone(navigateur_boite.raison_indisponible())

    def test_preparation_des_parametres(self):
        p = navigateur_boite.preparer
        self.assertIn("url", p("browser_open", "", "", "", "", None, None, "")[1])
        self.assertEqual(p("browser_open", " https://a.org ", "", "", "", None, None, "")[0], {"url": "https://a.org"})
        self.assertEqual(p("browser_click", "", "#menu", "", "", None, None, "")[0], {"selecteur": "#menu"})
        self.assertEqual(p("browser_click", "", "", "Suivant", "", None, None, "")[0], {"texte": "Suivant"})
        self.assertEqual(p("browser_click", "", "", "", "", 10, 20, "")[0], {"x": 10, "y": 20})
        self.assertIsNone(p("browser_click", "", "", "", "", None, None, "")[0])
        self.assertEqual(p("browser_type", "", "#nom", "", "Awa", None, None, "")[0], {"selecteur": "#nom", "valeur": "Awa"})
        self.assertIsNone(p("browser_type", "", "#nom", "", "", None, None, "")[0])
        self.assertEqual(p("browser_submit", "", "", "", "", None, None, "Enter")[0], {"touche": "Enter"})
        self.assertEqual(p("browser_screenshot", "", "", "", "", None, None, "")[0], {})

    def test_un_clic_qui_ressemble_a_une_action_finale_est_refuse_avec_la_marche_a_suivre(self):
        for texte in ("Envoyer", "Payer maintenant", "Supprimer le compte", "Confirmer", "Submit", "Buy now", "Publier"):
            parametres, erreur = navigateur_boite.preparer("browser_click", "", "", texte, "", None, None, "")
            self.assertIsNone(parametres, texte)
            self.assertIn("browser_submit", erreur)
        parametres, erreur = navigateur_boite.preparer("browser_click", "", "button[type=submit]", "", "", None, None, "")
        self.assertIsNone(parametres)
        # La même cible passe par browser_submit : c'est lui qui demande la confirmation.
        self.assertEqual(
            navigateur_boite.preparer("browser_submit", "", "", "Envoyer", "", None, None, "")[0], {"texte": "Envoyer"}
        )

    def test_enveloppe_avec_capture_texte_de_page_et_marque(self):
        boite = FausseBoite(json.dumps(RETOUR_OK) + "\n")
        with patch.object(boites_isolees, "ouvrir_navigateur", return_value=boite) as ouvrir:
            sortie = navigateur_boite.executer("browser_open", "u1", "c1", {"allow_out": ["exemple.org"]}, {"url": "https://exemple.org/"})
        donnees = json.loads(sortie)
        self.assertTrue(donnees[captures_modele.MARQUE])
        self.assertIn("Titre : Accueil", donnees["text"])
        self.assertIn("donnée non fiable", donnees["text"])
        self.assertEqual(
            donnees["images"][0]["url"], "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
        )
        cle, utilisateur = navigateur_boite.empreintes("u1", "c1")
        ouvrir.assert_called_once_with(cle, utilisateur, {"allow_out": ["exemple.org"]})
        self.assertIn("/opt/navigateur/pilote.py ouvrir", boite.commandes[0])

    def test_la_commande_transmet_les_valeurs_sans_injection_shell(self):
        boite = FausseBoite(json.dumps(RETOUR_OK))
        piege = "x'; rm -rf / #"
        with patch.object(boites_isolees, "ouvrir_navigateur", return_value=boite):
            navigateur_boite.executer("browser_type", "u1", "c1", {}, {"selecteur": "#a", "valeur": piege})
        import shlex
        argv = shlex.split(boite.commandes[0])
        self.assertEqual(json.loads(argv[-1])["valeur"], piege)
        self.assertEqual(len(argv), 4)

    def test_erreur_de_page_est_visible_pour_le_modele(self):
        boite = FausseBoite(json.dumps({"ok": False, "erreur": "Timeout", "url": "https://a.org/", "titre": "A", "capture": "/c.jpg"}))
        with patch.object(boites_isolees, "ouvrir_navigateur", return_value=boite):
            sortie = navigateur_boite.executer("browser_click", "u1", "c1", {}, {"texte": "Suivant"})
        self.assertIn("NAVIGATEUR_ERREUR: Timeout", json.loads(sortie)["text"])

    def test_sans_capture_lisible_le_texte_seul_est_renvoye(self):
        boite = FausseBoite(json.dumps(RETOUR_OK), octets=None)
        with patch.object(boites_isolees, "ouvrir_navigateur", return_value=boite):
            sortie = navigateur_boite.executer("browser_screenshot", "u1", "c1", {}, {})
        self.assertTrue(sortie.startswith("Adresse :"))

    def test_service_plein_et_service_injoignable_donnent_des_messages_clairs(self):
        with patch.object(boites_isolees, "ouvrir_navigateur", side_effect=boites_isolees.ErreurBoite("x", 429)):
            self.assertIn("NAVIGATEUR_CAPACITE", navigateur_boite.executer("browser_open", "u", "c", {}, {"url": "https://a.org"}))
        with patch.object(boites_isolees, "ouvrir_navigateur", side_effect=boites_isolees.ErreurBoite("x", 503)):
            self.assertIn("NAVIGATEUR_ERREUR", navigateur_boite.executer("browser_open", "u", "c", {}, {"url": "https://a.org"}))
        with patch.object(boites_isolees, "ouvrir_navigateur", side_effect=ValueError("secret interne")):
            sortie = navigateur_boite.executer("browser_open", "u", "c", {}, {"url": "https://a.org"})
        self.assertNotIn("secret interne", sortie)

    def test_fermer_detruit_la_boite_de_la_conversation(self):
        with patch.object(boites_isolees.BoiteDocker, "kill") as kill:
            self.assertIn("détruites", navigateur_boite.fermer("u1", "c1"))
        kill.assert_called_once_with(navigateur_boite.empreintes("u1", "c1")[0])


class OutilExecutionCode(unittest.TestCase):
    def test_les_actions_navigateur_sont_dans_l_outil_et_hors_reservation_de_quota(self):
        from core import outils_execution_code as outil
        with patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(outil, "_configuration_domaines", return_value={"allowed_domains": ["exemple.org"]}), \
                patch.object(outil, "_domaines_conversation_ou_vide", return_value=["autre.org"]), \
                patch.object(navigateur_boite, "executer", return_value="page") as executer, \
                patch.object(outil, "_rpc_objet", side_effect=AssertionError("pas de réservation de quota")):
            sortie = outil._action_navigateur("browser_open", "u1", "c1", "https://exemple.org", "", "", "", None, None, "")
        self.assertEqual(sortie, "page")
        options = executer.call_args.args[3]
        self.assertEqual(sorted(options["allow_out"]), ["autre.org", "exemple.org"])

    def test_clic_final_refuse_avant_toute_ouverture_de_boite(self):
        from core import outils_execution_code as outil
        with patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(boites_isolees, "ouvrir_navigateur", side_effect=AssertionError("boîte ouverte")):
            sortie = outil._action_navigateur("browser_click", "u1", "c1", "", "", "Payer", "", None, None, "")
        self.assertIn("NAVIGATEUR_ACTION_FINALE", sortie)

    def test_mode_docker_n_exige_plus_la_cle_e2b(self):
        from core import outils_execution_code as outil
        env = {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x", "BOITES_TOKEN": "t", "SUPABASE_SECRET": "s"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(outil, "_action_navigateur", return_value="ok-navigateur") as navigateur:
            sortie = outil.gerer_execution_code(action="browser_screenshot", ctx=None)
        self.assertEqual(sortie, "ok-navigateur")
        navigateur.assert_called_once()


class Approbation(unittest.TestCase):
    def test_action_finale_est_confirmee_les_autres_non(self):
        self.assertTrue(_est_outil_sensible({
            "name": "gerer_execution_code", "arguments": json.dumps({"action": "browser_submit", "text": "Envoyer"}),
        }))
        for action in ("browser_open", "browser_click", "browser_type", "browser_screenshot", "browser_close"):
            self.assertFalse(_est_outil_sensible({
                "name": "gerer_execution_code", "arguments": json.dumps({"action": action}),
            }), action)

    def test_libelles_et_icones_des_six_actions_avec_la_limite_de_18_caracteres(self):
        from registre_outils import REGISTRE_AFFICHAGE_OUTILS
        for action in navigateur_boite.ACTIONS:
            entree = REGISTRE_AFFICHAGE_OUTILS[f"gerer_execution_code:{action}"]
            self.assertLessEqual(len(entree["label"]), 18, action)
            self.assertTrue(entree["icone"])
            self.assertNotIn("--", entree["label"])

    def test_la_carte_de_confirmation_montre_la_cible_de_l_action_finale(self):
        appel = {"name": "gerer_execution_code", "arguments": json.dumps({"action": "browser_submit", "text": "Envoyer le formulaire"})}
        self.assertEqual(_nom_lisible_appel(appel), "Action finale : Envoyer le formulaire")
        appel["arguments"] = json.dumps({"action": "browser_submit", "key": "Enter"})
        self.assertEqual(_nom_lisible_appel(appel), "Action finale : touche Enter")
        appel["arguments"] = json.dumps({"action": "browser_submit"})
        self.assertEqual(_nom_lisible_appel(appel), "Action finale")


class IntegrationAuxAutresOutils(unittest.TestCase):
    """Le navigateur respecte la catégorisation et l'affichage des autres outils."""

    def test_le_site_ouvert_apparait_dans_la_frise_comme_pour_les_autres_outils(self):
        from core.domaines_affichage import domaines_de_l_appel
        self.assertEqual(
            domaines_de_l_appel("gerer_execution_code", {"action": "browser_open", "url": "https://www.exemple.org/page"}),
            ["exemple.org"],
        )
        for autre in ({"action": "browser_click", "text": "Suivant"}, {"action": "run_command", "command": "ls"}):
            self.assertEqual(domaines_de_l_appel("gerer_execution_code", autre), [])

    def test_le_modele_trouve_l_outil_quand_il_demande_un_navigateur(self):
        import asyncio
        from core.outils_execution_code import mcp_execution_code
        from recherche_outils import rechercher_outils_pertinents
        vrai = next(o for o in asyncio.run(mcp_execution_code.list_tools()) if o.name == "gerer_execution_code")
        for action in navigateur_boite.ACTIONS:
            self.assertIn(action, json.dumps(vrai.input_schema))

        def fn(nom, desc):
            return {"type": "function", "function": {"name": nom, "description": desc, "parameters": {}}}
        candidats = [
            fn("gerer_execution_code", vrai.description),
            fn("tavily_search", "Search the web for current information and news."),
            fn("generer_document_excel", "Genere un fichier Excel a partir de donnees."),
            fn("ui_photo", "Prend une photo avec la camera du telephone."),
        ]
        trouves = rechercher_outils_pertinents("ouvrir un site web dans un navigateur et prendre une capture d'ecran", candidats)
        self.assertEqual(trouves[0]["function"]["name"], "gerer_execution_code")


class CapturesModele(unittest.TestCase):
    ENVELOPPE = json.dumps({
        captures_modele.MARQUE: True, "text": "Page A",
        "images": [{"titre": "Navigateur : A", "url": "data:image/jpeg;base64,AAAA"}],
    })

    def test_un_resultat_ordinaire_n_est_jamais_modifie(self):
        for brut in ("texte simple", json.dumps({"images": [{"url": "https://x/y.png"}]}), "", None):
            self.assertEqual(captures_modele.sans_image(brut), brut)
            self.assertEqual(captures_modele.pour_le_modele(brut), (brut, []))
            self.assertEqual(captures_modele.galerie(brut), [])

    def test_sans_la_variable_aucune_image_n_est_envoyee_au_modele(self):
        with patch.dict(os.environ, {}, clear=True):
            texte, urls = captures_modele.pour_le_modele(self.ENVELOPPE)
        self.assertEqual(urls, [])
        self.assertIn("Page A", texte)
        self.assertNotIn("base64", texte)

    def test_avec_la_variable_la_capture_part_dans_un_message_d_image(self):
        with patch.dict(os.environ, {"NAVIGATEUR_VISION_MODELE": "1"}):
            texte, urls = captures_modele.pour_le_modele(self.ENVELOPPE)
        self.assertEqual(urls, ["data:image/jpeg;base64,AAAA"])
        self.assertNotIn("base64", texte)
        messages = [{"role": "tool", "content": texte}]
        captures_modele.ajouter_message_images(messages, urls)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"][1], {"type": "image_url", "image_url": {"url": urls[0]}})
        captures_modele.ajouter_message_images(messages, [])
        self.assertEqual(len(messages), 2)

    def test_texte_d_affichage_et_historique_sans_la_capture(self):
        self.assertEqual(captures_modele.sans_image(self.ENVELOPPE), "Page A")

    def test_galerie_pour_le_chemin_des_outils_approuves(self):
        g = captures_modele.galerie(self.ENVELOPPE)
        self.assertEqual(g[0]["url"], "data:image/jpeg;base64,AAAA")
        self.assertEqual(g[0]["miniature"], g[0]["url"])

    def test_seules_les_images_data_sont_envoyees_au_modele(self):
        brut = json.dumps({captures_modele.MARQUE: True, "text": "t", "images": [{"url": "https://intrus.example/a.png"}]})
        with patch.dict(os.environ, {"NAVIGATEUR_VISION_MODELE": "1"}):
            self.assertEqual(captures_modele.pour_le_modele(brut)[1], [])


class BoucleDOutils(unittest.TestCase):
    """Traversée réelle de _traiter_appels : le résultat d'outil, la galerie et le message d'image."""

    def _lancer(self, vision):
        import execution_outils
        appel = {"id": "call_1", "name": "gerer_execution_code", "arguments": json.dumps({"action": "browser_screenshot"})}
        messages = []
        with patch.dict(os.environ, {"NAVIGATEUR_VISION_MODELE": "1"} if vision else {}, clear=False), \
                patch.object(execution_outils, "appeler_outil", return_value=CapturesModele.ENVELOPPE):
            if not vision:
                os.environ.pop("NAVIGATEUR_VISION_MODELE", None)
            evenements = list(execution_outils._traiter_appels([appel], messages, {"gerer_execution_code": {}}))
        return evenements, messages

    def test_avec_vision_le_modele_recoit_le_texte_puis_la_capture_apres_les_resultats(self):
        evenements, messages = self._lancer(vision=True)
        self.assertEqual(messages[0]["role"], "tool")
        self.assertNotIn("base64", messages[0]["content"])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,AAAA")
        self.assertEqual([m["role"] for m in messages].index("user"), len(messages) - 1)

    def test_la_personne_voit_la_capture_et_l_historique_garde_seulement_le_texte(self):
        evenements, _ = self._lancer(vision=False)
        galeries = [e for e in evenements if e.get("type") == "images"]
        self.assertEqual(galeries[0]["images"][0]["url"], "data:image/jpeg;base64,AAAA")
        resultat = next(e for e in evenements if e.get("type") == "outil_resultat")
        self.assertEqual(resultat["resultat"], "Page A")
        self.assertNotIn("base64", json.dumps(resultat))

    def test_sans_vision_aucun_message_d_image_n_est_ajoute(self):
        _, messages = self._lancer(vision=False)
        self.assertEqual([m["role"] for m in messages], ["tool"])


if __name__ == "__main__":
    unittest.main()
