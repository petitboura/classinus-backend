"""
Lecture à la demande d'une vidéo ou d'un audio joint à une conversation
(26/10/2026, demande Bourama : contrairement aux images et aux documents, c'est
le MODÈLE qui décide de lire ou non une vidéo ou un audio).

Avant ce chantier, api/uploads.py transcrivait (Whisper) et extrayait 5 images
de chaque vidéo, ou transcrivait chaque audio, DÈS l'envoi, sans que le modèle ait
son mot à dire. Maintenant, l'envoi enregistre seulement le fichier et ses
informations peu coûteuses (durée, taille, résolution, présence de son). Ce
module fait le vrai travail, quand le modèle appelle l'outil
lire_media_conversation (core/outils_lecture_media.py) :

- mode "infos" : informations seules, aucun coût
- mode "transcription" : ce qui est dit, avec des repères [m:ss], par tranches
  (Whisper via Groq, même fournisseur que le reste du projet)
- mode "images" : quelques images décrites (ffmpeg + Gemini vision, mêmes
  briques que core/description_multimedia.py)
- mode "les_deux" : transcription puis images

Le modèle peut cibler un passage (debut_secondes / fin_secondes) : une vidéo ou un
audio long est donc lu par morceaux, jamais d'un bloc.

Le retour est toujours un TEXTE destiné au modèle, jamais une exception : un
média illisible n'est pas une erreur de l'application, le modèle doit
simplement le dire à l'étudiant sans rien inventer.

Les limites (taille, durée, images) viennent de core/limites_media.py.
"""

import json
import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from core.limites_media import images_max_par_appel, tranche_transcription_secondes

MODES = ("infos", "transcription", "images", "les_deux")
NB_IMAGES_PAR_DEFAUT = 5


def formater_duree(secondes: float) -> str:
    """92 -> '1:32', 3723 -> '1:02:03'."""
    total = max(0, int(round(secondes)))
    heures, reste = divmod(total, 3600)
    minutes, secs = divmod(reste, 60)
    if heures:
        return f"{heures}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def formater_taille(octets: int) -> str:
    """Taille lisible en français : '12,4 Mo', '830 Ko'."""
    if octets >= 1024 * 1024:
        return f"{octets / (1024 * 1024):.1f} Mo".replace(".", ",")
    return f"{max(1, round(octets / 1024))} Ko"


def lire_infos(chemin: str, taille_octets: int | None = None) -> dict:
    """
    Informations d'un fichier audio ou vidéo via ffprobe : duree_secondes,
    a_audio, a_video, largeur, hauteur, fps, taille_octets. Lève une exception
    si ffprobe ne peut pas lire le fichier (à l'appelant d'en tirer le message).
    """
    resultat = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", chemin,
        ],
        capture_output=True, text=True, timeout=20, check=True,
    )
    donnees = json.loads(resultat.stdout or "{}")
    flux = donnees.get("streams") or []
    format_ = donnees.get("format") or {}
    video = next((f for f in flux if f.get("codec_type") == "video" and f.get("disposition", {}).get("attached_pic") != 1), None)
    audio = next((f for f in flux if f.get("codec_type") == "audio"), None)

    duree = format_.get("duration")
    if duree is None:
        duree = (video or audio or {}).get("duration")
    duree = float(duree) if duree is not None else 0.0

    fps = None
    if video and video.get("avg_frame_rate") and video["avg_frame_rate"] != "0/0":
        try:
            num, den = video["avg_frame_rate"].split("/")
            fps = round(float(num) / float(den), 1) if float(den) else None
        except (ValueError, ZeroDivisionError):
            fps = None

    if taille_octets is None:
        try:
            taille_octets = int(format_.get("size") or os.path.getsize(chemin))
        except (ValueError, OSError):
            taille_octets = 0

    return {
        "duree_secondes": duree,
        "a_audio": audio is not None,
        "a_video": video is not None,
        "largeur": int(video["width"]) if video and video.get("width") else None,
        "hauteur": int(video["height"]) if video and video.get("height") else None,
        "fps": fps,
        "taille_octets": taille_octets,
    }


def resume_infos(infos: dict) -> str:
    """Résumé court des informations, le même texte pour le message et l'outil."""
    morceaux = [formater_duree(infos["duree_secondes"]), formater_taille(infos["taille_octets"])]
    if infos.get("a_video") and infos.get("largeur") and infos.get("hauteur"):
        morceaux.append(f"{infos['largeur']}x{infos['hauteur']}")
        if infos.get("fps"):
            morceaux.append(f"{infos['fps']:g} images/s".replace(".", ","))
    if infos.get("a_video"):
        morceaux.append("avec son" if infos.get("a_audio") else "sans piste audio")
    return ", ".join(morceaux)


def _extraire_audio_tranche(chemin_media: str, debut: float, duree: float, chemin_sortie: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(debut), "-t", str(duree), "-i", chemin_media,
            "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", chemin_sortie,
        ],
        capture_output=True, timeout=120, check=True,
    )


def _transcrire_wav(contenu_wav: bytes, langue: str | None) -> tuple[list[dict], str | None]:
    """
    Whisper (Groq) en verbose_json. `langue` vide = détection automatique (la
    langue détectée est renvoyée). Reprend le filtre des hallucinations Whisper
    connues sur un audio silencieux (core/description_multimedia.py).
    """
    from groq import Groq
    from core.description_multimedia import PHRASES_HALLUCINEES_WHISPER, _get_secret

    client = Groq(api_key=_get_secret("GROQ_API_KEY"))
    parametres = dict(
        file=("audio.wav", contenu_wav),
        model="whisper-large-v3",
        response_format="verbose_json",
    )
    if langue:
        parametres["language"] = langue
    transcription = client.audio.transcriptions.create(**parametres)

    segments = []
    for segment in getattr(transcription, "segments", None) or []:
        texte = ((segment.get("text") if isinstance(segment, dict) else segment.text) or "").strip()
        if not texte or texte.lower().rstrip(".") in PHRASES_HALLUCINEES_WHISPER:
            continue
        debut = segment.get("start") if isinstance(segment, dict) else segment.start
        segments.append({"text": texte, "start": float(debut or 0)})
    langue_detectee = getattr(transcription, "language", None)
    return segments, langue_detectee


def _bloc_transcription(chemin_media: str, infos: dict, debut: float, fin: float, langue: str | None) -> str:
    if not infos["a_audio"]:
        return "Transcription : ce fichier n'a pas de piste audio."

    tranche = tranche_transcription_secondes()
    fin_tranche = min(fin, debut + tranche)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_wav:
        chemin_wav = f_wav.name
    try:
        _extraire_audio_tranche(chemin_media, debut, fin_tranche - debut, chemin_wav)
        with open(chemin_wav, "rb") as f:
            segments, langue_detectee = _transcrire_wav(f.read(), langue)
    except Exception as e:
        logging.error(f"ERREUR transcription lire_media_conversation : {e}")
        return "Transcription : impossible de transcrire ce passage, réessaie."
    finally:
        if os.path.exists(chemin_wav):
            os.remove(chemin_wav)

    entete = f"Transcription de {formater_duree(debut)} à {formater_duree(fin_tranche)}"
    if langue_detectee:
        entete += f" (langue détectée : {langue_detectee})"
    if not segments:
        return f"{entete} : aucune parole exploitable sur ce passage."

    lignes = [f"[{formater_duree(s['start'] + debut)}] {s['text']}" for s in segments]
    texte = f"{entete} :\n" + "\n".join(lignes)
    if fin_tranche < fin:
        texte += (
            f"\n\nCette tranche s'arrête à {formater_duree(fin_tranche)} sur {formater_duree(fin)} : "
            f"pour lire la suite, rappelle lire_media_conversation avec debut_secondes={int(fin_tranche)}."
        )
    return texte


def _instants_images(debut: float, fin: float, nombre: int) -> list[float]:
    """Instants répartis sur [debut, fin], jamais la toute première ni la dernière milliseconde."""
    if nombre <= 1:
        return [debut if fin <= debut else (debut + fin) / 2]
    return [debut + (fin - debut) * (i + 1) / (nombre + 1) for i in range(nombre)]


def _extraire_image(chemin_video: str, instant: float, dossier: str, indice: int) -> bytes | None:
    chemin_image = os.path.join(dossier, f"image_{indice}.jpg")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(instant), "-i", chemin_video,
                "-frames:v", "1", "-vf", "scale=768:-1", chemin_image,
            ],
            capture_output=True, timeout=30, check=True,
        )
    except Exception as e:
        logging.error(f"ERREUR extraction image lire_media_conversation (t={instant:.1f}s) : {e}")
        return None
    if not os.path.exists(chemin_image):
        return None
    with open(chemin_image, "rb") as f:
        return f.read()


def _bloc_images(chemin_video: str, infos: dict, debut: float, fin: float, nombre: int) -> str:
    if not infos["a_video"]:
        return "Images : ce fichier n'a pas de partie vidéo (audio seul)."

    from core.description_multimedia import decrire_image_bibliotheque

    instants = _instants_images(debut, fin, nombre)
    with tempfile.TemporaryDirectory() as dossier:
        images = [(t, _extraire_image(chemin_video, t, dossier, i)) for i, t in enumerate(instants)]
        images = [(t, contenu) for t, contenu in images if contenu]
        if not images:
            return "Images : aucune image n'a pu être extraite de ce passage."
        with ThreadPoolExecutor(max_workers=min(4, len(images))) as pool:
            descriptions = list(pool.map(lambda x: decrire_image_bibliotheque(x[1], "image/jpeg"), images))

    lignes = [f"[{formater_duree(t)}] {d}" for (t, _), d in zip(images, descriptions) if d]
    if not lignes:
        return "Images : la description des images a échoué, réessaie."
    return f"Images décrites de {formater_duree(debut)} à {formater_duree(fin)} :\n" + "\n".join(lignes)


MARQUEURS_MEDIA_JOINT = ("[Vidéo jointe : ", "[Audio joint : ")


def media_joint_present(message_utilisateur, historique) -> bool:
    """
    True si le message courant ou un message de l'UTILISATEUR de l'historique
    contient une vidéo ou un audio joint (marqueurs écrits par le frontend,
    lib/preparerPiecesJointes.ts). Sert à main.py pour donner l'outil
    lire_media_conversation au modèle : sans cela, rien ne garantit qu'il soit
    proposé ce tour-ci, alors que le message lui dit que le contenu n'est pas lu.
    """
    textes = [message_utilisateur or ""]
    for m in historique or []:
        if isinstance(m, dict) and m.get("role") == "user":
            textes.append(m.get("content") or "")
    return any(marqueur in texte for texte in textes for marqueur in MARQUEURS_MEDIA_JOINT)


def retrouver_fichier(url_fichier: str, user_id: str) -> tuple[dict, bytes] | None:
    """
    Retrouve un fichier de CONVERSATION de cet utilisateur par son lien réel et
    relit ses octets. Scope strict sur user_id et sur l'origine "chat" : un lien
    inventé ou appartenant à un autre compte ne renvoie rien (même règle que
    core/bibliotheque_fichiers.py:renommer_fichier_par_url).
    """
    from core import stockage_r2
    from core.bibliotheque_fichiers import BUCKET, supabase

    res = (
        supabase.table("fichiers_uploades")
        .select("chemin_stockage,nom_fichier,type_mime,taille_octets")
        .eq("url_publique", url_fichier)
        .eq("user_id", user_id)
        .eq("origine", "chat")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    ligne = res.data[0]
    return ligne, stockage_r2.from_(BUCKET).download(ligne["chemin_stockage"])


def lire_media(
    url_fichier: str,
    user_id: str,
    mode: str = "infos",
    debut_secondes: float = 0,
    fin_secondes: float | None = None,
    nb_images: int = NB_IMAGES_PAR_DEFAUT,
    langue: str = "",
) -> str:
    """Point d'entrée de l'outil lire_media_conversation. Renvoie toujours un texte."""
    mode = (mode or "infos").strip().lower()
    if mode not in MODES:
        return f"Erreur : mode inconnu. Modes valides : {', '.join(MODES)}."
    url_fichier = (url_fichier or "").strip()
    if not url_fichier:
        return "Erreur : url_fichier manquant (le lien réel indiqué juste après le fichier joint)."

    trouve = retrouver_fichier(url_fichier, user_id)
    if trouve is None:
        return "Erreur : ce fichier est introuvable, ou ne t'appartient pas."
    ligne, contenu = trouve

    extension = (ligne.get("nom_fichier") or "").rsplit(".", 1)[-1].lower() if "." in (ligne.get("nom_fichier") or "") else "bin"
    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as f_media:
        f_media.write(contenu)
        chemin_media = f_media.name
    try:
        try:
            infos = lire_infos(chemin_media, len(contenu))
        except Exception as e:
            logging.error(f"ERREUR ffprobe lire_media_conversation : {e}")
            return "Erreur : ce fichier n'est pas un audio ou une vidéo lisible."

        duree = infos["duree_secondes"]
        debut = min(max(float(debut_secondes or 0), 0.0), duree)
        fin = duree if fin_secondes in (None, 0) else min(max(float(fin_secondes), debut), duree)

        parties = [f"{ligne.get('nom_fichier')} : {resume_infos(infos)}."]
        if mode in ("transcription", "les_deux"):
            parties.append(_bloc_transcription(chemin_media, infos, debut, fin, (langue or "").strip() or None))
        if mode in ("images", "les_deux"):
            nombre = max(1, min(int(nb_images or NB_IMAGES_PAR_DEFAUT), images_max_par_appel()))
            parties.append(_bloc_images(chemin_media, infos, debut, fin, nombre))
        return "\n\n".join(parties)
    finally:
        if os.path.exists(chemin_media):
            os.remove(chemin_media)
