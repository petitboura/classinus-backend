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

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "core"))

from core import ressources_ui as r  # noqa: E402


def _bloc(uri, mime="text/html", text=None, blob=None):
    return NS(type="resource", resource=NS(uri=uri, mime_type=mime, text=text, blob=blob))


def _resultat(blocs, structure=None):
    return NS(content=blocs, structured_content=structure)


class SessionFausse:
    def __init__(self, contenus=None, erreur=None):
        self.contenus, self.erreur, self.lectures = contenus or [], erreur, []

    async def read_resource(self, uri):
        self.lectures.append(uri)
        if self.erreur:
            raise self.erreur
        return NS(contents=self.contenus)


def collecter(blocs, session=None, texte="Submitted 1 job", structure=None):
    return asyncio.run(r.collecter_ressources_ui(session or SessionFausse(), _resultat(blocs, structure), texte))


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
