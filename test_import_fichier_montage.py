"""
Tests du pont fichiers joints -> montage vidéo (26/10/2026). Les médias sont de
VRAIS fichiers fabriqués avec ffmpeg et analysés par le vrai ffprobe ; seuls le
stockage distant (R2) et la base (fichiers_uploades) sont simulés. Ils vérifient
la logique et les frontières d'accès, pas l'accord avec R2 ni Supabase : à
confirmer sur staging avec un vrai fichier joint.
"""

import os
import re
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SUPABASE_SECRET", "test-only-secret")
sys.path.append("core")

import core.import_fichier_montage as pont  # noqa: E402
import core.serveur_mcp_video as serveur  # noqa: E402
import core.video_workspaces as espaces  # noqa: E402


class FauxStockage:
    def __init__(self):
        self.objets = {}

    def upload(self, chemin, contenu, options=None):
        self.objets[chemin] = bytes(contenu)

    def download(self, chemin):
        if chemin not in self.objets:
            raise FileNotFoundError(chemin)
        return self.objets[chemin]

    def download_to_file(self, chemin, destination):
        Path(destination).write_bytes(self.download(chemin))

    def remove(self, chemins):
        for chemin in chemins:
            self.objets.pop(chemin, None)


def _fabriquer(chemin, *arguments):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *arguments, str(chemin)], check=True)
    return chemin.read_bytes()


@pytest.fixture(scope="module")
def medias(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("medias")
    return {
        "video": _fabriquer(dossier / "cours.mp4", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3",
                            "-f", "lavfi", "-i", "sine=duration=3", "-shortest", "-pix_fmt", "yuv420p"),
        "audio": _fabriquer(dossier / "musique.wav", "-f", "lavfi", "-i", "sine=frequency=330:duration=4"),
        "image": _fabriquer(dossier / "schema.png", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=1", "-frames:v", "1"),
    }


@pytest.fixture
def monde(tmp_path, monkeypatch):
    """Faux stockage, dossier de travail isolé et table de fichiers joints simulée."""
    stockage = FauxStockage()
    monkeypatch.setattr(espaces, "ROOT", tmp_path / "instance-a")
    fichiers = {}

    def retrouver(url, user_id):
        ligne = fichiers.get(url)
        if ligne is None or ligne["user_id"] != user_id:
            return None
        return ligne["meta"], ligne["contenu"]

    monkeypatch.setattr(pont, "retrouver_fichier", retrouver)
    with patch("core.stockage_r2.from_", return_value=stockage):
        yield types.SimpleNamespace(stockage=stockage, fichiers=fichiers, racine=tmp_path)


def _joindre(monde, url, nom, mime, contenu, user="u1"):
    monde.fichiers[url] = {"user_id": user, "meta": {"nom_fichier": nom, "type_mime": mime}, "contenu": contenu}


def test_import_video(monde, medias):
    _joindre(monde, "https://r2/v", "cours.mp4", "video/mp4", medias["video"])
    r = pont.importer_fichier_conversation("u1", "conv1", "https://r2/v")
    assert r["success"] and r["type"] == "video"
    assert re.fullmatch(r"uploads/[0-9a-f]{32}\.mp4", r["source_path"])
    assert 2.5 < r["duree_secondes"] < 3.5
    racine = espaces.workspace_dir("u1", "conv1", create=False)
    assert (racine / r["source_path"]).is_file()


def test_import_audio_avec_type_mime_variante(monde, medias):
    _joindre(monde, "https://r2/a", "musique.wav", "audio/x-wav", medias["audio"])
    r = pont.importer_fichier_conversation("u1", "conv1", "https://r2/a")
    assert r["success"] and r["type"] == "audio" and r["source_path"].endswith(".wav")
    assert 3.5 < r["duree_secondes"] < 4.5


def test_import_image(monde, medias):
    _joindre(monde, "https://r2/i", "schema.png", "image/png", medias["image"])
    r = pont.importer_fichier_conversation("u1", "conv1", "https://r2/i")
    assert r["success"] and r["type"] == "image" and r["source_path"].endswith(".png")
    assert r["duree_secondes"] is None


def test_type_mime_avec_parametres_et_absent(monde, medias):
    _joindre(monde, "https://r2/w", "voix.webm", "audio/webm;codecs=opus", medias["audio"])
    assert pont.importer_fichier_conversation("u1", "c", "https://r2/w")["source_path"].endswith(".webm")
    _joindre(monde, "https://r2/s", "musique.wav", "", medias["audio"])  # type absent : déduit du nom
    assert pont.importer_fichier_conversation("u1", "c", "https://r2/s")["success"]


def test_fichier_d_un_autre_compte_refuse(monde, medias):
    _joindre(monde, "https://r2/v", "cours.mp4", "video/mp4", medias["video"], user="proprietaire")
    r = pont.importer_fichier_conversation("intrus", "conv1", "https://r2/v")
    assert not r["success"] and "introuvable" in r["error"]
    assert monde.stockage.objets == {}


def test_document_refuse(monde):
    _joindre(monde, "https://r2/d", "cours.pdf", "application/pdf", b"%PDF-1.4")
    r = pont.importer_fichier_conversation("u1", "conv1", "https://r2/d")
    assert not r["success"] and "vidéo, un audio ou une image" in r["error"]


def test_media_illisible_refuse(monde):
    _joindre(monde, "https://r2/f", "faux.mp4", "video/mp4", b"pas une video")
    r = pont.importer_fichier_conversation("u1", "conv1", "https://r2/f")
    assert not r["success"] and "pas un média lisible" in r["error"]
    assert monde.stockage.objets == {}


def test_url_vide_et_stockage_en_panne(monde, medias, monkeypatch):
    assert not pont.importer_fichier_conversation("u1", "c", "  ")["success"]
    _joindre(monde, "https://r2/v", "cours.mp4", "video/mp4", medias["video"])

    def panne(**_):
        raise RuntimeError("r2 down")

    monkeypatch.setattr(pont, "enregistrer_video", panne)
    r = pont.importer_fichier_conversation("u1", "c", "https://r2/v")
    assert not r["success"] and "indisponible" in r["error"]


def test_le_chemin_renvoye_est_accepte_par_les_outils_de_montage(monde, medias):
    for url, nom, mime, cle in [("https://r2/v", "cours.mp4", "video/mp4", "video"),
                                ("https://r2/a", "musique.wav", "audio/wav", "audio"),
                                ("https://r2/i", "schema.png", "image/png", "image")]:
        _joindre(monde, url, nom, mime, medias[cle])
        r = pont.importer_fichier_conversation("u1", "conv1", url)
        racine = espaces.workspace_dir("u1", "conv1", create=False)
        args = serveur._normaliser_arguments("video_trim", {"input_path": r["source_path"], "output_path": "outputs/sortie.mp4"}, racine)
        assert Path(args["input_path"]) == (racine / r["source_path"]).resolve()


def test_source_restauree_sur_une_autre_instance_pour_audio_et_image(monde, medias, monkeypatch, tmp_path):
    chemins = {}
    for url, nom, mime, cle in [("https://r2/a", "musique.wav", "audio/wav", "audio"),
                                ("https://r2/i", "schema.png", "image/png", "image")]:
        _joindre(monde, url, nom, mime, medias[cle])
        chemins[cle] = pont.importer_fichier_conversation("u1", "conv1", url)["source_path"]

    # Autre instance Railway : même stockage durable, dossier local vide.
    monkeypatch.setattr(espaces, "ROOT", tmp_path / "instance-b")
    racine_b = espaces.workspace_dir("u1", "conv1")
    for chemin in chemins.values():
        assert not (racine_b / chemin).exists()
    serveur._restaurer_sources_dans_arguments({"input_path": chemins["audio"], "image": chemins["image"]}, "u1", "conv1")
    for chemin in chemins.values():
        assert (racine_b / chemin).is_file()

    # Une autre conversation ne voit jamais ces sources.
    with pytest.raises(Exception):
        serveur._restaurer_sources_dans_arguments({"input_path": chemins["audio"]}, "u1", "conv-autre")


def _ctx(user, conv, secret="test-only-secret"):
    requete = types.SimpleNamespace(
        headers={"authorization": f"Bearer {secret}"},
        query_params={"user_id": user, "conversation_id": conv},
    )
    return types.SimpleNamespace(request_context=types.SimpleNamespace(request=requete))


def test_outil_mcp_de_bout_en_bout(monde, medias):
    _joindre(monde, "https://r2/v", "cours.mp4", "video/mp4", medias["video"])
    r = serveur.video_importer_fichier_conversation(_ctx("u1", "conv1"), "https://r2/v")
    assert r["success"] and r["source_path"].startswith("uploads/")
    with pytest.raises(PermissionError):
        serveur.video_importer_fichier_conversation(_ctx("u1", "conv1", secret="faux"), "https://r2/v")
    with pytest.raises(PermissionError):
        serveur.video_importer_fichier_conversation(_ctx("u1", ""), "https://r2/v")


def test_la_route_de_depot_video_n_accepte_toujours_que_des_videos():
    # EXTENSIONS_MIME est maintenant plus large (audio, image), la route non.
    import api.uploads as uploads
    assert set(uploads.TYPES_VIDEO_AUTORISES) <= {"video/mp4", "video/webm", "video/quicktime"}
