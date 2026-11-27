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
from unittest.mock import MagicMock, patch

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

    def etat(self, page_entiere=False):
        self.page_entiere = page_entiere
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


class BoiteUnique(unittest.TestCase):
    """Une seule boîte par conversation : le terminal et Chromium vivent ensemble."""

    def _arguments_de_creation(self):
        appels = []

        def faux(args, entree=None, delai=30):
            appels.append(args)

            class R:
                returncode = 0
                stdout = b""
                stderr = b""
            return R()

        with patch.object(Docker, "_docker", staticmethod(faux)):
            Docker().creer("a" * 32)
        return next(a for a in appels if a[0] == "run")

    def test_la_boite_a_la_place_pour_le_terminal_et_chromium(self):
        a = self._arguments_de_creation()
        self.assertIn("classinus-boite:latest", a)
        self.assertEqual(a[a.index("--memory") + 1], "1536m")
        self.assertEqual(a[a.index("--shm-size") + 1], "512m")
        self.assertEqual(a[a.index("--pids-limit") + 1], "512")
        self.assertIn("/tmp:rw,size=512m", a)

    def test_les_protections_de_la_boite_restent_intactes(self):
        a = self._arguments_de_creation()
        for obligatoire in ("--read-only", "--cap-drop", "ALL", "no-new-privileges", "1000:1000"):
            self.assertIn(obligatoire, a)
        self.assertEqual(a[a.index("--network") + 1], "boites_internes")
        self.assertEqual(a[a.index("--memory-swap") + 1], a[a.index("--memory") + 1])

    def test_localhost_reste_dans_la_boite_sans_passer_par_le_proxy(self):
        a = self._arguments_de_creation()
        self.assertIn("NO_PROXY=localhost,127.0.0.1,::1", a)
        self.assertIn("no_proxy=localhost,127.0.0.1,::1", a)

    def test_le_service_n_a_plus_de_route_navigateur(self):
        with patch.dict(os.environ, {"BOITES_TOKEN": "jeton-test"}), patch.object(app_mod, "docker", FauxDocker()):
            client = TestClient(app_mod.app)
            self.assertEqual(client.post("/navigateurs", json={}, headers=AUTH).status_code, 404)
            self.assertEqual(client.delete("/navigateurs?utilisateur=" + "9" * 32, headers=AUTH).status_code, 404)

    def test_l_image_contient_le_pilote(self):
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boites_service", "Dockerfile.boite")
        with open(chemin, encoding="utf-8") as fichier:
            texte = fichier.read()
        self.assertIn("COPY pilote.py /opt/navigateur/pilote.py", texte)
        self.assertIn("playwright install", texte)


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
    def _executer(self, action, parametres, boite, reservation=({"event_id": "e1"}, None)):
        """executer() avec un faux workspace : la réservation et l'ouverture de la boîte sont simulées."""
        def travailler(user_id, conversation_id, reservation_, nom_action, travail):
            return travail(boite, {})

        outil = navigateur_boite.outils_execution_code
        with patch.object(outil, "_reserver_workspace", return_value=reservation) as reserver, \
                patch.object(outil, "_travailler_dans_workspace", side_effect=travailler):
            sortie = navigateur_boite.executer(action, "u1", "c1", parametres)
        self.reserver = reserver
        return sortie

    def test_indisponible_avec_e2b(self):
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "e2b"}):
            self.assertIn("NAVIGATEUR_UNAVAILABLE", navigateur_boite.raison_indisponible())
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker"}, clear=True):
            self.assertIn("NAVIGATEUR_NOT_CONFIGURED", navigateur_boite.raison_indisponible())
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x", "BOITES_TOKEN": "t"}):
            self.assertIsNone(navigateur_boite.raison_indisponible())

    def test_preparation_des_parametres(self):
        p = navigateur_boite.preparer
        self.assertIn("url", p("open", "", "", "", "", None, None, "")[1])
        self.assertEqual(p("open", " https://a.org ", "", "", "", None, None, "")[0], {"url": "https://a.org"})
        self.assertEqual(p("click", "", "#menu", "", "", None, None, "")[0], {"selecteur": "#menu"})
        self.assertEqual(p("click", "", "", "Suivant", "", None, None, "")[0], {"texte": "Suivant"})
        self.assertEqual(p("click", "", "", "", "", 10, 20, "")[0], {"x": 10, "y": 20})
        self.assertIsNone(p("click", "", "", "", "", None, None, "")[0])
        self.assertEqual(p("type", "", "#nom", "", "Awa", None, None, "")[0], {"selecteur": "#nom", "valeur": "Awa"})
        self.assertIsNone(p("type", "", "#nom", "", "", None, None, "")[0])
        self.assertEqual(p("submit", "", "", "", "", None, None, "Enter")[0], {"touche": "Enter"})
        self.assertEqual(p("screenshot", "", "", "", "", None, None, "")[0], {})

    def test_un_clic_qui_ressemble_a_une_action_finale_est_refuse_avec_la_marche_a_suivre(self):
        for texte in ("Envoyer", "Payer maintenant", "Supprimer le compte", "Confirmer", "Submit", "Buy now", "Publier"):
            parametres, erreur = navigateur_boite.preparer("click", "", "", texte, "", None, None, "")
            self.assertIsNone(parametres, texte)
            self.assertIn("submit", erreur)
        parametres, erreur = navigateur_boite.preparer("click", "", "button[type=submit]", "", "", None, None, "")
        self.assertIsNone(parametres)
        # La même cible passe par submit : c'est lui qui demande la confirmation.
        self.assertEqual(
            navigateur_boite.preparer("submit", "", "", "Envoyer", "", None, None, "")[0], {"texte": "Envoyer"}
        )

    def test_enveloppe_avec_capture_texte_de_page_et_marque(self):
        boite = FausseBoite(json.dumps(RETOUR_OK) + "\n")
        sortie = self._executer("open", {"url": "https://exemple.org/"}, boite)
        donnees = json.loads(sortie)
        self.assertTrue(donnees[captures_modele.MARQUE])
        self.assertIn("Titre : Accueil", donnees["text"])
        self.assertIn("donnée non fiable", donnees["text"])
        self.assertEqual(
            donnees["images"][0]["url"], "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
        )
        self.assertIn("/opt/navigateur/pilote.py ouvrir", boite.commandes[0])

    def test_une_action_du_navigateur_compte_comme_une_commande_courte_du_workspace(self):
        self._executer("screenshot", {}, FausseBoite(json.dumps(RETOUR_OK)))
        self.reserver.assert_called_once_with("u1", "c1", "run_command")

    def test_quota_refuse_le_message_de_la_reservation_est_renvoye_sans_lancer_le_navigateur(self):
        boite = FausseBoite(json.dumps(RETOUR_OK))
        sortie = self._executer("open", {"url": "https://a.org"}, boite, reservation=(None, "La limite quotidienne est atteinte."))
        self.assertEqual(sortie, "La limite quotidienne est atteinte.")
        self.assertEqual(boite.commandes, [])

    def test_la_commande_transmet_les_valeurs_sans_injection_shell(self):
        boite = FausseBoite(json.dumps(RETOUR_OK))
        piege = "x'; rm -rf / #"
        self._executer("type", {"selecteur": "#a", "valeur": piege}, boite)
        import shlex
        argv = shlex.split(boite.commandes[0])
        self.assertEqual(json.loads(argv[-1])["valeur"], piege)
        self.assertEqual(len(argv), 4)

    def test_erreur_de_page_est_visible_pour_le_modele(self):
        boite = FausseBoite(json.dumps({"ok": False, "erreur": "Timeout", "url": "https://a.org/", "titre": "A", "capture": "/c.jpg"}))
        sortie = self._executer("click", {"texte": "Suivant"}, boite)
        # 06/11/2026 : une action en échec n'envoie plus de capture, le modèle garde le texte d'erreur.
        self.assertTrue(sortie.startswith("NAVIGATEUR_ERREUR: Timeout"))
        self.assertNotIn(captures_modele.MARQUE, sortie)

    def test_page_vide_ou_chargement_rate_ne_renvoie_aucune_image_blanche(self):
        for retour in (
            {"ok": True, "url": "about:blank", "titre": "", "texte": "", "capture": "/c.jpg"},
            {"ok": True, "url": "https://a.org/", "titre": "", "texte": "", "capture": "/c.jpg"},
            {"ok": False, "erreur": "net::ERR_TUNNEL_CONNECTION_FAILED", "url": "about:blank", "capture": "/c.jpg"},
        ):
            with self.subTest(retour=retour):
                sortie = self._executer("open", {"url": "https://a.org/"}, FausseBoite(json.dumps(retour)))
                self.assertNotIn(captures_modele.MARQUE, sortie)

    def test_page_normale_garde_sa_capture(self):
        sortie = self._executer("screenshot", {}, FausseBoite(json.dumps(RETOUR_OK)))
        self.assertTrue(json.loads(sortie)[captures_modele.MARQUE])

    def test_sans_capture_lisible_le_texte_seul_est_renvoye(self):
        sortie = self._executer("screenshot", {}, FausseBoite(json.dumps(RETOUR_OK), octets=None))
        self.assertTrue(sortie.startswith("Adresse :"))

    def test_console_et_fausses_reponses_n_envoient_pas_d_image(self):
        for action in ("console", "mock", "unmock"):
            with self.subTest(action=action):
                sortie = self._executer(action, {}, FausseBoite(json.dumps({**RETOUR_OK, "console": [], "simulations": []})))
                self.assertNotIn(captures_modele.MARQUE, sortie)

    def test_la_capture_complete_n_est_jamais_tronquee(self):
        grosse = b"\xff\xd8" + b"a" * 600_000
        sortie = self._executer("screenshot", {"page_entiere": True}, FausseBoite(json.dumps(RETOUR_OK), octets=grosse))
        image = json.loads(sortie)["images"][0]["url"]
        self.assertEqual(base64.b64decode(image.split(",", 1)[1]), grosse)

    def test_boite_sans_pilote_explique_comment_la_renouveler(self):
        class AncienneBoite(FausseBoite):
            def run(self, commande, timeout=60, request_timeout=None, **_):
                return boites_isolees.ResultatCommande(
                    stdout="", stderr="python3: can't open file '/opt/navigateur/pilote.py': [Errno 2] No such file or directory", exit_code=2,
                )

        sortie = self._executer("open", {"url": "https://a.org"}, AncienneBoite(""))
        self.assertIn("avant l'arrivée du navigateur", sortie)
        self.assertIn("download_files", sortie)

    def test_service_de_boites_en_erreur_donne_un_message_clair_sans_detail_interne(self):
        class BoiteEnPanne(FausseBoite):
            def run(self, *a, **k):
                raise boites_isolees.ErreurBoite("secret interne", 500)

        sortie = self._executer("open", {"url": "https://a.org"}, BoiteEnPanne(""))
        self.assertIn("NAVIGATEUR_ERREUR", sortie)
        self.assertNotIn("secret interne", sortie)

    def test_capacite_du_service_remonte_au_workspace_commun(self):
        class BoitePleine(FausseBoite):
            def run(self, *a, **k):
                raise boites_isolees.ErreurBoite("x", 429)

        with self.assertRaises(boites_isolees.ErreurBoite):
            navigateur_boite.lancer_dans_boite(BoitePleine(""), "open", {"url": "https://a.org"})

    def test_fermer_arrete_chromium_sans_detruire_le_workspace(self):
        boite = FausseBoite(json.dumps({"ok": True, "ferme": True}))
        faux_supabase = MagicMock()
        faux_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"sandbox_id": "a" * 32}
        ]
        with patch.object(navigateur_boite.outils_execution_code, "_client_supabase", return_value=faux_supabase), \
                patch.object(boites_isolees, "BoiteDocker", return_value=boite) as classe, \
                patch.object(boites_isolees.BoiteDocker, "kill", side_effect=AssertionError("workspace détruit"), create=True):
            sortie = navigateur_boite.fermer("u1", "c1")
        classe.assert_called_once_with("a" * 32)
        self.assertIn("pilote.py fermer", boite.commandes[0])
        self.assertIn("conservés", sortie)

    def test_fermer_sans_workspace_ne_cree_rien(self):
        faux_supabase = MagicMock()
        faux_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        with patch.object(navigateur_boite.outils_execution_code, "_client_supabase", return_value=faux_supabase), \
                patch.object(boites_isolees, "BoiteDocker", side_effect=AssertionError("boîte touchée")):
            self.assertEqual(navigateur_boite.fermer("u1", "c1"), "Aucun navigateur n'est ouvert.")

    def test_fermer_une_boite_deja_arretee_reste_un_succes(self):
        faux_supabase = MagicMock()
        faux_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"sandbox_id": "a" * 32}
        ]

        class BoiteArretee(FausseBoite):
            def run(self, *a, **k):
                raise boites_isolees.ErreurBoite("not found", 404)

        with patch.object(navigateur_boite.outils_execution_code, "_client_supabase", return_value=faux_supabase), \
                patch.object(boites_isolees, "BoiteDocker", return_value=BoiteArretee("")):
            self.assertIn("Navigateur fermé", navigateur_boite.fermer("u1", "c1"))


class NouvellesActions(unittest.TestCase):
    """Téléphone, défilement, attente, console et fausses réponses : paramètres envoyés au pilote."""

    def _p(self, action, url="", selector="", text="", content="", x=None, y=None, key="", **extras):
        return navigateur_boite.preparer(action, url, selector, text, content, x, y, key, **extras)

    def test_ouvrir_sur_un_telephone(self):
        self.assertEqual(
            self._p("open", url="http://localhost:5173", device="iphone")[0],
            {"url": "http://localhost:5173", "appareil": "iphone"},
        )
        self.assertEqual(
            self._p("open", url="http://localhost:5173", width=360, height=740)[0],
            {"url": "http://localhost:5173", "largeur": 360, "hauteur": 740},
        )
        self.assertEqual(self._p("open", url="https://a.org")[0], {"url": "https://a.org"})

    def test_changer_d_ecran_demande_un_appareil_ou_une_taille(self):
        self.assertEqual(self._p("device", device="android")[0], {"appareil": "android"})
        self.assertIsNone(self._p("device")[0])

    def test_capture_de_la_page_entiere(self):
        self.assertEqual(self._p("screenshot", full_page=True)[0], {"page_entiere": True})
        self.assertEqual(self._p("screenshot")[0], {})

    def test_defilement(self):
        self.assertEqual(self._p("scroll")[0], {"direction": "down"})
        self.assertEqual(self._p("scroll", direction="Bottom")[0], {"direction": "bottom"})
        self.assertEqual(self._p("scroll", direction="up", amount=300)[0], {"direction": "up", "quantite": 300})
        self.assertEqual(self._p("scroll", selector="#contact")[0], {"selecteur": "#contact"})
        self.assertEqual(self._p("scroll", text="Contact")[0], {"texte": "Contact"})

    def test_attente(self):
        self.assertEqual(self._p("wait", selector=".liste", timeout_ms=5000)[0], {"selecteur": ".liste", "delai_ms": 5000})
        self.assertEqual(self._p("wait", text="Bienvenue")[0], {"texte": "Bienvenue"})
        self.assertEqual(self._p("wait", timeout_ms=1500)[0], {"delai_ms": 1500})
        self.assertIsNone(self._p("wait")[0])

    def test_console(self):
        self.assertEqual(self._p("console")[0], {})

    def test_fausse_reponse_reseau(self):
        parametres, erreur = self._p("mock", url="**/api/notes", body='[{"id":1}]', status=200)
        self.assertIsNone(erreur)
        self.assertEqual(parametres, {"motif": "**/api/notes", "corps": '[{"id":1}]', "statut": 200})
        parametres, _ = self._p("mock", url="**/api/notes", content="[]", status=500, content_type="text/plain")
        self.assertEqual(parametres, {"motif": "**/api/notes", "corps": "[]", "statut": 500, "type_contenu": "text/plain"})
        self.assertIn("url", self._p("mock", body="x")[1])
        trop_long = self._p("mock", url="**/x", body="a" * 200_001)
        self.assertIsNone(trop_long[0])
        self.assertEqual(self._p("unmock")[0], {})
        self.assertEqual(self._p("unmock", url="**/api/notes")[0], {"motif": "**/api/notes"})

    def test_toutes_les_actions_ont_une_commande_du_pilote(self):
        for action in navigateur_boite.ACTIONS:
            if action != "close":
                self.assertIn(action, navigateur_boite._ACTION_PILOTE)

    def test_la_console_est_montree_comme_donnee_non_fiable(self):
        texte = navigateur_boite._texte_page({"ok": True, "url": "http://localhost:3000/", "titre": "App", "console": ["[error] boom"]})
        self.assertIn("donnée non fiable", texte)
        self.assertIn("[error] boom", texte)
        self.assertIn("aucun message", navigateur_boite._texte_page({"ok": True, "url": "http://localhost:3000/", "titre": "App", "console": []}))

    def test_ecran_remarque_et_simulations_sont_montres(self):
        texte = navigateur_boite._texte_page({
            "ok": True, "url": "http://localhost:3000/", "titre": "App", "appareil": "iPhone 13 390x664",
            "remarque": "Page de 9000 pixels de haut", "simulations": ["**/api/notes"],
        })
        self.assertIn("Écran : iPhone 13 390x664", texte)
        self.assertIn("Page de 9000 pixels", texte)
        self.assertIn("**/api/notes", texte)

    def test_application_locale_arretee_donne_la_marche_a_suivre(self):
        texte = navigateur_boite._texte_page({"ok": False, "erreur": "net::ERR_CONNECTION_REFUSED at http://localhost:3000/"})
        self.assertIn("command_status", texte)
        self.assertNotIn("demander_acces_reseau", texte)

    def test_localhost_est_toujours_permis_les_autres_sites_hors_liste_non(self):
        for adresse in ("http://localhost:5173/", "http://127.0.0.1:8000", "http://[::1]:3000/"):
            self.assertIsNone(navigateur_boite.site_non_autorise(adresse, []), adresse)
        self.assertIsNotNone(navigateur_boite.site_non_autorise("http://192.168.1.10:3000", []))
        self.assertIsNotNone(navigateur_boite.site_non_autorise("http://localhost.evil.org/", []))


class PiloteAppareilsEtActions(unittest.TestCase):
    CATALOGUE = {
        "iPhone 13": {"user_agent": "UA", "viewport": {"width": 390, "height": 664}, "screen": {"width": 390, "height": 844},
                      "device_scale_factor": 3, "is_mobile": True, "has_touch": True, "default_browser_type": "webkit"},
        "Pixel 7": {"user_agent": "UA2", "viewport": {"width": 412, "height": 839}, "device_scale_factor": 2.625,
                    "is_mobile": True, "has_touch": True},
    }

    def test_bureau_par_defaut(self):
        profil = pilote.resoudre_appareil("", None, None, self.CATALOGUE)
        self.assertEqual(profil["appareil"], "bureau")
        self.assertEqual(profil["options"]["viewport"], {"width": pilote.LARGEUR_BUREAU, "height": pilote.HAUTEUR_BUREAU})
        self.assertNotIn("has_touch", profil["options"])

    def test_alias_iphone_et_android_donnent_un_ecran_tactile(self):
        iphone = pilote.resoudre_appareil("iPhone", None, None, self.CATALOGUE)
        self.assertEqual(iphone["nom"], "iPhone 13 390x664")
        self.assertTrue(iphone["options"]["has_touch"])
        self.assertTrue(iphone["options"]["is_mobile"])
        self.assertNotIn("default_browser_type", iphone["options"])
        self.assertEqual(pilote.resoudre_appareil("android", None, None, self.CATALOGUE)["appareil"], "Pixel 7")

    def test_nom_exact_sans_tenir_compte_des_majuscules(self):
        self.assertEqual(pilote.resoudre_appareil("pixel 7", None, None, self.CATALOGUE)["appareil"], "Pixel 7")

    def test_taille_libre_remplace_celle_de_l_appareil(self):
        profil = pilote.resoudre_appareil("iphone", 360, 740, self.CATALOGUE)
        self.assertEqual(profil["options"]["viewport"], {"width": 360, "height": 740})
        self.assertNotIn("screen", profil["options"])
        self.assertTrue(profil["options"]["has_touch"])
        libre = pilote.resoudre_appareil("", 500, None, self.CATALOGUE)
        self.assertEqual(libre["options"]["viewport"]["width"], 500)

    def test_appareil_inconnu_et_dimensions_hors_limites_donnent_une_erreur_claire(self):
        with self.assertRaises(pilote.ErreurPilote) as e:
            pilote.resoudre_appareil("frigo", None, None, self.CATALOGUE)
        self.assertIn("appareil inconnu", str(e.exception))
        for largeur in (50, 5000, "abc"):
            with self.assertRaises(pilote.ErreurPilote, msg=str(largeur)):
                pilote.resoudre_appareil("", largeur, None, self.CATALOGUE)

    def test_la_capture_de_page_entiere_est_demandee_seulement_pour_capture(self):
        faux = FauxNavigateur()
        pilote.traiter(faux, {"action": "capture", "page_entiere": True})
        self.assertTrue(faux.page_entiere)
        faux = FauxNavigateur()
        pilote.traiter(faux, {"action": "cliquer", "page_entiere": True})
        self.assertFalse(faux.page_entiere)

    def test_les_informations_en_plus_de_console_et_simuler_rejoignent_l_etat(self):
        class Avec(FauxNavigateur):
            def agir(self, action, p):
                return {"console": ["[log] salut"]}

        reponse = pilote.traiter(Avec(), {"action": "console"})
        self.assertEqual(reponse["console"], ["[log] salut"])
        self.assertTrue(reponse["ok"])


class OutilNavigateur(unittest.TestCase):
    """L'outil gerer_navigateur : identité, réseau partagé avec l'exécution de code, aucun quota de workspace."""

    def _appeler(self, **kw):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)):
            return outil, kw

    def test_les_domaines_de_la_configuration_et_de_la_conversation_sont_transmis(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(outil, "_configuration_domaines", return_value={"allowed_domains": ["exemple.org"]}), \
                patch.object(outil, "_domaines_conversation_ou_vide", return_value=["autre.org"]), \
                patch.object(navigateur_boite, "executer", return_value="page") as executer:
            sortie = outil.gerer_navigateur(action="open", url="https://exemple.org", ctx=None)
        self.assertEqual(sortie, "page")
        executer.assert_called_once_with("open", "u1", "c1", {"url": "https://exemple.org"})
        # Les domaines servent à refuser un site absent de la liste, comme pour l'exécution de code.
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(outil, "_configuration_domaines", return_value={"allowed_domains": ["exemple.org"]}), \
                patch.object(outil, "_domaines_conversation_ou_vide", return_value=["autre.org"]), \
                patch.object(navigateur_boite, "executer", return_value="page"):
            self.assertIn("rien n'a été ouvert", outil.gerer_navigateur(action="open", url="https://inconnu.org", ctx=None))
            self.assertEqual(outil.gerer_navigateur(action="open", url="https://autre.org", ctx=None), "page")
            self.assertEqual(outil.gerer_navigateur(action="open", url="http://localhost:3000", ctx=None), "page")

    def test_clic_final_refuse_avant_toute_ouverture_de_boite(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(navigateur_boite, "executer", side_effect=AssertionError("boîte ouverte")):
            sortie = outil.gerer_navigateur(action="click", text="Payer", ctx=None)
        self.assertIn("NAVIGATEUR_ACTION_FINALE", sortie)

    def test_identite_invalide_et_service_absent_donnent_un_message_sans_ouvrir_de_boite(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=(None, None, "Erreur : non autorisée")):
            self.assertEqual(outil.gerer_navigateur(action="open", url="https://a.org", ctx=None), "Erreur : non autorisée")
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "e2b"}):
            self.assertIn("NAVIGATEUR_UNAVAILABLE", outil.gerer_navigateur(action="open", url="https://a.org", ctx=None))

    def test_les_nouveaux_parametres_arrivent_au_pilote(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(navigateur_boite, "executer", return_value="ok") as executer:
            outil.gerer_navigateur(action="scroll", direction="bottom", ctx=None)
            outil.gerer_navigateur(action="mock", url="**/api/x", body="[]", status=404, ctx=None)
            outil.gerer_navigateur(action="device", device="android", ctx=None)
        appels = [c.args for c in executer.call_args_list]
        self.assertEqual(appels[0], ("scroll", "u1", "c1", {"direction": "bottom"}))
        self.assertEqual(appels[1], ("mock", "u1", "c1", {"motif": "**/api/x", "corps": "[]", "statut": 404}))
        self.assertEqual(appels[2], ("device", "u1", "c1", {"appareil": "android"}))

    def test_description_de_l_outil_explique_le_mode_telephone_et_localhost(self):
        import asyncio
        from core.outils_navigateur import mcp_navigateur
        vrai = next(o for o in asyncio.run(mcp_navigateur.list_tools()) if o.name == "gerer_navigateur")
        for mot in ("localhost", "iphone", "full_page", "console", "mock"):
            self.assertIn(mot, vrai.description)
        for parametre in ("device", "width", "height", "full_page", "direction", "amount", "timeout_ms", "status", "body", "content_type"):
            self.assertIn(parametre, vrai.input_schema["properties"])

    def test_close_arrete_le_navigateur(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(navigateur_boite, "fermer", return_value="fermé") as fermer:
            self.assertEqual(outil.gerer_navigateur(action="close", ctx=None), "fermé")
        fermer.assert_called_once_with("u1", "c1")


class ExecutionDeCodeInchangee(unittest.TestCase):
    def test_le_navigateur_n_est_plus_dans_l_outil_d_execution_de_code(self):
        import asyncio
        from core.outils_execution_code import mcp_execution_code
        vrai = next(o for o in asyncio.run(mcp_execution_code.list_tools()) if o.name == "gerer_execution_code")
        texte = json.dumps(vrai.input_schema) + (vrai.description or "")
        for mot in ("browser", "navigateur", "capture d'écran", "Chromium"):
            self.assertNotIn(mot, texte)

    def test_mode_docker_n_exige_plus_la_cle_e2b(self):
        from core import outils_execution_code as outil
        env = {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x", "BOITES_TOKEN": "t", "SUPABASE_SECRET": "s"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(outil, "_rpc_objet", side_effect=RuntimeError("base absente")):
            sortie = outil.gerer_execution_code(action="list_files", ctx=None)
        self.assertNotIn("n'est pas configuré sur le serveur", sortie)


class Categorisation(unittest.TestCase):
    """Le navigateur est un outil et une catégorie à part, branchés comme les autres."""

    def test_categorie_a_part_et_serveur_enregistre(self):
        from registre_outils import CATEGORIES_OUTILS, SERVEURS_MCP
        self.assertEqual(CATEGORIES_OUTILS["navigateur"], ["gerer_navigateur"])
        self.assertEqual(CATEGORIES_OUTILS["execution_code"], ["gerer_execution_code"])
        serveur = next(s for s in SERVEURS_MCP if s["nom"] == "navigateur")
        self.assertTrue(serveur["necessite_utilisateur"])
        self.assertIn("/mcp/navigateur?user_id=u1&conversation_id=c1", serveur["url_builder"](lambda _: "s", "u1", None, "c1"))
        self.assertEqual(serveur["headers_builder"](lambda _: "secret", "u1", None), {"X-Classinus-Internal": "secret"})

    def test_la_categorie_est_decrite_au_modele_pour_demander_outils(self):
        import registre_outils
        textes = [v for v in vars(registre_outils).values() if isinstance(v, str) and "execution_code (lancer du code" in v]
        self.assertTrue(textes)
        self.assertIn("navigateur (ouvrir un site web", textes[0])

    def test_masque_avec_e2b_propose_avec_docker(self):
        import mcp_tools
        with patch.dict(os.environ, {"EXECUTION_CODE_FOURNISSEUR": "e2b"}):
            self.assertIn("NAVIGATEUR_UNAVAILABLE", mcp_tools._raison_navigateur_masque("c1"))
        env = {"EXECUTION_CODE_FOURNISSEUR": "docker", "BOITES_URL": "http://x", "BOITES_TOKEN": "t"}
        with patch.dict(os.environ, env):
            self.assertIsNone(mcp_tools._raison_navigateur_masque("c1"))
            self.assertIn("conversation", mcp_tools._raison_navigateur_masque(""))

    def test_migration_declare_le_serveur_navigateur(self):
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations", "2026_11_04_outil_navigateur.sql")
        with open(chemin, encoding="utf-8") as fichier:
            sql = fichier.read()
        self.assertIn("'gerer_navigateur', 1, 'navigateur', true", sql)
        self.assertIn("ON CONFLICT (nom_outil)", sql)

    def test_les_journaux_ne_contiennent_ni_adresse_ni_texte_saisi(self):
        import mcp_tools
        with patch.object(mcp_tools, "logging") as journal:
            mcp_tools.appeler_outil("gerer_navigateur", {"action": "type", "selector": "#iban", "content": "FR76 secret", "url": "https://banque.example/x"}, {})
        messages = " ".join(str(c.args[0]) for c in journal.info.call_args_list)
        for secret in ("FR76", "banque.example", "#iban"):
            self.assertNotIn(secret, messages)
        self.assertIn("content_chars", messages)

    def test_les_journaux_ne_contiennent_pas_les_fausses_reponses(self):
        import mcp_tools
        with patch.object(mcp_tools, "logging") as journal:
            mcp_tools.appeler_outil("gerer_navigateur", {"action": "mock", "url": "**/api/clients", "body": '{"nom":"Awa Traore"}'}, {})
        messages = " ".join(str(c.args[0]) for c in journal.info.call_args_list)
        for secret in ("Awa", "clients"):
            self.assertNotIn(secret, messages)
        self.assertIn("body_chars", messages)


class Approbation(unittest.TestCase):
    def test_action_finale_est_confirmee_les_autres_non(self):
        self.assertTrue(_est_outil_sensible({
            "name": "gerer_navigateur", "arguments": json.dumps({"action": "submit", "text": "Envoyer"}),
        }))
        for action in ("open", "click", "type", "screenshot", "close", "scroll", "wait", "console", "mock", "unmock", "device"):
            self.assertFalse(_est_outil_sensible({
                "name": "gerer_navigateur", "arguments": json.dumps({"action": action}),
            }), action)

    def test_libelles_et_icones_de_toutes_les_actions_avec_la_limite_de_18_caracteres(self):
        from registre_outils import REGISTRE_AFFICHAGE_OUTILS
        for action in navigateur_boite.ACTIONS:
            entree = REGISTRE_AFFICHAGE_OUTILS[f"gerer_navigateur:{action}"]
            self.assertLessEqual(len(entree["label"]), 18, action)
            self.assertTrue(entree["icone"])
            self.assertNotIn("--", entree["label"])

    def test_la_carte_de_confirmation_montre_la_cible_de_l_action_finale(self):
        appel = {"name": "gerer_navigateur", "arguments": json.dumps({"action": "submit", "text": "Envoyer le formulaire"})}
        self.assertEqual(_nom_lisible_appel(appel), "Action finale : Envoyer le formulaire")
        appel["arguments"] = json.dumps({"action": "submit", "key": "Enter"})
        self.assertEqual(_nom_lisible_appel(appel), "Action finale : touche Enter")
        appel["arguments"] = json.dumps({"action": "submit"})
        self.assertEqual(_nom_lisible_appel(appel), "Action finale")


class IntegrationAuxAutresOutils(unittest.TestCase):
    """Le navigateur respecte la catégorisation et l'affichage des autres outils."""

    def test_le_site_ouvert_apparait_dans_la_frise_comme_pour_les_autres_outils(self):
        from core.domaines_affichage import domaines_de_l_appel
        self.assertEqual(
            domaines_de_l_appel("gerer_navigateur", {"action": "open", "url": "https://www.exemple.org/page"}),
            ["exemple.org"],
        )
        # Une application locale n'est pas un site : rien dans la frise.
        self.assertEqual(domaines_de_l_appel("gerer_navigateur", {"action": "open", "url": "http://localhost:5173"}), [])
        for autre in ({"action": "click", "text": "Suivant"}, {"action": "run_command", "command": "ls"}):
            self.assertEqual(domaines_de_l_appel("gerer_navigateur", autre), [])

    def test_le_modele_trouve_l_outil_quand_il_demande_un_navigateur(self):
        import asyncio
        from core.outils_navigateur import mcp_navigateur
        from recherche_outils import rechercher_outils_pertinents
        vrai = next(o for o in asyncio.run(mcp_navigateur.list_tools()) if o.name == "gerer_navigateur")
        for action in navigateur_boite.ACTIONS:
            self.assertIn(action, json.dumps(vrai.input_schema))

        def fn(nom, desc):
            return {"type": "function", "function": {"name": nom, "description": desc, "parameters": {}}}
        candidats = [
            fn("gerer_navigateur", vrai.description),
            fn("tavily_search", "Search the web for current information and news."),
            fn("generer_document_excel", "Genere un fichier Excel a partir de donnees."),
            fn("ui_photo", "Prend une photo avec la camera du telephone."),
        ]
        trouves = rechercher_outils_pertinents("ouvrir un site web dans un navigateur et prendre une capture d'ecran", candidats)
        self.assertEqual(trouves[0]["function"]["name"], "gerer_navigateur")


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
        appel = {"id": "call_1", "name": "gerer_navigateur", "arguments": json.dumps({"action": "screenshot"})}
        messages = []
        with patch.dict(os.environ, {"NAVIGATEUR_VISION_MODELE": "1"} if vision else {}, clear=False), \
                patch.object(execution_outils, "appeler_outil", return_value=CapturesModele.ENVELOPPE):
            if not vision:
                os.environ.pop("NAVIGATEUR_VISION_MODELE", None)
            evenements = list(execution_outils._traiter_appels([appel], messages, {"gerer_navigateur": {}}))
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


class DemandeAccesReseauNavigateur(unittest.TestCase):
    """05/11/2026 : le navigateur a sa propre action demander_acces_reseau, comme l'exécution de code."""

    def _appel(self, **arguments):
        return {"id": "n1", "name": "gerer_navigateur", "arguments": json.dumps({"action": "demander_acces_reseau", **arguments})}

    def test_l_action_demande_toujours_la_confirmation_et_jamais_d_autorisation_permanente(self):
        from core import registre_outils
        self.assertTrue(_est_outil_sensible(self._appel(domain="gitlab.com")))
        self.assertIn("gerer_navigateur:demander_acces_reseau", registre_outils.AUTORISATION_PERMANENTE_INTERDITE)

    def test_la_carte_de_confirmation_affiche_le_site_demande(self):
        self.assertEqual(_nom_lisible_appel(self._appel(domain="GitLab.com")), "Accès au site gitlab.com")

    def test_l_action_enregistre_le_domaine_avec_les_memes_garde_fous_que_le_code(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(outil, "_autoriser_domaine", return_value="Accès autorisé") as autoriser, \
                patch.object(navigateur_boite, "executer", side_effect=AssertionError("boîte ouverte")):
            sortie = outil.gerer_navigateur(action="demander_acces_reseau", domain="gitlab.com", ctx=None)
        self.assertEqual(sortie, "Accès autorisé")
        autoriser.assert_called_once_with("u1", "c1", "gitlab.com")

    def test_un_site_bloque_donne_la_marche_a_suivre_au_modele(self):
        texte = navigateur_boite._texte_page({"ok": False, "erreur": "net::ERR_TUNNEL_CONNECTION_FAILED at https://x.org"})
        self.assertIn("demander_acces_reseau", texte)
        autre = navigateur_boite._texte_page({"ok": False, "erreur": "sélecteur introuvable"})
        self.assertNotIn("demander_acces_reseau", autre)


class SitesAutorisesNavigateur(unittest.TestCase):
    """06/11/2026 : le modèle connaît les sites autorisés et un site hors liste est refusé sans navigateur."""

    def test_regle_identique_a_celle_du_proxy(self):
        liste = ["github.com", "*.exemple.org"]
        self.assertTrue(navigateur_boite.hote_autorise("github.com", liste))
        self.assertTrue(navigateur_boite.hote_autorise("a.exemple.org", liste))
        self.assertFalse(navigateur_boite.hote_autorise("exemple.org", liste))
        self.assertFalse(navigateur_boite.hote_autorise("gitlab.com", liste))
        self.assertFalse(navigateur_boite.hote_autorise("", liste))

    def test_site_hors_liste_donne_la_marche_a_suivre_et_site_autorise_passe(self):
        refus = navigateur_boite.site_non_autorise("https://wikipedia.org/x", ["github.com"])
        self.assertIn("domain=wikipedia.org", refus)
        self.assertIsNone(navigateur_boite.site_non_autorise("https://github.com/x", ["github.com"]))

    def test_open_hors_liste_n_ouvre_aucune_boite(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(outil, "_configuration_domaines", return_value={"allowed_domains": ["github.com"]}), \
                patch.object(outil, "_domaines_conversation_ou_vide", return_value=[]), \
                patch.object(navigateur_boite, "executer", side_effect=AssertionError("boîte ouverte")):
            sortie = outil.gerer_navigateur(action="open", url="https://wikipedia.org", ctx=None)
        self.assertIn("rien n'a été ouvert", sortie)

    def test_open_autorise_par_la_conversation_continue_normalement(self):
        from core import outils_navigateur as outil
        with patch.object(outil, "_identite_interne", return_value=("u1", "c1", None)), \
                patch.object(navigateur_boite, "raison_indisponible", return_value=None), \
                patch.object(outil, "_configuration_domaines", return_value={"allowed_domains": ["github.com"]}), \
                patch.object(outil, "_domaines_conversation_ou_vide", return_value=["wikipedia.org"]), \
                patch.object(navigateur_boite, "executer", return_value="PAGE") as executer:
            sortie = outil.gerer_navigateur(action="open", url="https://wikipedia.org", ctx=None)
        self.assertEqual(sortie, "PAGE")
        executer.assert_called_once()

    def test_la_description_des_outils_reseau_donne_la_liste_des_sites_autorises(self):
        from core import outils_execution_code as code
        with patch.object(code, "_domaines_reseau_configures", return_value=["github.com", "pypi.org"]), \
                patch.object(code, "_domaines_conversation_ou_vide", return_value=["wikipedia.org", "github.com"]):
            texte = code.complement_description_domaines("u1", "c1")
        for domaine in ("github.com", "pypi.org", "wikipedia.org"):
            self.assertIn(domaine, texte)
        self.assertEqual(texte.count("github.com"), 1)
        self.assertIn("demander_acces_reseau", texte)

    def test_si_la_lecture_echoue_la_description_reste_inchangee(self):
        from core import outils_execution_code as code
        with patch.object(code, "_domaines_reseau_configures", side_effect=RuntimeError("base")):
            self.assertEqual(code.complement_description_domaines("u1", "c1"), "")


if __name__ == "__main__":
    unittest.main()
