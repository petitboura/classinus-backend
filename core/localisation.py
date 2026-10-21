"""Localisation des erreurs API selon l'en-tête HTTP Accept-Language.

Cette couche ne modifie ni les routes, ni les statuts, ni les règles d'accès,
ni les données métier. Elle traduit uniquement les enveloppes d'erreur
structurées dont le code est connu ; les réponses normales, le contenu de
l'utilisateur et les flux SSE restent inchangés.
"""
import json
from typing import Any

from core.erreurs import MESSAGES_EN, MESSAGES_FR


def _prefer_anglais(scope: dict[str, Any]) -> bool:
    entetes = dict(scope.get("headers") or [])
    valeur = entetes.get(b"accept-language", b"fr").decode("latin-1").strip().lower()
    # Le frontend envoie explicitement "en" ou "fr". Cette lecture couvre
    # aussi les clients standards comme en-US,en;q=0.9,fr;q=0.8.
    langues = []
    for partie in valeur.split(","):
        morceaux = partie.strip().split(";")
        code = morceaux[0].strip()
        try:
            poids = float(morceaux[1].split("=", 1)[1]) if len(morceaux) > 1 and "=" in morceaux[1] else 1.0
        except (ValueError, IndexError):
            poids = 1.0
        if code and poids > 0:
            langues.append((poids, code))
    langues.sort(key=lambda langue: langue[0], reverse=True)
    return bool(langues and (langues[0][1] == "en" or langues[0][1].startswith("en-")))


def _traduire_enveloppe(erreur: Any) -> bool:
    """Traduit le format d'erreur API stable sans altérer les autres JSON."""
    if not isinstance(erreur, dict):
        return False
    detail = erreur.get("detail")
    if not isinstance(detail, dict):
        return False
    code = detail.get("code")
    if not isinstance(code, str):
        return False
    modele = MESSAGES_EN.get(code)
    modele_fr = MESSAGES_FR.get(code)
    if not modele or not modele_fr:
        return False
    parametres = detail.get("params")
    try:
        message_fr_attendu = (
            modele_fr.format(**parametres) if isinstance(parametres, dict) else modele_fr
        )
        message_en = modele.format(**parametres) if isinstance(parametres, dict) else modele
    except (KeyError, IndexError, ValueError):
        # Une traduction mal paramétrée ne doit jamais casser une réponse API.
        return False
    # Ne remplace pas un message métier explicitement fourni par un appelant :
    # seules les erreurs fondées sur le catalogue stable sont traduites.
    if detail.get("message") != message_fr_attendu:
        return False
    detail["message"] = message_en
    erreur["detail"] = detail
    return True


class MiddlewareLangueErreurs:
    """Traduit les erreurs JSON structurées vers l'anglais lorsqu'il est demandé."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _prefer_anglais(scope):
            await self.app(scope, receive, send)
            return

        debut = None
        morceaux = []
        intercepter = False

        async def envoyer(message):
            nonlocal debut, morceaux, intercepter
            if message["type"] == "http.response.start":
                entetes = {
                    cle.lower(): valeur.lower()
                    for cle, valeur in message.get("headers", [])
                    if cle.lower() == b"content-type"
                }
                type_contenu = entetes.get(b"content-type", b"")
                intercepter = (
                    int(message.get("status", 200)) >= 400
                    and b"application/json" in type_contenu
                    and b"text/event-stream" not in type_contenu
                )
                if intercepter:
                    debut = message
                    morceaux = []
                    return
                await send(message)
                return

            if intercepter and message["type"] == "http.response.body":
                morceaux.append(message.get("body", b""))
                if message.get("more_body", False):
                    return

                corps = b"".join(morceaux)
                try:
                    donnees = json.loads(corps.decode("utf-8"))
                    modifie = _traduire_enveloppe(donnees)
                    if modifie:
                        corps = json.dumps(donnees, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    # Une réponse atypique doit passer telle quelle.
                    modifie = False

                entetes = [
                    (cle, valeur)
                    for cle, valeur in (debut.get("headers") or [])
                    if cle.lower() not in (b"content-length", b"transfer-encoding")
                ]
                entetes.append((b"content-length", str(len(corps)).encode("ascii")))
                if modifie:
                    deja_vary = next((v for k, v in entetes if k.lower() == b"vary"), None)
                    entetes = [(k, v) for k, v in entetes if k.lower() != b"vary"]
                    valeur_vary = deja_vary.decode("latin-1") if deja_vary else ""
                    parties = [v.strip() for v in valeur_vary.split(",") if v.strip()]
                    if not any(v.lower() == "accept-language" for v in parties):
                        parties.append("Accept-Language")
                    entetes.append((b"vary", ", ".join(parties).encode("latin-1")))
                debut["headers"] = entetes
                await send(debut)
                await send({"type": "http.response.body", "body": corps, "more_body": False})
                debut = None
                morceaux = []
                intercepter = False
                return

            await send(message)

        await self.app(scope, receive, envoyer)
