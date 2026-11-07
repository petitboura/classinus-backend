"""Widgets MCP-UI (ressources ui://) : collecte, enveloppe, separation.

Sans base ni reseau : bibliotheque standard seulement, session MCP simulee.
"""
import asyncio
import base64
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "core"))

from core import ressources_ui as r  # noqa: E402


def _bloc(uri, mime="text/html", text=None, blob=None):
    return NS(type="resource", resource=NS(uri=uri, mime_type=mime, text=text, blob=blob))


def _resultat(blocs, structure=None, erreur=False):
    return NS(content=blocs, structured_content=structure, is_error=erreur)


class SessionFausse:
    def __init__(self, contenus=None, erreur=None):
        self.contenus, self.erreur, self.lectures = contenus or [], erreur, []

    async def read_resource(self, uri):
        self.lectures.append(uri)
        if self.erreur:
            raise self.erreur
        return NS(contents=self.contenus)


def collecter(blocs, session=None, texte="Submitted 1 job", structure=None, declaree=None, erreur=False):
    return asyncio.run(
        r.collecter_ressources_ui(session or SessionFausse(), _resultat(blocs, structure, erreur), texte, declaree)
    )


class Collecte(unittest.TestCase):
    def test_html_inline(self):
        w = collecter([_bloc("ui://a/1", text="<p>Bonjour</p>")])
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["genre"], w[0]["contenu"], w[0]["uri"]), ("html", "<p>Bonjour</p>", "ui://a/1"))
        self.assertEqual(w[0]["donnees"]["content"][0]["text"], "Submitted 1 job")

    def test_html_en_base64(self):
        blob = base64.b64encode("<b>é</b>".encode()).decode()
        self.assertEqual(collecter([_bloc("ui://a/1", blob=blob)])[0]["contenu"], "<b>é</b>")

    def test_uri_seule_lue_par_resources_read(self):
        lu = NS(text="<div>job</div>", blob=None, mime_type="text/html;profile=mcp-app")
        s = SessionFausse([lu])
        w = collecter([_bloc("ui://hf/job", mime="")], session=s)
        self.assertEqual(s.lectures, ["ui://hf/job"])
        self.assertEqual((w[0]["genre"], w[0]["contenu"]), ("html", "<div>job</div>"))

    def test_lecture_en_echec_donne_repli_texte(self):
        self.assertEqual(collecter([_bloc("ui://hf/job")], session=SessionFausse(erreur=RuntimeError("x"))), [])

    def test_structured_content_transmis(self):
        w = collecter([_bloc("ui://a/1", text="<p/>")], structure={"statut": "en_cours"})
        self.assertEqual(w[0]["donnees"]["structuredContent"], {"statut": "en_cours"})

    def test_url_premiere_adresse_http(self):
        w = collecter([_bloc("ui://a/2", mime="text/uri-list", text="# c\njavascript:alert(1)\nhttps://x.test/w\nhttps://y.test")])
        self.assertEqual((w[0]["genre"], w[0]["contenu"]), ("url", "https://x.test/w"))

    def test_url_sans_http_ignoree(self):
        self.assertEqual(collecter([_bloc("ui://a/2", mime="text/uri-list", text="javascript:alert(1)")]), [])

    def test_type_non_rendu_ignore(self):
        self.assertEqual(collecter([_bloc("ui://a/3", mime="application/vnd.mcp-ui.remote-dom", text="x")]), [])

    def test_uri_non_ui_ignoree(self):
        self.assertEqual(collecter([_bloc("https://x.test/a", text="<p/>")]), [])

    def test_trop_gros_ignore(self):
        gros = "a" * (r.PLAFOND_WIDGET_UI_OCTETS + 1)
        self.assertEqual(collecter([_bloc("ui://a/4", text=gros)]), [])

    def test_doublon_et_plafond_par_resultat(self):
        blocs = [_bloc("ui://a/%d" % (i % 2), text="<p/>") for i in range(10)]
        self.assertEqual([w["uri"] for w in collecter(blocs)], ["ui://a/0", "ui://a/1"])

    def test_interrupteur_eteint(self):
        import os
        os.environ["CLASSINUS_MCP_UI_ACTIF"] = "0"
        try:
            self.assertEqual(collecter([_bloc("ui://a/1", text="<p/>")]), [])
        finally:
            del os.environ["CLASSINUS_MCP_UI_ACTIF"]


LU_MCP_APP = NS(text="<div>presets</div>", blob=None, mime_type="text/html;profile=mcp-app")
TEXTE_SEUL = NS(type="text", text="Presets")


class AdresseDeclaree(unittest.TestCase):
    """MCP Apps (07/11/2026) : le widget est annonce par la definition de l'outil, pas par son resultat."""

    def test_widget_lu_depuis_l_adresse_declaree(self):
        s = SessionFausse([LU_MCP_APP])
        w = collecter([TEXTE_SEUL], session=s, declaree="ui://hf/presets", structure={"n": 1})
        self.assertEqual(s.lectures, ["ui://hf/presets"])
        self.assertEqual((w[0]["uri"], w[0]["genre"], w[0]["contenu"]), ("ui://hf/presets", "html", "<div>presets</div>"))
        self.assertEqual(w[0]["mimeType"], "text/html;profile=mcp-app")
        self.assertEqual(w[0]["donnees"]["structuredContent"], {"n": 1})

    def test_bloc_du_resultat_prioritaire(self):
        s = SessionFausse([LU_MCP_APP])
        w = collecter([_bloc("ui://a/1", text="<p>direct</p>")], session=s, declaree="ui://hf/presets")
        self.assertEqual([x["uri"] for x in w], ["ui://a/1"])
        self.assertEqual(s.lectures, [])

    def test_resultat_en_erreur_sans_widget(self):
        s = SessionFausse([LU_MCP_APP])
        self.assertEqual(collecter([TEXTE_SEUL], session=s, declaree="ui://hf/presets", erreur=True), [])
        self.assertEqual(s.lectures, [])

    def test_lecture_en_echec_donne_repli_texte(self):
        s = SessionFausse(erreur=RuntimeError("x"))
        self.assertEqual(collecter([TEXTE_SEUL], session=s, declaree="ui://hf/presets"), [])

    def test_adresse_non_ui_ignoree(self):
        s = SessionFausse([LU_MCP_APP])
        self.assertEqual(collecter([TEXTE_SEUL], session=s, declaree="https://x.test/w"), [])
        self.assertEqual(s.lectures, [])

    def test_sans_adresse_declaree_rien_ne_change(self):
        s = SessionFausse([LU_MCP_APP])
        self.assertEqual(collecter([TEXTE_SEUL], session=s), [])
        self.assertEqual(s.lectures, [])

    def test_trop_gros_ignore(self):
        gros = NS(text="a" * (r.PLAFOND_WIDGET_UI_OCTETS + 1), blob=None, mime_type="text/html;profile=mcp-app")
        self.assertEqual(collecter([TEXTE_SEUL], session=SessionFausse([gros]), declaree="ui://hf/presets"), [])

    def test_interrupteur_eteint(self):
        import os
        os.environ["CLASSINUS_MCP_UI_ACTIF"] = "0"
        try:
            s = SessionFausse([LU_MCP_APP])
            self.assertEqual(collecter([TEXTE_SEUL], session=s, declaree="ui://hf/presets"), [])
            self.assertEqual(s.lectures, [])
        finally:
            del os.environ["CLASSINUS_MCP_UI_ACTIF"]


class LectureDefinitionOutil(unittest.TestCase):
    def test_forme_de_la_spec(self):
        outil = NS(meta={"ui": {"resourceUri": "ui://hf/presets"}})
        self.assertEqual(r.adresse_widget_declaree(outil), "ui://hf/presets")

    def test_cle_plate_acceptee(self):
        self.assertEqual(r.adresse_widget_declaree(NS(meta={"ui/resourceUri": "ui://hf/p"})), "ui://hf/p")

    def test_rien_a_declarer(self):
        for outil in (NS(meta=None), NS(), NS(meta={}), NS(meta={"ui": {}}), NS(meta="x"), NS(meta={"ui": "x"}), None):
            self.assertIsNone(r.adresse_widget_declaree(outil), repr(outil))

    def test_adresse_qui_n_est_pas_ui_ignoree(self):
        for adresse in ("https://x.test", "javascript:1", 5, ["ui://a"]):
            self.assertIsNone(r.adresse_widget_declaree(NS(meta={"ui": {"resourceUri": adresse}})), repr(adresse))

    def test_vrai_objet_tool_du_sdk(self):
        try:
            from mcp.types import Tool
        except Exception as erreur:  # bibliotheque MCP absente de cet environnement
            self.skipTest(f"SDK mcp non importable ici : {erreur}")
        declare = Tool(name="get_presets", input_schema={"type": "object"}, _meta={"ui": {"resourceUri": "ui://hf/presets"}})
        self.assertEqual(r.adresse_widget_declaree(declare), "ui://hf/presets")
        self.assertIsNone(r.adresse_widget_declaree(Tool(name="autre", input_schema={"type": "object"})))


class TransmissionAuxAppels(unittest.TestCase):
    """L'adresse gardee dans la route de l'outil arrive bien jusqu'a l'appel MCP, et seulement alors."""

    def setUp(self):
        try:
            from core import mcp_tools
        except Exception as erreur:  # bibliotheque MCP absente de cet environnement
            self.skipTest(f"mcp_tools non importable ici : {erreur}")
        self.mcp_tools = mcp_tools

    def _appeler(self, route):
        recus = []

        async def faux(url, nom, arguments, headers=None, **plus):
            recus.append(plus)
            return "ok"

        with patch.object(self.mcp_tools, "_appeler_outil_async", faux):
            self.mcp_tools.appeler_outil("higgsfield_get_presets", {}, {"higgsfield_get_presets": route})
        return recus

    def test_adresse_transmise_quand_declaree(self):
        route = {"url": "https://x.test", "headers": {}, "nom_reel": "get_presets", "widget_ui_uri": "ui://hf/presets"}
        self.assertEqual(self._appeler(route), [{"adresse_widget": "ui://hf/presets"}])

    def test_rien_transmis_sinon(self):
        route = {"url": "https://x.test", "headers": {}, "nom_reel": "get_presets"}
        self.assertEqual(self._appeler(route), [{}])


class Enveloppe(unittest.TestCase):
    def test_sans_widget_texte_inchange(self):
        self.assertEqual(r.joindre_ressources_ui("Submitted 1 job", []), "Submitted 1 job")
        self.assertEqual(r.separer_ressources_ui("Submitted 1 job"), ("Submitted 1 job", []))

    def test_aller_retour_texte(self):
        w = [{"uri": "ui://a/1", "genre": "html", "contenu": "<p/>"}]
        env = r.joindre_ressources_ui("Submitted 1 job", w)
        self.assertEqual(r.separer_ressources_ui(env), ("Submitted 1 job", w))

    def test_aller_retour_json_avec_images(self):
        w = [{"uri": "ui://a/1", "genre": "html", "contenu": "<p/>"}]
        base = json.dumps({"text": "t", "images": [{"url": "https://x/a.png"}]})
        texte, widgets = r.separer_ressources_ui(r.joindre_ressources_ui(base, w))
        self.assertEqual(widgets, w)
        self.assertEqual(json.loads(texte), {"text": "t", "images": [{"url": "https://x/a.png"}]})

    def test_widget_gros_survit_a_la_troncature_d_affichage(self):
        # Le HTML est separe du texte avant la coupe a 3000 caracteres.
        w = [{"uri": "ui://a/1", "genre": "html", "contenu": "x" * 50000}]
        texte, widgets = r.separer_ressources_ui(r.joindre_ressources_ui("ok", w))
        self.assertEqual(texte, "ok")
        self.assertEqual(len(widgets[0]["contenu"]), 50000)

    def test_json_invalide_ne_leve_pas(self):
        self.assertEqual(r.separer_ressources_ui("{" + r.CLE_ENVELOPPE), ("{" + r.CLE_ENVELOPPE, []))


if __name__ == "__main__":
    unittest.main()
