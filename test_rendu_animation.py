"""Rendu vidéo des animations : file d'attente, droits d'accès et rendu réel.

Les premiers tests n'ouvrent aucun navigateur. Le dernier lance le vrai
script de rendu sur une page minimale et est ignoré si le navigateur ou
ffmpeg ne sont pas installés.
"""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from core import rendu_animation_travaux as travaux
from core.rendu_animation_constantes import ATTENTE_MAX, FICHIER_THREE, SCRIPT_PROCESSUS

DOCUMENT = "<html><body><script>window.__ANIM_CONF={};</script></body></html>"


class FileEtDroits(unittest.TestCase):
    def setUp(self):
        travaux._travaux.clear()
        self._soumission = patch.object(travaux._executeur, "submit")
        self._soumission.start()

    def tearDown(self):
        self._soumission.stop()
        for t in list(travaux._travaux):
            travaux._supprimer_fichiers(t)
        travaux._travaux.clear()

    def test_format_inconnu_refuse(self):
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.creer_travail("u1", "4:3", DOCUMENT)
        self.assertEqual(e.exception.code, "RENDU_VIDEO_FORMAT_INVALIDE")

    def test_page_quelconque_refusee(self):
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.creer_travail("u1", "9:16", "<html><script>alert(1)</script></html>")
        self.assertEqual(e.exception.code, "RENDU_VIDEO_DOCUMENT_INVALIDE")

    def test_document_trop_lourd_refuse(self):
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.creer_travail("u1", "9:16", DOCUMENT + "x" * 1_600_000)
        self.assertEqual(e.exception.code, "RENDU_VIDEO_DOCUMENT_TROP_LOURD")

    def test_une_seule_demande_active_par_personne(self):
        travaux.creer_travail("u1", "9:16", DOCUMENT)
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.creer_travail("u1", "16:9", DOCUMENT)
        self.assertEqual(e.exception.code, "RENDU_VIDEO_DEJA_EN_COURS")
        travaux.creer_travail("u2", "16:9", DOCUMENT)

    def test_file_pleine(self):
        for i in range(ATTENTE_MAX):
            travaux.creer_travail(f"u{i}", "9:16", DOCUMENT)
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.creer_travail("autre", "9:16", DOCUMENT)
        self.assertEqual(e.exception.code, "RENDU_VIDEO_OCCUPE")

    def test_travail_d_un_autre_introuvable(self):
        t = travaux.creer_travail("u1", "9:16", DOCUMENT)
        with self.assertRaises(travaux.ErreurRendu) as e:
            travaux.lire_travail(t.id, "u2")
        self.assertEqual(e.exception.statut_http, 404)
        with self.assertRaises(travaux.ErreurRendu):
            travaux.annuler_travail(t.id, "u2")
        self.assertFalse(t.annule.is_set())

    def test_annulation_libere_la_personne(self):
        t = travaux.creer_travail("u1", "9:16", DOCUMENT)
        travaux.annuler_travail(t.id, "u1")
        self.assertTrue(t.annule.is_set())
        travaux._terminer(t, "annule")
        travaux.creer_travail("u1", "9:16", DOCUMENT)

    def test_travaux_termines_oublies_apres_conservation(self):
        t = travaux.creer_travail("u1", "9:16", DOCUMENT)
        travaux._terminer(t, "echec", "RENDU_VIDEO_ECHEC")
        t.termine_a -= 10_000
        with self.assertRaises(travaux.ErreurRendu):
            travaux.lire_travail(t.id, "u1")

    def test_message_d_erreur_dans_l_etat(self):
        t = travaux.creer_travail("u1", "9:16", DOCUMENT)
        travaux._terminer(t, "echec", "RENDU_VIDEO_TROP_LONGUE")
        corps = travaux.serialiser(t)
        self.assertEqual(corps["code_erreur"], "RENDU_VIDEO_TROP_LONGUE")
        self.assertIn("trop longue", corps["message_erreur"])


PAGE_MINIMALE = """<!DOCTYPE html><html><body style="margin:0">
<div id="f" style="width:100vw;height:100vh;background:#fff"></div>
<script>
window.__ANIM_CONF = {};
window.__rendu = {
  etat: function () { return 'pret'; },
  info: function () { return { duree: 1 }; },
  aller: function (t) { document.getElementById('f').style.background = t > 0.5 ? '#000' : '#fff'; return ''; }
};
</script></body></html>"""


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent")
class RenduReel(unittest.TestCase):
    def test_une_page_devient_une_video(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            document = Path(d) / "document.html"
            document.write_text(PAGE_MINIMALE, encoding="utf-8")
            sortie = Path(d) / "video.mp4"
            r = subprocess.run(
                [sys.executable, str(SCRIPT_PROCESSUS), "--document", str(document), "--sortie", str(sortie),
                 "--largeur", "320", "--hauteur", "180", "--fps", "10", "--duree-max", "10",
                 "--maintien-fin", "0.5", "--delai-chargement", "10", "--three", str(FICHIER_THREE)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 4:
                self.skipTest("navigateur du rendu non installé")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertGreater(sortie.stat().st_size, 0)
            duree = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(sortie)],
                capture_output=True, text=True,
            ).stdout.strip()
            self.assertAlmostEqual(float(duree), 1.6, delta=0.15)


if __name__ == "__main__":
    unittest.main()
