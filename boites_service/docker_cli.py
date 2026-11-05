"""
Accès à Docker par la ligne de commande, rien d'autre. Un seul fichier sait lancer docker,
ce qui permet de le remplacer par un faux dans les tests.
"""
import os
import posixpath
import re
import subprocess
import time

_ID = re.compile(r"^[a-f0-9]{16,32}$")
_RACINES_AUTORISEES = ("/home/user", "/tmp")


class ErreurDocker(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def id_valide(boite_id: str) -> str:
    if not _ID.fullmatch(boite_id or ""):
        raise ErreurDocker("identifiant de boîte invalide", 400)
    return boite_id


def chemin_sur(chemin: str) -> str:
    """Refuse tout chemin hors du dossier de travail et de /tmp, y compris avec « .. »."""
    normalise = posixpath.normpath(str(chemin or ""))
    if not normalise.startswith("/") or "\x00" in normalise:
        raise ErreurDocker("chemin invalide", 400)
    for racine in _RACINES_AUTORISEES:
        if normalise == racine or normalise.startswith(racine + "/"):
            return normalise
    raise ErreurDocker("chemin hors du dossier de travail", 400)


def _entier(nom: str, defaut: int) -> int:
    try:
        return int(os.environ.get(nom, defaut))
    except ValueError:
        return defaut


class Docker:
    """Limites lues dans l'environnement du service, jamais envoyées par le backend."""

    def __init__(self):
        self.image = os.environ.get("BOITES_IMAGE", "classinus-boite:latest")
        self.reseau = os.environ.get("BOITES_RESEAU", "boites_internes")
        self.memoire = os.environ.get("BOITES_MEMOIRE", "512m")
        self.cpus = os.environ.get("BOITES_CPUS", "1")
        self.pids = str(_entier("BOITES_PIDS", 256))
        self.disque = os.environ.get("BOITES_DISQUE", "256m")
        self.hote_proxy = os.environ.get("BOITES_HOTE_PROXY", "boites-service")
        self.port_proxy = _entier("BOITES_PORT_PROXY", 3128)
        self.sortie_max = _entier("BOITES_SORTIE_MAX", 2_000_000)
        self.lecture_max = _entier("BOITES_LECTURE_MAX", 50_000_000)
        # Boîtes navigateur (étape 6) : Chromium demande plus de mémoire, de processus et de mémoire partagée.
        self.image_nav = os.environ.get("BOITES_IMAGE_NAV", "classinus-navigateur:latest")
        self.memoire_nav = os.environ.get("BOITES_NAV_MEMOIRE", "1536m")
        self.cpus_nav = os.environ.get("BOITES_NAV_CPUS", "1")
        self.pids_nav = str(_entier("BOITES_NAV_PIDS", 512))
        self.disque_nav = os.environ.get("BOITES_NAV_DISQUE", "512m")

    @staticmethod
    def _docker(args: list[str], entree: bytes | None = None, delai: float = 30):
        try:
            return subprocess.run(
                ["docker", *args], input=entree, capture_output=True, timeout=delai, check=False
            )
        except subprocess.TimeoutExpired as e:
            raise ErreurDocker("délai dépassé", 504) from e
        except FileNotFoundError as e:
            raise ErreurDocker("docker est introuvable sur ce serveur", 503) from e

    @staticmethod
    def nom(boite_id: str) -> str:
        return f"boite-{id_valide(boite_id)}"

    def etat(self, boite_id: str) -> str | None:
        """running, exited, etc., ou None si la boîte n'existe pas."""
        r = self._docker(["inspect", "-f", "{{.State.Status}}", self.nom(boite_id)])
        return r.stdout.decode().strip() if r.returncode == 0 else None

    def adresse(self, boite_id: str) -> str | None:
        r = self._docker([
            "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", self.nom(boite_id),
        ])
        if r.returncode != 0:
            return None
        morceaux = r.stdout.decode().split()
        return morceaux[0] if morceaux else None

    def lister(self) -> list[str]:
        r = self._docker(["ps", "-a", "--filter", "label=classinus=boite", "--format", "{{.Names}}"])
        return [n.removeprefix("boite-") for n in r.stdout.decode().split() if n.startswith("boite-")]

    def creer(self, boite_id: str, navigateur: bool = False, utilisateur: str = "") -> None:
        nom = self.nom(boite_id)
        volume = f"volume-{nom}"
        disque = self.disque_nav if navigateur else self.disque
        r = self._docker([
            "volume", "create", "--driver", "local", "--opt", "type=tmpfs", "--opt", "device=tmpfs",
            "--opt", f"o=size={disque},uid=1000,gid=1000,mode=0755", "--label", "classinus=boite", volume,
        ])
        if r.returncode != 0:
            raise ErreurDocker("création du volume impossible", 503)
        proxy = f"http://{self.hote_proxy}:{self.port_proxy}"
        if navigateur:
            image, memoire, cpus, pids = self.image_nav, self.memoire_nav, self.cpus_nav, self.pids_nav
            # Chromium écrit beaucoup dans /tmp et /dev/shm : tailles à la mesure de la boîte, jamais illimitées.
            specifique = [
                "--shm-size", "512m", "--tmpfs", "/tmp:rw,size=512m",
                "--label", "classinus-profil=navigateur", "--label", f"classinus-cree={int(time.time())}",
                "--label", f"classinus-utilisateur={utilisateur or 'inconnu'}",
            ]
        else:
            image, memoire, cpus, pids = self.image, self.memoire, self.cpus, self.pids
            specifique = ["--tmpfs", "/tmp:rw,size=256m"]
        r = self._docker([
            "run", "-d", "--init", "--name", nom, "--label", "classinus=boite",
            "--network", self.reseau,
            "--memory", memoire, "--memory-swap", memoire, "--cpus", cpus,
            "--pids-limit", pids, "--ulimit", "nofile=1024:1024",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--read-only", *specifique,
            "--user", "1000:1000", "-v", f"{volume}:/home/user", "-w", "/home/user",
            "-e", f"HTTP_PROXY={proxy}", "-e", f"HTTPS_PROXY={proxy}",
            "-e", f"http_proxy={proxy}", "-e", f"https_proxy={proxy}",
            "-e", "NO_PROXY=", "-e", "HOME=/home/user",
            image,
        ], delai=60)
        if r.returncode != 0:
            self._docker(["volume", "rm", "-f", volume])
            raise ErreurDocker("démarrage de la boîte impossible", 503)

    def lister_navigateurs(self, utilisateur: str = "") -> list[tuple[str, int]]:
        """Boîtes navigateur (identifiant, date de création en secondes), éventuellement d'un seul utilisateur."""
        filtres = ["--filter", "label=classinus-profil=navigateur"]
        if utilisateur:
            filtres += ["--filter", f"label=classinus-utilisateur={utilisateur}"]
        r = self._docker([
            "ps", "-a", *filtres, "--format", '{{.Names}} {{.Label "classinus-cree"}}',
        ])
        trouvees = []
        for ligne in r.stdout.decode().splitlines():
            morceaux = ligne.split()
            if len(morceaux) == 2 and morceaux[0].startswith("boite-") and morceaux[1].isdigit():
                trouvees.append((morceaux[0].removeprefix("boite-"), int(morceaux[1])))
        return trouvees

    def demarrer(self, boite_id: str) -> None:
        r = self._docker(["start", self.nom(boite_id)], delai=60)
        if r.returncode != 0:
            raise ErreurDocker("reprise de la boîte impossible", 503)

    def arreter(self, boite_id: str) -> None:
        self._docker(["stop", "-t", "2", self.nom(boite_id)], delai=30)

    def supprimer(self, boite_id: str) -> None:
        nom = self.nom(boite_id)
        self._docker(["rm", "-f", nom], delai=30)
        self._docker(["volume", "rm", "-f", f"volume-{nom}"], delai=30)

    def executer(self, boite_id: str, commande: str, delai: int) -> dict:
        delai = max(1, min(int(delai), 3600))
        r = self._docker([
            "exec", "-u", "1000:1000", "-w", "/home/user", self.nom(boite_id),
            "timeout", "-k", "2", str(delai), "sh", "-c", commande,
        ], delai=delai + 15)
        if r.returncode == 124:
            sortie_erreur = (r.stderr + f"\nCommande interrompue après {delai} s.".encode())
        else:
            sortie_erreur = r.stderr
        return {
            "stdout": r.stdout[: self.sortie_max].decode("utf-8", "replace"),
            "stderr": sortie_erreur[: self.sortie_max].decode("utf-8", "replace"),
            "exit_code": r.returncode,
        }

    def lire(self, boite_id: str, chemin: str) -> bytes:
        r = self._docker(["exec", "-u", "1000:1000", self.nom(boite_id), "cat", "--", chemin_sur(chemin)], delai=60)
        if r.returncode != 0:
            raise ErreurDocker("fichier introuvable", 404)
        if len(r.stdout) > self.lecture_max:
            raise ErreurDocker("fichier trop volumineux", 413)
        return r.stdout

    def ecrire(self, boite_id: str, chemin: str, octets: bytes) -> None:
        if len(octets) > self.lecture_max:
            raise ErreurDocker("fichier trop volumineux", 413)
        r = self._docker([
            "exec", "-i", "-u", "1000:1000", self.nom(boite_id), "sh", "-c",
            'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"', "sh", chemin_sur(chemin),
        ], entree=octets, delai=120)
        if r.returncode != 0:
            raise ErreurDocker("écriture impossible", 500)
