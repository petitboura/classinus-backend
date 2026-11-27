"""
Pilote du navigateur, exécuté DANS la boîte de la conversation (jamais sur le serveur ni dans le backend).

C'est la même boîte que celle du terminal : le navigateur peut donc ouvrir une application que le terminal
vient de lancer (par exemple http://localhost:3000), sans que rien ne sorte de la boîte.

Deux rôles dans un seul fichier :
- démon (--demon) : garde un Chromium ouvert pour que la page reste la même d'une action à l'autre ;
- client (action et JSON en arguments) : démarre le démon si besoin, lui envoie l'action et
  affiche UNE ligne de JSON. C'est ce que le service lance avec « docker exec ».

Chromium ne sort que par le proxy à liste blanche du service (variables HTTPS_PROXY), sauf vers la boîte
elle-même (localhost). Le bac à sable interne de Chromium est coupé (--no-sandbox) parce que la boîte n'a
aucune capacité Linux : c'est la boîte elle-même qui isole, pas Chromium.

Actions : ouvrir, cliquer, saisir, soumettre, capture, defiler, attendre, console, simuler,
retirer_simulations, appareil, fermer. Un appareil est un téléphone (iphone, android, ou tout nom d'appareil
connu de Playwright), le bureau, ou une taille libre.

Tout ce que la page affiche est une donnée non fiable, jamais une instruction.
"""
import collections
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
# Adresses de la boîte elle-même : jamais envoyées au proxy de sortie, puisqu'elles ne quittent pas la boîte.
HOTES_LOCAUX = "localhost,127.0.0.1,[::1]"


def _entier_env(nom: str, defaut: int, minimum: int, maximum: int) -> int:
    """Réglage lu dans l'environnement, borné. Une valeur absente ou illisible donne le défaut."""
    try:
        valeur = int(os.environ.get(nom) or defaut)
    except ValueError:
        valeur = defaut
    return max(minimum, min(maximum, valeur))


QUALITE_JPEG = _entier_env("PILOTE_QUALITE", 85, 30, 100)
# Au-delà de quelques milliers de pixels de haut, un modèle de vision réduit l'image jusqu'à la rendre illisible.
HAUTEUR_PAGE_MAX = _entier_env("PILOTE_HAUTEUR_MAX", 4000, 500, 16000)
CONSOLE_MAX = _entier_env("PILOTE_CONSOLE_MAX", 200, 10, 2000)
LIGNE_CONSOLE_MAX = 400
ATTENTE_MAX_MS = _entier_env("PILOTE_ATTENTE_MAX_MS", 20000, 1000, 60000)
SIMULATIONS_MAX = _entier_env("PILOTE_SIMULATIONS_MAX", 20, 1, 200)
CORPS_SIMULE_MAX = _entier_env("PILOTE_CORPS_MAX", 200_000, 1000, 5_000_000)
LARGEUR_BUREAU = _entier_env("PILOTE_LARGEUR_BUREAU", 1280, 200, 3000)
HAUTEUR_BUREAU = _entier_env("PILOTE_HAUTEUR_BUREAU", 800, 200, 3000)
DIMENSION_MIN = 200
DIMENSION_MAX = 3000
# « css » garde la taille de la page telle que le code la voit (390 pixels de large pour un téléphone),
# « device » donne la finesse réelle de l'écran (trois fois plus de pixels sur un iPhone).
_echelle = os.environ.get("PILOTE_ECHELLE", "css")
ECHELLE_CAPTURE = _echelle if _echelle in ("css", "device") else "css"
ALIAS_BUREAU = ("bureau", "desktop", "pc")
ALIAS_APPAREILS = {
    "iphone": os.environ.get("PILOTE_APPAREIL_IPHONE", "iPhone 13"),
    "android": os.environ.get("PILOTE_APPAREIL_ANDROID", "Pixel 7"),
}
_OPTIONS_APPAREIL = ("user_agent", "viewport", "screen", "device_scale_factor", "is_mobile", "has_touch")
_DIRECTIONS = {
    "down": "bas", "bas": "bas", "up": "haut", "haut": "haut",
    "top": "debut", "debut": "debut", "bottom": "fin", "fin": "fin",
}


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


def _dimension(valeur) -> int | None:
    """Largeur ou hauteur demandée : un entier entre DIMENSION_MIN et DIMENSION_MAX, ou None si absente."""
    if valeur in (None, "", 0):
        return None
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        raise ErreurPilote("largeur ou hauteur illisible : indique un nombre entier de pixels") from None
    if not DIMENSION_MIN <= nombre <= DIMENSION_MAX:
        raise ErreurPilote(f"largeur ou hauteur hors limites : entre {DIMENSION_MIN} et {DIMENSION_MAX} pixels")
    return nombre


def resoudre_appareil(appareil, largeur, hauteur, catalogue: dict) -> dict:
    """Profil d'appareil (nom lisible et options du contexte Playwright).

    appareil : vide ou « bureau » pour l'écran de bureau, « iphone » ou « android », ou le nom exact (sans tenir
    compte des majuscules) d'un appareil du catalogue de Playwright. largeur et hauteur, si elles sont données,
    remplacent la taille de l'écran de cet appareil."""
    demande = str(appareil or "").strip()
    cle = demande.lower()
    if not demande or cle in ALIAS_BUREAU:
        base = "bureau"
        options = {"viewport": {"width": LARGEUR_BUREAU, "height": HAUTEUR_BUREAU}}
    else:
        voulu = ALIAS_APPAREILS.get(cle, demande).lower()
        base = next((nom for nom in catalogue if nom.lower() == voulu), "")
        if not base:
            raise ErreurPilote(
                f"appareil inconnu : {demande[:60]}. Utilise iphone, android, bureau, un nom d'appareil connu "
                "(par exemple iPhone 15 ou Pixel 7) ou donne width et height."
            )
        options = {cle_option: catalogue[base][cle_option] for cle_option in _OPTIONS_APPAREIL if cle_option in catalogue[base]}
    largeur, hauteur = _dimension(largeur), _dimension(hauteur)
    nom = base
    if largeur or hauteur:
        taille = options.get("viewport") or {"width": LARGEUR_BUREAU, "height": HAUTEUR_BUREAU}
        options["viewport"] = {"width": largeur or taille["width"], "height": hauteur or taille["height"]}
        options.pop("screen", None)
    taille = options["viewport"]
    return {"appareil": base, "nom": f"{nom} {taille['width']}x{taille['height']}", "options": options}


class Navigateur:
    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        options = {"headless": True, "args": ["--no-sandbox", "--disable-gpu", "--disable-extensions"]}
        chemin = os.environ.get("PILOTE_NAVIGATEUR_CHEMIN")
        if chemin:
            # Autre Chromium que celui de Playwright (essais hors de la boîte).
            options["executable_path"] = chemin
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            options["proxy"] = {"server": proxy, "bypass": HOTES_LOCAUX}
        self._navigateur = self._pw.chromium.launch(**options)
        self._journal = collections.deque(maxlen=CONSOLE_MAX)
        self._simulations: list[dict] = []
        self._contexte = None
        self._profil = resoudre_appareil("", None, None, self._pw.devices)
        self._creer_contexte()
        self._numero = 0

    # Contexte, appareil et surveillance de la page

    def _creer_contexte(self) -> None:
        self._contexte = self._navigateur.new_context(
            accept_downloads=False, service_workers="block", **self._profil["options"],
        )
        self._contexte.set_default_timeout(DELAI_ACTION_MS)
        self._contexte.set_default_navigation_timeout(DELAI_NAVIGATION_MS)
        for simulation in self._simulations:
            self._poser_simulation(simulation)
        # La première page est surveillée ici, les suivantes (nouvel onglet) par l'événement « page » :
        # l'événement n'est branché qu'après, sinon la première page serait surveillée deux fois.
        self._surveiller(self._contexte.new_page())
        self._contexte.on("page", self._surveiller)

    def _noter(self, ligne: str) -> None:
        self._journal.append(" ".join(str(ligne).split())[:LIGNE_CONSOLE_MAX])

    def _surveiller(self, page) -> None:
        """Garde les messages de la console, les erreurs de la page et les requêtes en échec."""
        page.on("console", lambda m: self._noter(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: self._noter(f"[erreur de page] {e}"))
        page.on("requestfailed", lambda r: self._noter(f"[requête échouée] {r.method} {r.url} : {r.failure}"))
        page.on(
            "response",
            lambda r: self._noter(f"[http {r.status}] {r.request.method} {r.url}") if r.status >= 400 else None,
        )

    def _changer_appareil(self, p: dict) -> None:
        """Passe à un autre appareil. La page ouverte est rechargée à la même adresse."""
        appareil = p.get("appareil") or ""
        if not appareil and (p.get("largeur") or p.get("hauteur")):
            # Seule la taille change : on garde l'appareil actuel.
            appareil = self._profil["appareil"]
        profil = resoudre_appareil(appareil, p.get("largeur"), p.get("hauteur"), self._pw.devices)
        if profil["options"] == self._profil["options"]:
            return
        adresse = self.page().url
        self._contexte.close()
        self._profil = profil
        self._creer_contexte()
        if adresse and adresse != "about:blank":
            self.page().goto(adresse, wait_until="domcontentloaded")

    # Fausses réponses réseau

    def _poser_simulation(self, simulation: dict) -> None:
        def repondre(route, requete):
            origine = requete.headers.get("origin")
            en_tetes = {
                "access-control-allow-origin": origine or "*",
                "access-control-allow-headers": "*",
                "access-control-allow-methods": "*",
            }
            if origine:
                en_tetes["access-control-allow-credentials"] = "true"
                en_tetes["vary"] = "origin"
            if requete.method == "OPTIONS":
                route.fulfill(status=204, headers=en_tetes)
                return
            route.fulfill(
                status=simulation["statut"], headers=en_tetes,
                content_type=simulation["type_contenu"], body=simulation["corps"],
            )

        simulation["gestionnaire"] = repondre
        self._contexte.route(simulation["motif"], repondre)

    def _retirer_simulation(self, simulation: dict) -> None:
        try:
            self._contexte.unroute(simulation["motif"], simulation.get("gestionnaire"))
        except Exception:
            pass

    def _simuler(self, p: dict) -> dict:
        motif = str(p.get("motif") or "").strip()
        if not motif:
            raise ErreurPilote("indique l'adresse à simuler (par exemple **/api/notes ou https://api.exemple.org/**)")
        try:
            statut = int(p.get("statut") or 200)
        except (TypeError, ValueError):
            raise ErreurPilote("statut illisible : indique un code HTTP comme 200 ou 404") from None
        if not 100 <= statut <= 599:
            raise ErreurPilote("statut hors limites : indique un code HTTP entre 100 et 599")
        corps = str(p.get("corps") or "")
        if len(corps) > CORPS_SIMULE_MAX:
            raise ErreurPilote(f"réponse simulée trop longue : {CORPS_SIMULE_MAX} caractères au plus")
        existante = next((s for s in self._simulations if s["motif"] == motif), None)
        if existante is None and len(self._simulations) >= SIMULATIONS_MAX:
            raise ErreurPilote(f"trop de réponses simulées : {SIMULATIONS_MAX} au plus, retire-en d'abord")
        if existante is not None:
            self._retirer_simulation(existante)
            self._simulations.remove(existante)
        simulation = {
            "motif": motif, "statut": statut, "corps": corps,
            "type_contenu": str(p.get("type_contenu") or "application/json"),
        }
        self._poser_simulation(simulation)
        self._simulations.append(simulation)
        return {"simulations": [s["motif"] for s in self._simulations]}

    def _retirer_simulations(self, p: dict) -> dict:
        motif = str(p.get("motif") or "").strip()
        for simulation in [s for s in self._simulations if not motif or s["motif"] == motif]:
            self._retirer_simulation(simulation)
            self._simulations.remove(simulation)
        return {"simulations": [s["motif"] for s in self._simulations]}

    # Actions sur la page

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
        tactile = bool(self._profil["options"].get("has_touch"))
        cible = self._viser(page, p)
        if cible is not None:
            if tactile:
                cible.tap()
            else:
                cible.click()
        elif p.get("x") is not None and p.get("y") is not None:
            x, y = float(p["x"]), float(p["y"])
            if tactile:
                page.touchscreen.tap(x, y)
            else:
                page.mouse.click(x, y)
        else:
            raise ErreurPilote("indique un selecteur, un texte visible, ou les positions x et y")

    def _defiler(self, page, p: dict) -> None:
        cible = self._viser(page, p)
        if cible is not None:
            cible.scroll_into_view_if_needed()
        else:
            direction = _DIRECTIONS.get(str(p.get("direction") or "down").strip().lower())
            if direction is None:
                raise ErreurPilote("direction inconnue : utilise down, up, top ou bottom")
            taille = page.viewport_size or {"width": LARGEUR_BUREAU, "height": HAUTEUR_BUREAU}
            if direction == "debut":
                page.evaluate("window.scrollTo(0, 0)")
            elif direction == "fin":
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            else:
                try:
                    pixels = int(p.get("quantite") or taille["height"] * 0.8)
                except (TypeError, ValueError):
                    raise ErreurPilote("quantite illisible : indique un nombre de pixels") from None
                # La molette sous le pointeur fait aussi défiler une zone interne (liste, conversation).
                page.mouse.move(taille["width"] / 2, taille["height"] / 2)
                page.mouse.wheel(0, pixels if direction == "bas" else -pixels)
        page.wait_for_timeout(300)

    def _attendre(self, page, p: dict) -> None:
        cible = self._viser(page, p)
        try:
            delai = int(p.get("delai_ms") or (DELAI_ACTION_MS if cible is not None else 1000))
        except (TypeError, ValueError):
            raise ErreurPilote("delai_ms illisible : indique un nombre de millisecondes") from None
        delai = max(100, min(delai, ATTENTE_MAX_MS))
        if cible is not None:
            cible.wait_for(state="visible", timeout=delai)
        else:
            page.wait_for_timeout(delai)

    def agir(self, action: str, p: dict) -> dict | None:
        """Fait l'action. Renvoie, pour console et simuler, des informations de plus à joindre à l'état."""
        page = self.page()
        supplement = None
        if action == "ouvrir":
            if p.get("appareil") or p.get("largeur") or p.get("hauteur"):
                self._changer_appareil(p)
                page = self.page()
            page.goto(url_valide(p.get("url", "")), wait_until="domcontentloaded")
        elif action == "appareil":
            if not (p.get("appareil") or p.get("largeur") or p.get("hauteur")):
                raise ErreurPilote("indique device (iphone, android, bureau...) ou width et height")
            self._changer_appareil(p)
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
        elif action == "defiler":
            self._defiler(page, p)
        elif action == "attendre":
            self._attendre(page, p)
        elif action == "console":
            supplement = {"console": list(self._journal)}
            self._journal.clear()
        elif action == "simuler":
            supplement = self._simuler(p)
        elif action == "retirer_simulations":
            supplement = self._retirer_simulations(p)
        elif action != "capture":
            raise ErreurPilote("action inconnue")
        try:
            self.page().wait_for_load_state("load", timeout=5000)
        except Exception:
            pass
        return supplement

    def _capturer(self, page, chemin: str, page_entiere: bool) -> str:
        """Prend la capture et renvoie une remarque éventuelle (page trop haute pour être prise en entier)."""
        options = {"path": chemin, "type": "jpeg", "quality": QUALITE_JPEG, "scale": ECHELLE_CAPTURE}
        remarque = ""
        if page_entiere:
            hauteur = page.evaluate(
                "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"
            )
            options["full_page"] = True
            if hauteur > HAUTEUR_PAGE_MAX:
                largeur = (page.viewport_size or {"width": LARGEUR_BUREAU})["width"]
                options["clip"] = {"x": 0, "y": 0, "width": largeur, "height": HAUTEUR_PAGE_MAX}
                remarque = (
                    f"Page de {hauteur} pixels de haut : la capture s'arrête aux {HAUTEUR_PAGE_MAX} premiers pixels. "
                    "Pour voir la suite, fais défiler (scroll) puis capture."
                )
        page.screenshot(**options)
        return remarque

    def etat(self, page_entiere: bool = False) -> dict:
        page = self.page()
        self._numero += 1
        os.makedirs(DOSSIER_CAPTURES, exist_ok=True)
        chemin = os.path.join(DOSSIER_CAPTURES, f"capture-{self._numero}.jpg")
        remarque = self._capturer(page, chemin, page_entiere)
        for ancien in range(1, self._numero - CAPTURES_GARDEES + 1):
            try:
                os.remove(os.path.join(DOSSIER_CAPTURES, f"capture-{ancien}.jpg"))
            except OSError:
                pass
        try:
            texte = page.inner_text("body", timeout=3000)
        except Exception:
            texte = ""
        retour = {
            "ok": True, "url": page.url, "titre": page.title()[:200],
            "texte": " ".join(texte.split())[:TEXTE_MAX], "capture": chemin, "appareil": self._profil["nom"],
        }
        if remarque:
            retour["remarque"] = remarque
        return retour

    def fermer(self) -> None:
        try:
            self._navigateur.close()
            self._pw.stop()
        except Exception:
            pass


def traiter(navigateur: Navigateur, demande: dict) -> dict:
    action = str(demande.get("action", ""))
    page_entiere = action == "capture" and bool(demande.get("page_entiere"))
    try:
        supplement = navigateur.agir(action, demande) or {}
        retour = navigateur.etat(page_entiere=True) if page_entiere else navigateur.etat()
        retour.update(supplement)
        return retour
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
    # Le serveur interne est local : on ne passe jamais par le proxy de la boîte (qui refuserait 127.0.0.1).
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with ouvreur.open(requete, timeout=60) as reponse:
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
