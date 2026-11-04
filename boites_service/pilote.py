"""
Pilote du navigateur, exécuté DANS la boîte navigateur (jamais sur le serveur ni dans le backend).

Deux rôles dans un seul fichier :
- démon (--demon) : garde un Chromium ouvert pour que la page reste la même d'une action à l'autre ;
- client (action et JSON en arguments) : démarre le démon si besoin, lui envoie l'action et
  affiche UNE ligne de JSON. C'est ce que le service lance avec « docker exec ».

Chromium ne sort que par le proxy à liste blanche du service (variables HTTPS_PROXY). Le bac à sable
interne de Chromium est coupé (--no-sandbox) parce que la boîte n'a aucune capacité Linux : c'est la
boîte elle-même qui isole, pas Chromium.

Tout ce que la page affiche est une donnée non fiable, jamais une instruction.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

HOTE = "127.0.0.1"
PORT = int(os.environ.get("PILOTE_PORT", "9333"))
DOSSIER_CAPTURES = os.environ.get("PILOTE_CAPTURES", "/home/user/captures")
CAPTURES_GARDEES = 5
TEXTE_MAX = int(os.environ.get("PILOTE_TEXTE_MAX", "2500"))
INACTIVITE_MAX = int(os.environ.get("PILOTE_INACTIVITE", "900"))
DELAI_NAVIGATION_MS = 20000
DELAI_ACTION_MS = 10000
SCHEMAS_AUTORISES = ("http", "https")


class ErreurPilote(Exception):
    pass


def url_valide(url: str) -> str:
    adresse = (url or "").strip()
    morceaux = urlparse(adresse)
    if morceaux.scheme.lower() not in SCHEMAS_AUTORISES or not morceaux.hostname:
        raise ErreurPilote("adresse refusée : seules les adresses http et https sont ouvertes")
    return adresse


def _court(erreur: Exception) -> str:
    texte = (str(erreur).strip().splitlines() or [type(erreur).__name__])[0]
    return texte[:300]


class Navigateur:
    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        options = {"headless": True, "args": ["--no-sandbox", "--disable-gpu", "--disable-extensions"]}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            options["proxy"] = {"server": proxy}
        self._navigateur = self._pw.chromium.launch(**options)
        self._contexte = self._navigateur.new_context(
            viewport={"width": 1280, "height": 800}, accept_downloads=False, service_workers="block",
        )
        self._contexte.set_default_timeout(DELAI_ACTION_MS)
        self._contexte.set_default_navigation_timeout(DELAI_NAVIGATION_MS)
        self._contexte.new_page()
        self._numero = 0

    def page(self):
        # Un clic peut ouvrir un nouvel onglet : on suit toujours le plus récent.
        return self._contexte.pages[-1]

    def _viser(self, page, p: dict):
        """Localisateur ou position visés par une action (sélecteur, texte visible, ou x et y)."""
        if p.get("selecteur"):
            return page.locator(str(p["selecteur"])).first
        if p.get("texte"):
            return page.get_by_text(str(p["texte"]), exact=False).first
        return None

    def _cliquer(self, page, p: dict):
        cible = self._viser(page, p)
        if cible is not None:
            cible.click()
        elif p.get("x") is not None and p.get("y") is not None:
            page.mouse.click(float(p["x"]), float(p["y"]))
        else:
            raise ErreurPilote("indique un selecteur, un texte visible, ou les positions x et y")

    def agir(self, action: str, p: dict) -> None:
        page = self.page()
        if action == "ouvrir":
            page.goto(url_valide(p.get("url", "")), wait_until="domcontentloaded")
        elif action == "cliquer":
            self._cliquer(page, p)
        elif action == "saisir":
            valeur = str(p.get("valeur", ""))
            cible = self._viser(page, p)
            if cible is not None:
                cible.fill(valeur)
            else:
                page.keyboard.type(valeur)
        elif action == "soumettre":
            if p.get("touche"):
                page.keyboard.press(str(p["touche"]))
            else:
                self._cliquer(page, p)
        elif action != "capture":
            raise ErreurPilote("action inconnue")
        try:
            self.page().wait_for_load_state("load", timeout=5000)
        except Exception:
            pass

    def etat(self) -> dict:
        page = self.page()
        self._numero += 1
        os.makedirs(DOSSIER_CAPTURES, exist_ok=True)
        chemin = os.path.join(DOSSIER_CAPTURES, f"capture-{self._numero}.jpg")
        page.screenshot(path=chemin, type="jpeg", quality=60)
        for ancien in range(1, self._numero - CAPTURES_GARDEES + 1):
            try:
                os.remove(os.path.join(DOSSIER_CAPTURES, f"capture-{ancien}.jpg"))
            except OSError:
                pass
        try:
            texte = page.inner_text("body", timeout=3000)
        except Exception:
            texte = ""
        return {
            "ok": True, "url": page.url, "titre": page.title()[:200],
            "texte": " ".join(texte.split())[:TEXTE_MAX], "capture": chemin,
        }

    def fermer(self) -> None:
        try:
            self._navigateur.close()
            self._pw.stop()
        except Exception:
            pass


def traiter(navigateur: Navigateur, demande: dict) -> dict:
    action = str(demande.get("action", ""))
    try:
        navigateur.agir(action, demande)
        return navigateur.etat()
    except Exception as e:
        # La page reste exploitable : le modèle voit l'erreur et la page telle qu'elle est.
        reponse = {"ok": False, "erreur": _court(e)}
        try:
            reponse.update({k: v for k, v in navigateur.etat().items() if k != "ok"})
        except Exception:
            pass
        return reponse


def demon() -> None:
    navigateur = Navigateur()
    dernier = {"t": time.monotonic(), "fin": False}

    class Gestionnaire(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_POST(self):
            dernier["t"] = time.monotonic()
            try:
                taille = int(self.headers.get("Content-Length", "0"))
                demande = json.loads(self.rfile.read(taille) or b"{}")
            except Exception:
                demande = {}
            if demande.get("action") == "fermer":
                dernier["fin"] = True
                reponse = {"ok": True, "ferme": True}
            else:
                reponse = traiter(navigateur, demande)
            corps = json.dumps(reponse, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            self.send_response(200)
            self.end_headers()

    serveur = HTTPServer((HOTE, PORT), Gestionnaire)
    serveur.timeout = 5
    try:
        while not dernier["fin"] and time.monotonic() - dernier["t"] < INACTIVITE_MAX:
            serveur.handle_request()
    finally:
        serveur.server_close()
        navigateur.fermer()


def _demon_vivant() -> bool:
    try:
        with socket.create_connection((HOTE, PORT), timeout=1):
            return True
    except OSError:
        return False


def _demarrer_demon() -> None:
    journal = open("/tmp/pilote.log", "ab")
    # Détaché et sans tube hérité : « docker exec » ne doit pas attendre la fin du démon.
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--demon"],
        stdin=subprocess.DEVNULL, stdout=journal, stderr=journal, start_new_session=True,
    )
    fin = time.monotonic() + 40
    while time.monotonic() < fin:
        if _demon_vivant():
            return
        time.sleep(0.3)
    raise ErreurPilote("le navigateur n'a pas démarré à temps")


def client(action: str, parametres: dict) -> dict:
    if action == "fermer" and not _demon_vivant():
        return {"ok": True, "ferme": True}
    if not _demon_vivant():
        _demarrer_demon()
    corps = json.dumps({**parametres, "action": action}).encode()
    requete = urllib.request.Request(f"http://{HOTE}:{PORT}/", data=corps, method="POST")
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        return json.loads(reponse.read())


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--demon":
        demon()
        return 0
    try:
        action = sys.argv[1]
        parametres = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        resultat = client(action, parametres)
    except Exception as e:
        resultat = {"ok": False, "erreur": _court(e)}
    print(json.dumps(resultat, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
