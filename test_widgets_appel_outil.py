"""Appels d'outils lances depuis un widget : regles de routage, sensibilite, resultat rendu."""
import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "core"))

try:
    from core import widgets_appel_outil as w
    from core import ressources_ui as r
    from core.execution_outils import cle_autorisation_appel
    IMPORT_ERREUR = None
except Exception as erreur:  # dependances lourdes absentes de cet environnement
    IMPORT_ERREUR = erreur


def route(url="https://mcp.higgsfield.ai/mcp", **plus):
    return {"url": url, "headers": {}, "nom_reel": "x", **plus}


TABLE = {
    "higgsfield_get_presets": route(),
    "higgsfield_generate_image": route(),
    "vercel_list_projects": route(url="https://mcp.vercel.com"),
    "custommcp_abc_outil": route(custom_mcp=True),
}


@unittest.skipIf(IMPORT_ERREUR, f"imports indisponibles : {IMPORT_ERREUR}")
class Routage(unittest.TestCase):
    def test_meme_serveur_accepte(self):
        self.assertEqual(w.resoudre_appel("higgsfield_get_presets", "generate_image", TABLE), "higgsfield_generate_image")

    def test_autre_serveur_refuse(self):
        with self.assertRaises(w.ErreurWidget) as c:
            w.resoudre_appel("higgsfield_get_presets", "list_projects", TABLE)
        self.assertEqual(c.exception.code, "WIDGET_OUTIL_INTROUVABLE")

    def test_nom_avec_prefixe_d_un_autre_serveur_refuse(self):
        # Le widget ne peut pas viser "vercel_list_projects" en passant le prefixe dans le nom.
        with self.assertRaises(w.ErreurWidget):
            w.resoudre_appel("higgsfield_get_presets", "vercel_list_projects", TABLE)

    def test_source_sans_prefixe_connu_refusee(self):
        for source in ("gerer_navigateur", "custommcp_abc_outil", "", "higgsfield_get_presets; rm"):
            with self.assertRaises(w.ErreurWidget, msg=source):
                w.resoudre_appel(source, "get_presets", TABLE)

    def test_outil_inconnu(self):
        with self.assertRaises(w.ErreurWidget) as c:
            w.resoudre_appel("higgsfield_get_presets", "n_existe_pas", TABLE)
        self.assertEqual(c.exception.code, "WIDGET_OUTIL_INTROUVABLE")

    def test_source_absente_de_la_table(self):
        with self.assertRaises(w.ErreurWidget):
            w.resoudre_appel("higgsfield_inconnu", "get_presets", TABLE)

    def test_adresse_differente_refusee(self):
        table = {**TABLE, "higgsfield_generate_image": route(url="https://autre.test/mcp")}
        with self.assertRaises(w.ErreurWidget) as c:
            w.resoudre_appel("higgsfield_get_presets", "generate_image", table)
        self.assertEqual(c.exception.code, "WIDGET_APPEL_REFUSE")

    def test_telephone_et_personnalise_exclus(self):
        for plus in ({"via_app_telephone": True}, {"custom_mcp": True}):
            table = {**TABLE, "higgsfield_generate_image": route(**plus)}
            with self.assertRaises(w.ErreurWidget):
                w.resoudre_appel("higgsfield_get_presets", "generate_image", table)


@unittest.skipIf(IMPORT_ERREUR, f"imports indisponibles : {IMPORT_ERREUR}")
class Sensibilite(unittest.TestCase):
    def cle(self, nom):
        return cle_autorisation_appel(w.appel_au_format_chat(nom, {"a": 1}))

    def test_lecture_sans_confirmation(self):
        self.assertIsNone(self.cle("higgsfield_get_presets"))
        self.assertIsNone(self.cle("higgsfield_list_jobs"))

    def test_action_qui_coute_confirmee(self):
        self.assertEqual(self.cle("higgsfield_generate_image"), "higgsfield_generate_image")


@unittest.skipIf(IMPORT_ERREUR, f"imports indisponibles : {IMPORT_ERREUR}")
class Resultat(unittest.TestCase):
    def test_texte_simple(self):
        self.assertEqual(w.texte_pour_widget("ok"), "ok")

    def test_enveloppe_widget_retiree(self):
        env = r.joindre_ressources_ui('{"a": 1}', [{"uri": "ui://x", "genre": "html", "contenu": "<p/>"}])
        self.assertEqual(json.loads(w.texte_pour_widget(env)), {"a": 1})

    def test_galerie_retiree_texte_garde(self):
        env = json.dumps({"text": '{"jobs": []}', "images": [{"url": "https://x/a.png"}]})
        self.assertEqual(w.texte_pour_widget(env), '{"jobs": []}')

    def test_json_sans_enveloppe_inchange(self):
        self.assertEqual(w.texte_pour_widget('{"jobs": []}'), '{"jobs": []}')

    def test_erreurs(self):
        self.assertTrue(w.est_erreur("Erreur : outil 'x' inconnu."))
        self.assertTrue(w.est_erreur("Délai dépassé : x"))
        self.assertFalse(w.est_erreur('{"ok": true}'))

    def test_marquer_source(self):
        marque = r.marquer_source([{"uri": "ui://a"}, "x"], "higgsfield_get_presets")
        self.assertEqual(marque, [{"uri": "ui://a", "outil_source": "higgsfield_get_presets"}])
        self.assertEqual(r.marquer_source(None, "x"), [])


@unittest.skipIf(IMPORT_ERREUR, f"imports indisponibles : {IMPORT_ERREUR}")
class RouteHttp(unittest.TestCase):
    """La route complete, avec catalogue, autorisations et appel MCP simules."""

    def setUp(self):
        try:
            from unittest.mock import patch
            from types import SimpleNamespace
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from api import widgets_outils as m
            from api.auth import utilisateur_courant
        except Exception as erreur:
            self.skipTest(f"FastAPI ou api indisponibles ici : {erreur}")
        self.m, self.appels = m, []
        app = FastAPI()
        app.include_router(m.router)
        app.dependency_overrides[utilisateur_courant] = lambda: SimpleNamespace(id="u1")
        self.client = TestClient(app)
        self.autorisations = frozenset()

        def faux_appel(nom, arguments, table, arret=None):
            self.appels.append((nom, arguments))
            return '{"text": "fait", "images": []}'

        self.patches = [
            patch.object(m, "lister_outils_autorises_pour_agent", lambda *a, **k: ([], TABLE)),
            patch.object(m, "appeler_outil", faux_appel),
            patch.object(m, "charger_autorisations", lambda uid: self.autorisations),
            patch.object(m, "enregistrer_autorisation", lambda *a: self.appels.append(("enregistre", a[1]))),
            patch.object(m, "journaliser", lambda **k: self.appels.append(("journal", k["details"]["outil"]))),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def poster(self, **plus):
        corps = {"outil_source": "higgsfield_get_presets", "nom_outil": "get_presets", "arguments": {"q": 1}}
        return self.client.post("/api/widgets/appel-outil", json={**corps, **plus})

    def test_lecture_executee_sans_confirmation(self):
        reponse = self.poster()
        self.assertEqual(reponse.json(), {"statut": "ok", "contenu": [{"type": "text", "text": "fait"}], "est_erreur": False})
        self.assertEqual(self.appels, [("higgsfield_get_presets", {"q": 1})])

    def test_action_qui_coute_demande_confirmation_sans_rien_lancer(self):
        corps = self.poster(nom_outil="generate_image").json()
        self.assertEqual(corps["statut"], "confirmation_requise")
        self.assertEqual(corps["cle"], "higgsfield_generate_image")
        self.assertEqual(self.appels, [])

    def test_action_approuvee_executee_et_journalisee(self):
        corps = self.poster(nom_outil="generate_image", approuve=True).json()
        self.assertEqual(corps["statut"], "ok")
        self.assertEqual([a[0] for a in self.appels], ["higgsfield_generate_image", "journal"])

    def test_toujours_autoriser_enregistre(self):
        self.poster(nom_outil="generate_image", approuve=True, toujours_autoriser=True)
        self.assertIn(("enregistre", "higgsfield_generate_image"), self.appels)

    def test_toujours_autoriser_sans_approbation_ne_fait_rien(self):
        self.poster(nom_outil="generate_image", toujours_autoriser=True)
        self.assertEqual(self.appels, [])

    def test_autorisation_permanente_evite_la_confirmation(self):
        self.autorisations = frozenset({"higgsfield_generate_image"})
        self.assertEqual(self.poster(nom_outil="generate_image").json()["statut"], "ok")

    def test_autre_serveur_refuse(self):
        reponse = self.poster(nom_outil="list_projects")
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(self.appels, [])

    def test_source_non_relayable_refusee(self):
        reponse = self.poster(outil_source="gerer_navigateur")
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(self.appels, [])


if __name__ == "__main__":
    unittest.main()
