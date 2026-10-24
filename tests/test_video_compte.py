"""Vidéos du montage et compte : export, suppression, et absence de nettoyage.

Un faux stockage R2 en mémoire remplace le vrai : on vérifie que seuls les
objets de CET utilisateur sont listés et supprimés, et que le cache local part.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SUPABASE_SECRET", "test-only-video-account-secret")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("R2_ENDPOINT", "https://example.invalid")
os.environ.setdefault("R2_BUCKET_NAME", "test")

from core import video_workspaces as vw


class FauxStockage:
    def __init__(self, objets=None, echec_remove=False):
        self.objets = dict(objets or {})
        self.echec_remove = echec_remove
        self.lots = []

    def lister(self, prefixe):
        return sorted(c for c in self.objets if c.startswith(prefixe))

    def download(self, chemin):
        return self.objets[chemin]

    def remove(self, chemins):
        self.lots.append(list(chemins))
        if self.echec_remove:
            raise RuntimeError("R2 indisponible")
        for chemin in chemins:
            self.objets.pop(chemin, None)


class TestVideosCompte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch_root = mock.patch.object(vw, "ROOT", Path(self.tmp.name).resolve())
        patch_root.start()
        self.addCleanup(patch_root.stop)

        self.seg_a = vw._segment("user-a")
        self.seg_b = vw._segment("user-b")
        meta = lambda vid, nom: json.dumps({
            "video_id": vid, "nom_fichier": nom, "taille_octets": 10,
            "type_mime": "video/mp4", "duree_secondes": 3.5,
        }).encode()
        self.stockage = FauxStockage({
            f"montages-video/originaux/{self.seg_a}/c1/{'a' * 32}.mp4": b"x",
            f"montages-video/originaux/{self.seg_a}/c1/{'a' * 32}.json": meta("a" * 32, "cours.mp4"),
            f"montages-video/originaux/{self.seg_a}/c2/{'b' * 32}.json": meta("b" * 32, "tp.mp4"),
            f"montages-video/workspaces/{self.seg_a}/c1/outputs/final.mp4": b"y",
            f"montages-video/workspaces/{self.seg_a}/c1/manifest.json": b"{}",
            f"montages-video/originaux/{self.seg_b}/c9/{'c' * 32}.mp4": b"autre",
            f"montages-video/workspaces/{self.seg_b}/c9/outputs/autre.mp4": b"autre",
        })
        faux_module = types.SimpleNamespace(from_=lambda _bucket: self.stockage)
        patcher = mock.patch.dict(sys.modules, {"core.stockage_r2": faux_module})
        patcher.start()
        self.addCleanup(patcher.stop)
        patch_attr = mock.patch.object(sys.modules["core"], "stockage_r2", faux_module, create=True)
        patch_attr.start()
        self.addCleanup(patch_attr.stop)

    def test_export_decrit_les_videos_du_compte_sans_les_contenus(self):
        resultat = vw.lister_videos_utilisateur("user-a")
        noms = sorted(v["nom_fichier"] for v in resultat["videos_importees"])
        self.assertEqual(noms, ["cours.mp4", "tp.mp4"])
        self.assertEqual(resultat["fichiers_produits"], 1)
        self.assertNotIn("autre", json.dumps(resultat))

    def test_suppression_efface_tout_le_compte_et_rien_d_autre(self):
        dossier_local = vw.ROOT / self.seg_a / "c1" / "uploads"
        dossier_local.mkdir(parents=True)
        (dossier_local / "cache.mp4").write_bytes(b"z")
        autre_local = vw.ROOT / self.seg_b / "c9"
        autre_local.mkdir(parents=True)

        bilan = vw.supprimer_videos_utilisateur("user-a")

        self.assertEqual(bilan, {"supprimes": 5, "en_echec": 0})
        restants = list(self.stockage.objets)
        self.assertTrue(all(self.seg_b in c for c in restants))
        self.assertEqual(len(restants), 2)
        self.assertFalse((vw.ROOT / self.seg_a).exists())
        self.assertTrue(autre_local.exists())

    def test_suppression_par_lots_de_mille(self):
        for i in range(2500):
            self.stockage.objets[f"montages-video/workspaces/{self.seg_a}/c1/outputs/f{i}.mp4"] = b"x"
        bilan = vw.supprimer_videos_utilisateur("user-a")
        self.assertEqual(bilan["en_echec"], 0)
        self.assertTrue(all(len(lot) <= 1000 for lot in self.stockage.lots))
        self.assertEqual(sum(len(lot) for lot in self.stockage.lots), bilan["supprimes"])

    def test_une_panne_r2_est_signalee_sans_faire_planter_la_suppression(self):
        self.stockage.echec_remove = True
        with self.assertLogs(level="ERROR"):
            bilan = vw.supprimer_videos_utilisateur("user-a")
        self.assertEqual(bilan["supprimes"], 0)
        self.assertEqual(bilan["en_echec"], 5)

    def test_aucun_nettoyage_automatique_n_existe(self):
        source = Path(vw.__file__).read_text(encoding="utf-8").lower()
        for mot in ("ttl", "retention", "expire_apres", "nettoyer_"):
            self.assertNotIn(mot, source)


class TestListerR2(unittest.TestCase):
    def test_lister_parcourt_toutes_les_pages(self):
        from core import stockage_r2

        pages = [
            {"Contents": [{"Key": "images-publiques/p/a"}], "IsTruncated": True, "NextContinuationToken": "t1"},
            {"Contents": [{"Key": "images-publiques/p/b"}], "IsTruncated": False},
        ]
        appels = []

        class FauxClient:
            def list_objects_v2(self, **kwargs):
                appels.append(kwargs)
                return pages[len(appels) - 1]

        with mock.patch.object(stockage_r2, "_client", FauxClient()):
            chemins = stockage_r2.from_("images-publiques").lister("p/")
        self.assertEqual(chemins, ["p/a", "p/b"])
        self.assertEqual(appels[0]["Prefix"], "images-publiques/p/")
        self.assertEqual(appels[1]["ContinuationToken"], "t1")


if __name__ == "__main__":
    unittest.main()
