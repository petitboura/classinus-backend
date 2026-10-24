"""Plafond de taille totale d'une requete, pour proteger la memoire du serveur.

Le chat envoie tout en une seule requete (message, historique, images) et FastAPI la lit en
entier avant de la valider. Sans plafond, un envoi tres volumineux, notamment d'un visiteur
non connecte, peut saturer la memoire du service pour tous les autres utilisateurs. Le
limiteur de debit compte les requetes, pas leur taille.

Ce plafond ne regarde jamais le contenu (message, historique, outils) : il ne mesure que les
octets recus. Deux controles : l'en-tete Content-Length (refus immediat, sans rien lire) et le
comptage des octets au fil de la lecture (requete sans Content-Length, par exemple en
transfert par morceaux). La reponse est une erreur structuree 413 traduisible, comme les
autres erreurs de l'API (core/erreurs.py).
"""
from starlette.responses import JSONResponse

from core.erreurs import erreur_api

_METHODES_AVEC_CORPS = ("POST", "PUT", "PATCH")


class _RequeteTropVolumineuse(Exception):
    pass


class PlafondTailleRequete:
    def __init__(self, app, prefixes, taille_max_mo):
        self.app = app
        self.prefixes = tuple(prefixes)
        self.taille_max_mo = taille_max_mo
        self.taille_max_octets = taille_max_mo * 1024 * 1024

    def _concerne(self, scope):
        return (
            scope["type"] == "http"
            and scope.get("method") in _METHODES_AVEC_CORPS
            and scope.get("path", "").startswith(self.prefixes)
        )

    @staticmethod
    def _taille_annoncee(scope):
        for cle, valeur in scope.get("headers", []):
            if cle == b"content-length":
                try:
                    return int(valeur)
                except ValueError:
                    return None
        return None

    async def _refuser(self, scope, receive, send):
        erreur = erreur_api(413, "REQUETE_TROP_VOLUMINEUSE", taille_max=self.taille_max_mo)
        reponse = JSONResponse(status_code=413, content={"detail": erreur.detail})
        await reponse(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if not self._concerne(scope):
            await self.app(scope, receive, send)
            return

        annoncee = self._taille_annoncee(scope)
        if annoncee is not None and annoncee > self.taille_max_octets:
            await self._refuser(scope, receive, send)
            return

        recus = 0
        reponse_commencee = False

        async def recevoir():
            nonlocal recus
            message = await receive()
            if message["type"] == "http.request":
                recus += len(message.get("body", b""))
                if recus > self.taille_max_octets:
                    raise _RequeteTropVolumineuse()
            return message

        async def envoyer(message):
            nonlocal reponse_commencee
            if message["type"] == "http.response.start":
                reponse_commencee = True
            await send(message)

        try:
            await self.app(scope, recevoir, envoyer)
        except _RequeteTropVolumineuse:
            if reponse_commencee:
                raise
            await self._refuser(scope, receive, send)
