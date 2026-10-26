"""
Tests de la lecture à la demande d'une vidéo ou d'un audio joint (26/10/2026).
Les fichiers sont de VRAIS médias fabriqués ici avec ffmpeg (une vidéo de 6 s avec
son, une vidéo muette, un audio de 5 s), analysés par le vrai ffprobe. Seuls les
services distants sont simulés : Whisper (Groq), Gemini et le stockage. Ces
tests vérifient la logique, pas l'accord avec Groq et Gemini : à confirmer en
production avec un vrai fichier.
"""

import re
import subprocess
import sys

import pytest

sys.path.append("core")  # comme les autres tests

import core.lecture_media_conversation as lecteur  # noqa: E402
from core import limites_media  # noqa: E402


def _fabriquer(chemin, *arguments):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *arguments, str(chemin)], check=True)


@pytest.fixture(scope="module")
def video_avec_son(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("media") / "cours.mp4"
    _fabriquer(
        chemin, "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest",
        "-pix_fmt", "yuv420p",
    )
    return chemin


@pytest.fixture(scope="module")
def video_muette(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("media") / "muette.mp4"
    _fabriquer(chemin, "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3", "-pix_fmt", "yuv420p")
    return chemin


@pytest.fixture(scope="module")
def audio_seul(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("media") / "dictee.wav"
    _fabriquer(chemin, "-f", "lavfi", "-i", "sine=frequency=330:duration=5")
    return chemin


# --- informations -----------------------------------------------------------

def test_infos_video_avec_son(video_avec_son):
    infos = lecteur.lire_infos(str(video_avec_son))
    assert 5.5 < infos["duree_secondes"] < 6.5
    assert infos["a_audio"] and infos["a_video"]
    assert (infos["largeur"], infos["hauteur"]) == (320, 240)
    assert infos["fps"] == 10


def test_infos_video_muette(video_muette):
    infos = lecteur.lire_infos(str(video_muette))
    assert infos["a_video"] and not infos["a_audio"]
    assert "sans piste audio" in lecteur.resume_infos(infos)


def test_infos_audio_seul(audio_seul):
    infos = lecteur.lire_infos(str(audio_seul))
    assert infos["a_audio"] and not infos["a_video"]
    assert infos["largeur"] is None
    resume = lecteur.resume_infos(infos)
    assert not re.search(r"\d+x\d+", resume) and "0:05" in resume


def test_fichier_illisible_leve_une_exception(tmp_path):
    faux = tmp_path / "faux.mp4"
    faux.write_bytes(b"ceci n'est pas une video")
    with pytest.raises(Exception):
        lecteur.lire_infos(str(faux))


def test_formats():
    assert lecteur.formater_duree(92) == "1:32"
    assert lecteur.formater_duree(3723) == "1:02:03"
    assert lecteur.formater_taille(12_990_000).endswith("Mo") and "," in lecteur.formater_taille(12_990_000)
    assert lecteur.formater_taille(2048) == "2 Ko"


# --- détection dans le message ---------------------------------------------

def test_media_joint_present():
    assert lecteur.media_joint_present("\n\n[Vidéo jointe : a.mp4 -- 0:06]", [])
    assert lecteur.media_joint_present("Et la suite ?", [{"role": "user", "content": "x\n\n[Audio joint : a.mp3 -- 1:00]"}])
    # Un marqueur écrit par l'assistant ne compte pas : seul l'étudiant joint des fichiers.
    assert not lecteur.media_joint_present("salut", [{"role": "assistant", "content": "[Vidéo jointe : a.mp4]"}])
    assert not lecteur.media_joint_present("salut", None)


# --- lecture par l'outil ----------------------------------------------------

@pytest.fixture
def faux_services(monkeypatch):
    """Simule le stockage, Whisper et Gemini ; renvoie les appels reçus pour les vérifier."""
    appels = {"transcription": [], "images": []}

    def transcrire(contenu_wav, langue):
        appels["transcription"].append((len(contenu_wav), langue))
        return [{"text": "Bonjour à tous.", "start": 0.5}, {"text": "Voici le théorème.", "start": 3.0}], "fr"

    def decrire(contenu, mime):
        appels["images"].append(len(contenu))
        return "Un damier coloré."

    import core.description_multimedia as dm
    monkeypatch.setattr(lecteur, "_transcrire_wav", transcrire)
    monkeypatch.setattr(dm, "decrire_image_bibliotheque", decrire)
    return appels


def _brancher_fichier(monkeypatch, chemin, nom, user="u1"):
    contenu = chemin.read_bytes()

    def retrouver(url, user_id):
        if user_id != user or not url.endswith(nom):
            return None
        return {"nom_fichier": nom}, contenu

    monkeypatch.setattr(lecteur, "retrouver_fichier", retrouver)


def test_mode_infos_ne_consulte_aucun_service(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "infos")
    assert "cours.mp4" in texte and "320x240" in texte and "avec son" in texte
    assert faux_services == {"transcription": [], "images": []}


def test_transcription_avec_reperes_et_langue_detectee(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "transcription")
    assert "[0:00] Bonjour à tous." in texte and "[0:03] Voici le théorème." in texte
    assert "langue détectée : fr" in texte
    assert faux_services["transcription"][0][1] is None  # détection automatique par défaut
    assert faux_services["images"] == []


def test_transcription_decale_les_reperes_selon_le_debut(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "transcription", debut_secondes=2, langue="en")
    assert "[0:02] Bonjour à tous." in texte and "[0:05] Voici le théorème." in texte
    assert faux_services["transcription"][0][1] == "en"


def test_transcription_longue_propose_la_suite(video_avec_son, monkeypatch, faux_services):
    monkeypatch.setenv("MEDIA_TRANCHE_TRANSCRIPTION_SECONDES", "2")
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "transcription")
    assert "debut_secondes=2" in texte


def test_images_decrites_avec_leur_instant(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "images", nb_images=3)
    assert texte.count("Un damier coloré.") == 3
    assert len(faux_services["images"]) == 3 and all(taille > 0 for taille in faux_services["images"])
    assert faux_services["transcription"] == []


def test_une_seule_image_a_un_instant_precis(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "images", debut_secondes=4, fin_secondes=4, nb_images=1)
    assert "[0:04] Un damier coloré." in texte


def test_nombre_d_images_plafonne_par_la_configuration(video_avec_son, monkeypatch, faux_services):
    monkeypatch.setenv("MEDIA_IMAGES_MAX", "2")
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    lecteur.lire_media("https://x/cours.mp4", "u1", "images", nb_images=50)
    assert len(faux_services["images"]) == 2


def test_les_deux(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "les_deux", nb_images=2)
    assert "Voici le théorème." in texte and texte.count("Un damier coloré.") == 2


def test_video_muette_pas_de_transcription_mais_des_images(video_muette, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_muette, "muette.mp4")
    texte = lecteur.lire_media("https://x/muette.mp4", "u1", "les_deux", nb_images=2)
    assert "pas de piste audio" in texte and "Un damier coloré." in texte
    assert faux_services["transcription"] == []


def test_audio_seul_pas_d_images(audio_seul, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, audio_seul, "dictee.wav")
    texte = lecteur.lire_media("https://x/dictee.wav", "u1", "les_deux")
    assert "Voici le théorème." in texte and "audio seul" in texte
    assert faux_services["images"] == []


def test_fichier_d_un_autre_compte_refuse(video_avec_son, monkeypatch, faux_services):
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4", user="u1")
    texte = lecteur.lire_media("https://x/cours.mp4", "autre", "transcription")
    assert texte.startswith("Erreur") and "introuvable" in texte
    assert faux_services["transcription"] == []


def test_entrees_invalides(monkeypatch):
    assert "mode inconnu" in lecteur.lire_media("https://x/a.mp4", "u1", "regarder")
    assert "url_fichier manquant" in lecteur.lire_media("", "u1", "infos")


def test_fichier_non_media_donne_un_message_clair(tmp_path, monkeypatch, faux_services):
    faux = tmp_path / "notes.mp4"
    faux.write_bytes(b"pas une video")
    _brancher_fichier(monkeypatch, faux, "notes.mp4")
    assert "pas un audio ou une vidéo lisible" in lecteur.lire_media("https://x/notes.mp4", "u1", "infos")


def test_echec_whisper_ne_leve_pas_d_exception(video_avec_son, monkeypatch, faux_services):
    def echec(*_):
        raise RuntimeError("groq indisponible")

    monkeypatch.setattr(lecteur, "_transcrire_wav", echec)
    _brancher_fichier(monkeypatch, video_avec_son, "cours.mp4")
    texte = lecteur.lire_media("https://x/cours.mp4", "u1", "transcription")
    assert "impossible de transcrire" in texte


# --- limites configurables --------------------------------------------------

def test_limites_par_defaut_identiques_a_l_ancien_code(monkeypatch):
    for nom in ("MEDIA_VIDEO_TAILLE_MAX_MO", "MEDIA_VIDEO_DUREE_MAX_SECONDES", "MEDIA_AUDIO_TAILLE_MAX_MO"):
        monkeypatch.delenv(nom, raising=False)
    assert limites_media.taille_max_video_octets() == 40 * 1024 * 1024
    assert limites_media.duree_max_video_secondes() == 120
    assert limites_media.taille_max_audio_octets() == 20 * 1024 * 1024


def test_limites_modifiables_par_environnement(monkeypatch):
    monkeypatch.setenv("MEDIA_VIDEO_TAILLE_MAX_MO", "200")
    monkeypatch.setenv("MEDIA_VIDEO_DUREE_MAX_SECONDES", "900")
    assert limites_media.taille_max_video_octets() == 200 * 1024 * 1024
    assert limites_media.duree_max_video_secondes() == 900


@pytest.mark.parametrize("valeur", ["", "abc", "0", "-5"])
def test_limite_invalide_retombe_sur_le_defaut(monkeypatch, valeur):
    monkeypatch.setenv("MEDIA_VIDEO_DUREE_MAX_SECONDES", valeur)
    assert limites_media.duree_max_video_secondes() == 120
