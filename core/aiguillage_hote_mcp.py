"""
Aiguillage par domaine du serveur MCP "espace" de Classinus.

But : que le connecteur Classinus dans Claude s'ajoute avec une adresse
nue, sans chemin (ex. https://mcp.classinus.com), comme les autres
connecteurs. Le serveur MCP est monte en interne sur un chemin fixe
(voir `CHEMIN_INTERNE_MCP_ESPACE` dans api/main.py) ; ce module fait
simplement en sorte qu'une requete arrivant a la RACINE du domaine
dedie soit traitee comme une requete vers ce chemin interne.

Seule la racine ("/") du domaine dedie est concernee. Les autres chemins
de ce domaine (decouverte OAuth, etc.) et tous les chemins des autres
domaines restent exactement comme avant.

Le domaine dedie n'est jamais ecrit en dur : il est deduit de l'adresse
publique du serveur de ressources (variable d'environnement
URL_RESOURCE_SERVER_PUBLIC, voir core/mcp_auth_public.py).
"""

from urllib.parse import urlparse


def hote_depuis_url(url: str | None) -> str | None:
    """Nom d'hote en minuscules d'une URL, ou None si absent/invalide."""
    if not url:
        return None
    hote = urlparse(url).hostname
    return hote.lower() if hote else None


def _hote_de_la_requete(scope) -> str | None:
    """Nom d'hote (sans port, en minuscules) de l'en-tete Host."""
    for nom, valeur in scope.get("headers", []):
        if nom == b"host":
            return valeur.decode("latin-1").split(":", 1)[0].strip().lower() or None
    return None


class AiguillageHoteMcp:
    """Middleware ASGI : racine du domaine dedie -> chemin interne du MCP."""

    def __init__(self, app, hote_mcp: str | None, chemin_interne: str):
        self._app = app
        self._hote_mcp = hote_mcp
        self._chemin_interne = chemin_interne

    async def __call__(self, scope, receive, send):
        if (
            self._hote_mcp
            and scope["type"] == "http"
            and scope["path"] in ("", "/")
            and _hote_de_la_requete(scope) == self._hote_mcp
        ):
            scope = dict(scope)
            scope["path"] = self._chemin_interne
            scope["raw_path"] = self._chemin_interne.encode("latin-1")
        await self._app(scope, receive, send)
