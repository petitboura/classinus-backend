"""Réseau sécurisé pour les serveurs MCP ajoutés par les utilisateurs.

Trois protections, toutes appliquées au moment de la connexion réelle (et pas
seulement à l'ajout du serveur) :

1. Aucune redirection n'est suivie. La bibliothèque MCP les suit toujours par
   défaut : un serveur public pouvait répondre « va voir cette adresse interne »
   et Classinus envoyait la requête à l'interne.
2. L'adresse IP est vérifiée au moment exact où la connexion s'ouvre, et la
   connexion se fait directement sur l'adresse vérifiée. Un nom de domaine ne
   peut donc plus changer d'adresse entre la vérification et l'appel.
3. La liste des adresses interdites est écrite explicitement, au lieu de
   dépendre du comportement de `is_global`, qui change selon la version de
   Python (3.11, 3.12 et 3.13 ne répondent pas toujours pareil).
"""
import asyncio
import ipaddress
import socket
from typing import Callable

import httpcore2
import httpx2

# Délais comparables à ceux du client MCP standard (connexion courte, lecture
# longue pour les flux en continu).
DELAI_CONNEXION_SECONDES = 30.0
DELAI_LECTURE_SECONDES = 300.0

_RESEAUX_INTERDITS = tuple(
    ipaddress.ip_network(reseau)
    for reseau in (
        # IPv4
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
        "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
        # IPv6
        "::/96", "::1/128", "100::/64", "2001::/32", "2001:10::/28", "2001:20::/28",
        "2001:db8::/32", "3fff::/20", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8",
        "64:ff9b:1::/48",
    )
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _adresses_ipv4_integrees(ip):
    """Adresses IPv4 cachées dans une adresse IPv6 (écriture « mappée », 6to4, NAT64)."""
    if ip.version != 6:
        return []
    integrees = []
    if ip.ipv4_mapped is not None:
        integrees.append(ip.ipv4_mapped)
    if ip.sixtofour is not None:
        integrees.append(ip.sixtofour)
    if ip in _NAT64:
        integrees.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return integrees


def verifier_ip_publique(valeur: str) -> None:
    """Lève ValueError si l'adresse n'est pas une adresse publique joignable depuis Internet."""
    try:
        ip = ipaddress.ip_address(str(valeur).split("%", 1)[0])
    except ValueError:
        raise ValueError("L’adresse du serveur MCP est invalide.")
    for candidate in [ip, *_adresses_ipv4_integrees(ip)]:
        if not candidate.is_global or any(candidate in reseau for reseau in _RESEAUX_INTERDITS):
            raise ValueError("Le serveur MCP pointe vers une adresse IP privée ou réservée.")


def resoudre_adresses_publiques(hote: str, port: int, verificateur: Callable[[str], None] = verifier_ip_publique) -> list[str]:
    """Résout un nom d'hôte et ne renvoie que des adresses vérifiées ; toute adresse interdite refuse l'ensemble."""
    try:
        resultats = socket.getaddrinfo(hote, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("Le nom d’hôte du serveur MCP ne peut pas être résolu.")
    adresses = list(dict.fromkeys(item[4][0].split("%", 1)[0] for item in resultats))
    if not adresses:
        raise ValueError("Le nom d’hôte du serveur MCP ne possède aucune adresse publique.")
    for adresse in adresses:
        verificateur(adresse)
    return adresses


class _ReseauVerifie(httpcore2.AsyncNetworkBackend):
    """Ouvre la connexion directement sur une adresse vérifiée à l'instant même."""

    def __init__(self, verificateur: Callable[[str], None]):
        self._verificateur = verificateur
        self._interne = httpcore2.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            adresses = await asyncio.get_running_loop().run_in_executor(
                None, resoudre_adresses_publiques, host, port, self._verificateur
            )
        except ValueError as exc:
            raise httpcore2.ConnectError(str(exc))
        derniere_erreur = None
        for adresse in adresses:
            try:
                return await self._interne.connect_tcp(
                    adresse, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except Exception as exc:
                derniere_erreur = exc
        raise derniere_erreur or httpcore2.ConnectError("Connexion impossible.")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore2.ConnectError("Les connexions locales sont interdites.")

    async def sleep(self, seconds):
        await self._interne.sleep(seconds)


class TransportVerifie(httpx2.AsyncHTTPTransport):
    """Transport HTTP dont les connexions passent toutes par `_ReseauVerifie`."""

    def __init__(self, verificateur: Callable[[str], None] = verifier_ip_publique):
        super().__init__(http1=True, http2=False)
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(),
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            network_backend=_ReseauVerifie(verificateur),
        )


def creer_client_http_mcp(headers: dict | None = None, verificateur: Callable[[str], None] = verifier_ip_publique, timeout=None):
    """Client HTTP des serveurs MCP personnalisés : sans redirection, adresse vérifiée à la connexion."""
    return httpx2.AsyncClient(
        transport=TransportVerifie(verificateur),
        follow_redirects=False,
        timeout=timeout or httpx2.Timeout(DELAI_CONNEXION_SECONDES, read=DELAI_LECTURE_SECONDES),
        headers=headers or {},
    )


def requete_securisee(methode: str, url: str, *, verificateur: Callable[[str], None] = verifier_ip_publique,
                      timeout: float = 10, **options):
    """Requête ponctuelle (métadonnées OAuth, échange de jetons) avec les mêmes protections.

    À appeler depuis du code synchrone, hors boucle asyncio (routes FastAPI classiques).
    """
    async def _executer():
        async with creer_client_http_mcp(verificateur=verificateur, timeout=httpx2.Timeout(timeout)) as client:
            return await client.request(methode, url, **options)

    return asyncio.run(_executer())
