"""
Sortie réseau filtrée des boîtes. Les boîtes vivent sur un réseau Docker interne, sans aucune
route vers Internet : leur seul passage est ce proxy, qui laisse sortir uniquement vers les
domaines autorisés pour CETTE boîte (identifiée par son adresse), uniquement vers des adresses
publiques, uniquement sur les ports 80 et 443.
"""
import asyncio
import ipaddress
import logging
import socket

PORTS_AUTORISES = {80, 443}
DELAI_INACTIVITE = 300


def domaine_autorise(hote: str, autorises: list[str]) -> bool:
    """Un nom exact, ou *.exemple.org pour les sous-domaines de exemple.org."""
    hote = (hote or "").strip().lower().rstrip(".")
    if not hote:
        return False
    try:
        ipaddress.ip_address(hote)
        return False
    except ValueError:
        pass
    for regle in autorises:
        regle = str(regle).strip().lower().rstrip(".")
        if regle.startswith("*."):
            if hote.endswith(regle[1:]) and len(hote) > len(regle) - 1:
                return True
        elif hote == regle:
            return True
    return False


def adresse_publique(adresse: str) -> bool:
    """Refuse le réseau interne, le loopback, les adresses de lien local (dont 169.254.x.x) et réservées."""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class RegistreBoites:
    """Associe l'adresse d'une boîte à ses domaines autorisés."""

    def __init__(self):
        self._par_adresse: dict[str, list[str]] = {}
        self._adresse_de: dict[str, str] = {}

    def regler(self, boite_id: str, adresse: str | None, domaines: list[str]) -> None:
        ancienne = self._adresse_de.pop(boite_id, None)
        if ancienne:
            self._par_adresse.pop(ancienne, None)
        if adresse:
            self._par_adresse[adresse] = list(domaines)
            self._adresse_de[boite_id] = adresse

    def oublier(self, boite_id: str) -> None:
        self.regler(boite_id, None, [])

    def domaines(self, adresse: str) -> list[str] | None:
        return self._par_adresse.get(adresse)


async def _resoudre_public(hote: str, port: int):
    boucle = asyncio.get_running_loop()
    infos = await boucle.getaddrinfo(hote, port, type=socket.SOCK_STREAM)
    for _famille, _t, _p, _n, adresse in infos:
        if adresse_publique(adresse[0]):
            return adresse[0]
    return None


async def _relayer(lecteur, ecrivain):
    try:
        while True:
            morceau = await asyncio.wait_for(lecteur.read(65536), DELAI_INACTIVITE)
            if not morceau:
                break
            ecrivain.write(morceau)
            await ecrivain.drain()
    except Exception:
        pass
    finally:
        try:
            ecrivain.close()
        except Exception:
            pass


def fabriquer_gestionnaire(registre: RegistreBoites):
    async def gerer(lecteur, ecrivain):
        try:
            pair = ecrivain.get_extra_info("peername") or ("", 0)
            autorises = registre.domaines(pair[0])
            tete = await asyncio.wait_for(lecteur.readuntil(b"\r\n\r\n"), 15)
            ligne, _, reste = tete.partition(b"\r\n")
            methode, cible, version = (ligne.decode("latin-1").split(" ") + ["", "", ""])[:3]
            if methode.upper() == "CONNECT":
                hote, _, port_texte = cible.rpartition(":")
                port = int(port_texte or 443)
                suite = b""
            else:
                url = cible.split("://", 1)
                if len(url) != 2 or url[0].lower() != "http":
                    raise PermissionError("requête non prise en charge")
                autorite, _, chemin = url[1].partition("/")
                hote, _, port_texte = autorite.partition(":")
                port = int(port_texte or 80)
                suite = f"{methode} /{chemin} {version}\r\n".encode("latin-1") + reste
            if autorises is None or port not in PORTS_AUTORISES or not domaine_autorise(hote, autorises):
                raise PermissionError("domaine non autorisé")
            adresse = await _resoudre_public(hote, port)
            if not adresse:
                raise PermissionError("adresse non publique")
            distant_l, distant_e = await asyncio.wait_for(asyncio.open_connection(adresse, port), 15)
            if methode.upper() == "CONNECT":
                ecrivain.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await ecrivain.drain()
            else:
                distant_e.write(suite)
                await distant_e.drain()
            await asyncio.gather(_relayer(lecteur, distant_e), _relayer(distant_l, ecrivain))
        except PermissionError:
            try:
                ecrivain.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await ecrivain.drain()
            except Exception:
                pass
        except Exception as e:
            logging.warning("proxy boîtes : %s", type(e).__name__)
            try:
                ecrivain.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await ecrivain.drain()
            except Exception:
                pass
        finally:
            try:
                ecrivain.close()
            except Exception:
                pass

    return gerer
