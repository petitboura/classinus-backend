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
    if isinstance(detail, str):
        # Compatibilité avec les anciennes routes FastAPI qui renvoient
        # HTTPException(detail="...") sans code stable. On ne traduit que
        # les messages strictement identiques au catalogue et seulement si
        # toutes les entrées correspondantes convergent vers la même phrase.
        traductions = {
            MESSAGES_EN[code]
            for code, message_fr in MESSAGES_FR.items()
            if message_fr == detail and code in MESSAGES_EN
        }
        if len(traductions) == 1:
            erreur["detail"] = next(iter(traductions))
            return True
        return False
    if not isinstance(detail, dict):
        return False
    code = detail.get("code")
    if not isinstance(code, str):
        return False
    modele = MESSAGES_EN.get(code)
    if not modele:
        return False
    modele_fr = MESSAGES_FR.get(code)
    parametres = detail.get("params")
    try:
        message_en = modele.format(**parametres) if isinstance(parametres, dict) else modele
        if modele_fr:
            message_fr_attendu = (
                modele_fr.format(**parametres) if isinstance(parametres, dict) else modele_fr
            )
        else:
            # Les routes historiques sans entrée française dans le catalogue
            # gardent leur repli français générique ; seule cette valeur précise
            # peut être remplacée, jamais un message personnalisé.
            message_fr_attendu = MESSAGES_FR["ERREUR_INCONNUE"]
    except (KeyError, IndexError, ValueError):
        # Une traduction mal paramétrée ne doit jamais casser une réponse API.
        return False
    # Ne remplace pas un message métier explicitement fourni par un appelant.
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
        messages_corps = []
        intercepter = False

        async def envoyer(message):
            nonlocal debut, messages_corps, intercepter
            if message["type"] == "http.response.start":
                entetes = {
                    cle.lower(): valeur.lower()
                    for cle, valeur in message.get("headers", [])
                }
                type_contenu = entetes.get(b"content-type", b"")
                intercepter = (
                    int(message.get("status", 200)) >= 400
                    and b"application/json" in type_contenu
                    and b"text/event-stream" not in type_contenu
                    and b"content-encoding" not in entetes
                )
                if intercepter:
                    debut = message
                    messages_corps = []
                    return
                await send(message)
                return

            if intercepter and message["type"] == "http.response.body":
                messages_corps.append(message)
                if message.get("more_body", False):
                    return

                corps_original = b"".join(partie.get("body", b"") for partie in messages_corps)
                corps_final = corps_original
                try:
                    donnees = json.loads(corps_original.decode("utf-8"))
                    modifie = _traduire_enveloppe(donnees)
                    if modifie:
                        corps_final = json.dumps(
                            donnees, ensure_ascii=False, separators=(",", ":")
                        ).encode("utf-8")
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    # Une réponse atypique doit passer telle quelle.
                    modifie = False

                if modifie:
                    entetes = [
                        (cle, valeur)
                        for cle, valeur in (debut.get("headers") or [])
                        if cle.lower() not in (b"content-length", b"transfer-encoding", b"vary")
                    ]
                    entetes.append((b"content-length", str(len(corps_final)).encode("ascii")))
                    deja_vary = next(
                        (v for k, v in (debut.get("headers") or []) if k.lower() == b"vary"),
                        None,
                    )
                    valeur_vary = deja_vary.decode("latin-1") if deja_vary else ""
                    parties = [v.strip() for v in valeur_vary.split(",") if v.strip()]
                    if not any(v.lower() == "accept-language" for v in parties):
                        parties.append("Accept-Language")
                    entetes.append((b"vary", ", ".join(parties).encode("latin-1")))
                    debut["headers"] = entetes
                    await send(debut)
                    await send({"type": "http.response.body", "body": corps_final, "more_body": False})
                else:
                    # Aucun code traduisible : renvoie exactement les en-têtes et
                    # les fragments originaux, sans réécrire le corps JSON.
                    await send(debut)
                    for partie in messages_corps:
                        await send(partie)

                debut = None
                messages_corps = []
                intercepter = False
                return

            await send(message)

        await self.app(scope, receive, envoyer)
