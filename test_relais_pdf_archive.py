"""Relais des PDF Internet Archive : aucun accès réseau, l'amont est simulé."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from core import relais_pdf_archive as rel
from core import lecture_document_archive as lda

PDF = b"%PDF-1.4 " + b"x" * 3000


def _amont(statut=200, contenu=PDF, entetes=None, url="https://ia800.us.archive.org/1/items/livre/livre.pdf", historique=()):
    r = MagicMock()
    r.status_code = statut
    r.headers = entetes if entetes is not None else {"Content-Length": str(len(contenu))}
    r.url = url
    r.history = [MagicMock(url=u) for u in historique]
    r.iter_content.side_effect = lambda n: iter([contenu[i:i + n] for i in range(0, len(contenu), n)])
    return r


def _meta(restreint=False, taille="3000"):
    return {
        "metadata": {"title": "Livre", **({"access-restricted-item": "true"} if restreint else {})},
        "files": [{"name": "livre.pdf", "format": "Text PDF", "size": taille}],
    }


def _client():
    from api.fichiers_archive import router
    from core.limitation_debit import limiteur
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    app.state.limiter = limiteur
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.include_router(router)
    return TestClient(app)


class Relais(unittest.TestCase):
    def setUp(self):
        rel._memoire.clear()
        self.client = _client()

    def _simuler(self, meta=None, amont=None):
        return (
            patch.object(rel, "_recuperer_metadonnees", return_value=meta or _meta()),
            patch.object(rel.requests, "request", return_value=amont or _amont()),
        )

    def test_get_complet_sans_compression(self):
        p1, p2 = self._simuler()
        with p1, p2:
            r = self.client.get("/fichiers/archive/livre.pdf", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, PDF)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertEqual(r.headers["accept-ranges"], "bytes")
        self.assertEqual(r.headers["content-encoding"], "identity")
        self.assertIn("Content-Range", r.headers["access-control-expose-headers"])

    def test_requete_partielle_transmise(self):
        partiel = _amont(206, PDF[:100], {"Content-Length": "100", "Content-Range": f"bytes 0-99/{len(PDF)}"})
        p1, p2 = self._simuler(amont=partiel)
        with p1, p2 as appel:
            r = self.client.get("/fichiers/archive/livre.pdf", headers={"Range": "bytes=0-99"})
            self.assertEqual(appel.call_args.kwargs["headers"], {"Range": "bytes=0-99"})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.content, PDF[:100])
        self.assertEqual(r.headers["content-range"], f"bytes 0-99/{len(PDF)}")

    def test_head(self):
        p1, p2 = self._simuler()
        with p1, p2 as appel:
            r = self.client.head("/fichiers/archive/livre.pdf")
            self.assertEqual(appel.call_args.args[0], "HEAD")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-length"], str(len(PDF)))

    def test_pret_numerique_refuse(self):
        p1, p2 = self._simuler(meta=_meta(restreint=True))
        with p1, p2 as appel:
            r = self.client.get("/fichiers/archive/livre.pdf")
            appel.assert_not_called()
        self.assertEqual(r.status_code, 403)

    def test_acces_refuse_en_amont(self):
        p1, p2 = self._simuler(amont=_amont(403))
        with p1, p2:
            self.assertEqual(self.client.get("/fichiers/archive/livre.pdf").status_code, 403)

    def test_plafond_selon_metadonnees(self):
        p1, p2 = self._simuler(meta=_meta(taille=str(10**10)))
        with p1, p2 as appel:
            r = self.client.get("/fichiers/archive/livre.pdf")
            appel.assert_not_called()
        self.assertEqual(r.status_code, 413)

    def test_plafond_selon_amont(self):
        gros = _amont(200, b"x", {"Content-Length": str(10**10)})
        p1, p2 = self._simuler(amont=gros)
        with p1, p2:
            self.assertEqual(self.client.get("/fichiers/archive/livre.pdf").status_code, 413)

    def test_flux_coupe_au_plafond(self):
        menteur = _amont(200, PDF, {})  # n'annonce aucune taille
        with patch.dict("os.environ", {"ARCHIVE_RELAIS_TAILLE_MAX": "1000"}):
            p1, p2 = self._simuler(amont=menteur)
            with p1, p2:
                r = self.client.get("/fichiers/archive/livre.pdf")
        self.assertLessEqual(len(r.content), 1000)

    def test_redirection_hors_archive_refusee(self):
        p1, p2 = self._simuler(amont=_amont(url="https://evil.example.com/x.pdf", historique=["https://archive.org/download/livre/livre.pdf"]))
        with p1, p2:
            self.assertEqual(self.client.get("/fichiers/archive/livre.pdf").status_code, 502)

    def test_noms_refuses(self):
        for nom in ("livre", "livre.txt", "..%2Fx.pdf"):
            self.assertIn(self.client.get(f"/fichiers/archive/{nom}").status_code, (404, 422))

    def test_document_inconnu(self):
        with patch.object(rel, "_recuperer_metadonnees", side_effect=lda._DocumentIllisible("x")):
            self.assertEqual(self.client.get("/fichiers/archive/inconnu.pdf").status_code, 404)

    def test_lien_du_visionneur(self):
        self.assertEqual(rel.url_visionneur("livre_2020", "https://api.classinus.com/"), "https://api.classinus.com/fichiers/archive/livre_2020.pdf")
        self.assertEqual(rel.identifiant_depuis_nom("livre_2020.pdf"), "livre_2020")
        self.assertIsNone(rel.identifiant_depuis_nom("livre_2020"))


if __name__ == "__main__":
    unittest.main()
