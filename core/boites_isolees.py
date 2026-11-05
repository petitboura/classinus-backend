"""
Fournisseur des boîtes d'exécution de code : E2B ou boîtes Docker sur un serveur Vultr.

core/outils_execution_code.py ne connaît qu'une classe avec create, connect, kill et pause,
et des objets avec commands.run, files.read, files.write et update_network. Ce module fournit
cette même interface pour les deux fournisseurs, de sorte que les 16 actions de l'outil
ignorent qui les exécute.

Choix par la variable EXECUTION_CODE_FOURNISSEUR : "e2b" (valeur par défaut, la production
ne change pas) ou "docker". Le mode docker demande BOITES_URL et BOITES_TOKEN : l'adresse et
le jeton du service boites_service qui tourne sur le serveur Vultr. Le backend n'a jamais
accès au socket Docker : seul ce petit service le possède.
"""
import logging
import os
from dataclasses import dataclass

import httpx

_FOURNISSEURS = ("e2b", "docker")


def fournisseur() -> str:
    valeur = (os.environ.get("EXECUTION_CODE_FOURNISSEUR") or "e2b").strip().lower()
    if valeur not in _FOURNISSEURS:
        logging.error("EXECUTION_CODE_FOURNISSEUR inconnu (%r), E2B conservé.", valeur)
        return "e2b"
    return valeur


def raison_non_configuree() -> str | None:
    """Pourquoi l'exécution de code n'est pas proposée (None si le fournisseur est prêt)."""
    if fournisseur() == "docker":
        if not os.environ.get("BOITES_URL"):
            return "la variable BOITES_URL est absente du serveur"
        if not os.environ.get("BOITES_TOKEN"):
            return "la variable BOITES_TOKEN est absente du serveur"
        return None
    if not os.environ.get("E2B_API_KEY"):
        return "la variable E2B_API_KEY est absente du serveur"
    return None


def configuree() -> bool:
    return raison_non_configuree() is None


def classe_sandbox():
    """Classe à utiliser pour create, connect, kill et pause selon le fournisseur choisi."""
    if fournisseur() == "docker":
        return BoiteDocker
    from e2b import Sandbox
    return Sandbox


class ErreurBoite(Exception):
    """Erreur du service de boîtes. status_code suit la convention déjà lue par l'outil."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ResultatCommande:
    stdout: str
    stderr: str
    exit_code: int


def _delai() -> float:
    try:
        return float(os.environ.get("BOITES_DELAI_REQUETE", "120"))
    except ValueError:
        return 120.0


def _client(delai: float | None = None) -> httpx.Client:
    url = (os.environ.get("BOITES_URL") or "").rstrip("/")
    token = os.environ.get("BOITES_TOKEN") or ""
    if not url or not token:
        raise ErreurBoite("Service de boîtes non configuré.", 503)
    return httpx.Client(
        base_url=url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=delai or _delai(),
    )


def _appeler(methode: str, chemin: str, *, delai: float | None = None, **kw) -> httpx.Response:
    try:
        with _client(delai) as client:
            reponse = client.request(methode, chemin, **kw)
    except httpx.HTTPError as e:
        raise ErreurBoite(f"Service de boîtes injoignable ({type(e).__name__}).", 503) from e
    if reponse.status_code >= 400:
        message = "not found" if reponse.status_code == 404 else f"erreur HTTP {reponse.status_code}"
        raise ErreurBoite(message, reponse.status_code)
    return reponse


class _Commandes:
    def __init__(self, boite_id: str):
        self._id = boite_id

    def run(self, commande: str, timeout=60, request_timeout=None, **_ignores) -> ResultatCommande:
        delai_requete = float(request_timeout or (float(timeout or 60) + 20))
        reponse = _appeler(
            "POST", f"/boites/{self._id}/commande",
            json={"commande": commande, "timeout": int(timeout or 60)},
            delai=delai_requete,
        )
        donnees = reponse.json()
        return ResultatCommande(
            stdout=donnees.get("stdout", ""),
            stderr=donnees.get("stderr", ""),
            exit_code=int(donnees.get("exit_code", 0)),
        )


class _Fichiers:
    def __init__(self, boite_id: str):
        self._id = boite_id

    def read(self, chemin: str, format: str = "text", request_timeout=None, **_ignores):
        reponse = _appeler(
            "GET", f"/boites/{self._id}/fichier", params={"chemin": chemin},
            delai=float(request_timeout) if request_timeout else None,
        )
        return reponse.content if format == "bytes" else reponse.content.decode("utf-8", "replace")

    def write(self, chemin: str, contenu, **_ignores):
        octets = contenu.encode("utf-8") if isinstance(contenu, str) else bytes(contenu)
        _appeler(
            "PUT", f"/boites/{self._id}/fichier", params={"chemin": chemin},
            content=octets, headers={"Content-Type": "application/octet-stream"},
        )


class BoiteDocker:
    """Une boîte Docker du serveur Vultr, avec la même interface que le Sandbox E2B."""

    def __init__(self, boite_id: str):
        self.sandbox_id = boite_id
        self.commands = _Commandes(boite_id)
        self.files = _Fichiers(boite_id)

    @classmethod
    def create(cls, template=None, timeout=3600, metadata=None, network=None, lifecycle=None, **_ignores):
        reponse = _appeler("POST", "/boites", json={"timeout": int(timeout or 3600)})
        boite = cls(reponse.json()["id"])
        try:
            boite.update_network(network)
        except Exception:
            # Une boîte dont le réseau n'a pas pu être réglé ne doit pas survivre : fermée par défaut.
            try:
                cls.kill(boite.sandbox_id)
            except Exception:
                pass
            raise
        return boite

    @classmethod
    def connect(cls, sandbox_id: str, timeout=3600, **_ignores):
        _appeler("POST", f"/boites/{sandbox_id}/connexion", json={"timeout": int(timeout or 3600)})
        return cls(sandbox_id)

    @classmethod
    def kill(cls, sandbox_id: str, **_ignores):
        _appeler("DELETE", f"/boites/{sandbox_id}")

    @classmethod
    def pause(cls, sandbox_id: str, **_ignores):
        _appeler("POST", f"/boites/{sandbox_id}/pause")

    def update_network(self, options):
        """Règles réseau au format de l'outil : tout refusé sauf les domaines de allow_out."""
        autorises = list((options or {}).get("allow_out") or [])
        _appeler("PUT", f"/boites/{self.sandbox_id}/reseau", json={"allow_out": autorises})


def ouvrir_navigateur(cle: str, utilisateur: str, network=None) -> "BoiteDocker":
    """Boîte navigateur de la conversation : créée ou reprise par le service, réseau réglé à chaque appel."""
    reponse = _appeler("POST", "/navigateurs", json={"cle": cle, "utilisateur": utilisateur})
    boite = BoiteDocker(reponse.json()["id"])
    try:
        boite.update_network(network)
    except Exception:
        # Une boîte dont le réseau n'a pas pu être réglé ne reste pas ouverte : fermée par défaut.
        try:
            BoiteDocker.kill(boite.sandbox_id)
        except Exception:
            pass
        raise
    return boite


def detruire_navigateurs_utilisateur(utilisateur: str) -> None:
    """Détruit toutes les boîtes navigateur d'un utilisateur (suppression de compte)."""
    _appeler("DELETE", "/navigateurs", params={"utilisateur": utilisateur})
