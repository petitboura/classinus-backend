"""
Rendu vidéo d'une animation guidée, exécuté dans un processus séparé
(07/10/2026, demande Bourama).

Pourquoi un processus à part : le code de l'animation est écrit par le
modèle (ou modifié par un utilisateur) et tourne dans un navigateur. En
l'isolant, un code qui boucle sans fin ou qui consomme toute la mémoire
est tué net par le superviseur (core/rendu_animation_travaux.py) sans
toucher à l'API, et le processus ne reçoit aucun secret de l'API.

Principe : le document HTML de l'animation (construit par le frontend, le
même que celui du lecteur, voir construireDocumentAnimation.ts) est chargé
dans un Chromium sans écran. Le lecteur sait dessiner l'animation à
n'importe quel instant t (window.__rendu.aller(t)) : on avance donc le temps
image par image, on capture chaque image, et ffmpeg les assemble en MP4.

Fichier autonome : uniquement la bibliothèque standard, playwright et
ffmpeg. Il est lancé par chemin de fichier, jamais importé, et tout lui est
passé en arguments.

Dialogue avec le superviseur, une ligne JSON par message sur la sortie
standard :
  {"p": 0.42}                  avancement, de 0 à 1
  {"erreur": "CODE"}           échec connu (code de core/erreurs.py)
  {"fin": true}                vidéo écrite

Code de sortie : 0 réussite, 1 échec, 4 navigateur indisponible.
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

CODE_SORTIE_INDISPONIBLE = 4

# Hôtes depuis lesquels le document charge three.js. La requête est servie
# par la copie locale, jamais envoyée sur le réseau.
HOTES_THREE = {"cdnjs.cloudflare.com", "cdn.jsdelivr.net"}

ARGUMENTS_CHROMIUM = [
    # /dev/shm est minuscule dans un conteneur : le navigateur crash sans cela.
    "--disable-dev-shm-usage",
    # WebGL logiciel pour les animations 3D (aucune carte graphique).
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    # Aucune mise en veille du moteur pendant les captures.
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]


def dire(message: dict) -> None:
    print(json.dumps(message), flush=True)


def echouer(code: str, sortie: int = 1) -> None:
    dire({"erreur": code})
    sys.exit(sortie)


def lire_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--document", required=True)
    p.add_argument("--sortie", required=True)
    p.add_argument("--largeur", type=int, required=True)
    p.add_argument("--hauteur", type=int, required=True)
    p.add_argument("--fps", type=int, required=True)
    p.add_argument("--duree-max", type=float, required=True)
    p.add_argument("--maintien-fin", type=float, required=True)
    p.add_argument("--delai-chargement", type=float, required=True)
    p.add_argument("--three", required=True)
    return p.parse_args()


def est_three(url: str) -> bool:
    adresse = urlparse(url)
    return adresse.hostname in HOTES_THREE and adresse.path.endswith("/three.min.js")


def diagnostic_memoire() -> str:
    """Photo de la mémoire du conteneur au moment d'un arrêt de ffmpeg.
    Sert à savoir si le système a tué ffmpeg faute de mémoire."""
    morceaux = []
    for nom, chemin in (
        ("utilisee", "/sys/fs/cgroup/memory.current"),
        ("limite", "/sys/fs/cgroup/memory.max"),
        ("evenements", "/sys/fs/cgroup/memory.events"),
    ):
        try:
            morceaux.append(f"{nom}={Path(chemin).read_text().strip().replace(chr(10), ' ')}")
        except OSError:
            morceaux.append(f"{nom}=indisponible")
    return " ".join(morceaux)


def lancer_ffmpeg(sortie: str, fps: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(fps), "-vcodec", "mjpeg", "-i", "pipe:0",
            "-c:v", "libx264", "-preset", "superfast", "-threads", "2", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", str(fps),
            sortie,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def main() -> None:
    a = lire_arguments()
    document = Path(a.document).read_text(encoding="utf-8")
    three = Path(a.three).read_bytes()

    try:
        from playwright.sync_api import Error as ErreurPlaywright
        from playwright.sync_api import sync_playwright
    except ImportError:
        echouer("RENDU_VIDEO_INDISPONIBLE", CODE_SORTIE_INDISPONIBLE)

    def filtrer(route):
        # Rien ne sort vers le réseau. Seule exception : three.js, servi
        # depuis la copie locale.
        if est_three(route.request.url):
            route.fulfill(status=200, body=three, content_type="application/javascript")
        else:
            route.abort()

    ffmpeg = None
    try:
        with sync_playwright() as pw:
            try:
                navigateur = pw.chromium.launch(
                    args=ARGUMENTS_CHROMIUM,
                    # Dernier verrou : tout ce qui échapperait au filtre
                    # ci dessus (WebSocket, boucle locale) part vers un
                    # relais qui n'existe pas.
                    proxy={"server": "http://127.0.0.1:9", "bypass": "<-loopback>"},
                )
            except ErreurPlaywright as e:
                print(f"navigateur indisponible : {e}", file=sys.stderr)
                echouer("RENDU_VIDEO_INDISPONIBLE", CODE_SORTIE_INDISPONIBLE)

            contexte = navigateur.new_context(
                viewport={"width": a.largeur, "height": a.hauteur},
                device_scale_factor=1,
                service_workers="block",
            )
            contexte.route("**/*", filtrer)
            page = contexte.new_page()
            page.route_web_socket("**/*", lambda ws: ws.close())
            page.set_content(document, wait_until="load")

            try:
                page.wait_for_function(
                    "window.__rendu && window.__rendu.etat() !== 'chargement'",
                    timeout=a.delai_chargement * 1000,
                )
            except ErreurPlaywright:
                echouer("RENDU_VIDEO_ANIMATION_EN_ERREUR")
            if page.evaluate("window.__rendu.etat()") != "pret":
                echouer("RENDU_VIDEO_ANIMATION_EN_ERREUR")

            duree = float(page.evaluate("window.__rendu.info().duree"))
            if not (duree > 0):
                echouer("RENDU_VIDEO_ANIMATION_EN_ERREUR")
            if duree > a.duree_max:
                echouer("RENDU_VIDEO_TROP_LONGUE")

            images = int(math.ceil(duree * a.fps)) + 1
            images_fin = int(round(a.maintien_fin * a.fps))
            total = images + images_fin
            ffmpeg = lancer_ffmpeg(a.sortie, a.fps)

            derniere = b""
            for i in range(images):
                t = min(i / a.fps, duree)
                if page.evaluate("t => window.__rendu.aller(t)", t):
                    echouer("RENDU_VIDEO_ANIMATION_EN_ERREUR")
                derniere = page.screenshot(type="jpeg", quality=92)
                ffmpeg.stdin.write(derniere)
                if i % 15 == 0:
                    dire({"p": round(0.97 * i / total, 3)})
            for _ in range(images_fin):
                ffmpeg.stdin.write(derniere)

            navigateur.close()

        ffmpeg.stdin.close()
        erreurs_ffmpeg = ffmpeg.stderr.read().decode("utf-8", "replace")
        if ffmpeg.wait() != 0:
            print(f"ffmpeg : {erreurs_ffmpeg}", file=sys.stderr)
            echouer("RENDU_VIDEO_ECHEC")
    except BrokenPipeError:
        erreurs_ffmpeg = ffmpeg.stderr.read().decode("utf-8", "replace") if ffmpeg else ""
        try:
            code_ffmpeg = ffmpeg.wait(timeout=5) if ffmpeg else None
        except subprocess.TimeoutExpired:
            code_ffmpeg = "toujours en cours"
        # Un code négatif signifie que ffmpeg a été tué par un signal (-9 : tué par le système)
        print(
            f"ffmpeg a fermé son entrée : code de sortie {code_ffmpeg}, {diagnostic_memoire()}, {erreurs_ffmpeg}",
            file=sys.stderr,
        )
        echouer("RENDU_VIDEO_ECHEC")
    except Exception as e:
        print(f"échec du rendu : {type(e).__name__} : {e}", file=sys.stderr)
        echouer("RENDU_VIDEO_ECHEC")

    dire({"fin": True})


if __name__ == "__main__":
    main()
