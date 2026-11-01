"""Client du MCP Higgsfield officiel via le compte partage Classinus.

Utilise le jeton OAuth du compte de service (connexions/higgsfield_mcp.py,
variable HIGGSFIELD_MCP_SERVICE_USER_ID). Aucun jeton colle, aucune cle API :
si le jeton meurt et ne se renouvelle pas, les appels echouent avec un
message clair et journalise, sans rien depenser. Le MCP personnel d'un
utilisateur n'est jamais utilise ici.

Protocole : HTTP streamable du MCP officiel (initialize, tools/list,
tools/call) en JSON-RPC, reponses JSON ou flux SSE selon le serveur.
"""
import json
import logging

import httpx

from connexions import higgsfield_mcp as _connexion
from core.higgsfield_capacites import OUTILS_MCP_AUTORISES
from core.higgsfield_requetes import ErreurHiggsfield

MCP_URL = _connexion.MCP_URL
DELAI_SECONDES = 120


def _erreur_indisponible(message):
    logging.error("MCP Higgsfield partage indisponible : %s", message)
    return ErreurHiggsfield(message)


def _token_ou_erreur():
    etat = _connexion.etat_service()
    if not etat["configure"]:
        raise _erreur_indisponible(
            "Le MCP Higgsfield de Classinus n'est pas configure "
            "(HIGGSFIELD_MCP_SERVICE_USER_ID absent cote serveur)."
        )
    token = _connexion.obtenir_token_service()
    if not token:
        raise _erreur_indisponible(
            "Le compte Higgsfield partage de Classinus doit etre reconnecte "
            "(jeton expire). Les fonctions API restent disponibles."
        )
    return token


def _lire_reponse_jsonrpc(reponse):
    """Extrait l'objet JSON-RPC d'une reponse JSON ou d'un flux SSE."""
    type_contenu = (reponse.headers.get("content-type") or "").lower()
    if "text/event-stream" in type_contenu:
        dernier = None
        for ligne in reponse.text.splitlines():
            ligne = ligne.strip()
            if ligne.startswith("data:"):
                try:
                    dernier = json.loads(ligne[5:].strip())
                except ValueError:
                    continue
        if dernier is None:
            raise ErreurHiggsfield("Reponse MCP Higgsfield illisible.")
        return dernier
    try:
        return reponse.json()
    except ValueError:
        raise ErreurHiggsfield("Reponse MCP Higgsfield illisible.")


class _SessionMCP:
    """Une session courte : ouverture, un ou plusieurs appels, fermeture."""

    def __init__(self, token):
        self._client = httpx.Client(timeout=DELAI_SECONDES)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._session_id = None
        self._prochain_id = 1

    def __enter__(self):
        corps = {
            "jsonrpc": "2.0",
            "id": self._prendre_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Classinus", "version": "1.0"},
            },
        }
        reponse = self._poster(corps)
        donnees = _lire_reponse_jsonrpc(reponse)
        if donnees.get("error"):
            raise ErreurHiggsfield("Le MCP Higgsfield a refuse l'ouverture de session.")
        self._session_id = reponse.headers.get("mcp-session-id")
        self._poster({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }, notification=True)
        return self

    def __exit__(self, *exc):
        self._client.close()
        return False

    def _prendre_id(self):
        valeur = self._prochain_id
        self._prochain_id += 1
        return valeur

    def _poster(self, corps, notification=False):
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            reponse = self._client.post(MCP_URL, headers=headers, json=corps)
        except httpx.HTTPError as e:
            raise _erreur_indisponible(f"Le MCP Higgsfield ne repond pas ({e}).")
        if reponse.status_code in (401, 403):
            raise _erreur_indisponible(
                "Le compte Higgsfield partage de Classinus doit etre reconnecte "
                "(jeton refuse). Les fonctions API restent disponibles."
            )
        if not notification and reponse.status_code >= 400:
            raise ErreurHiggsfield(
                f"Le MCP Higgsfield a refuse la demande (code {reponse.status_code})."
            )
        return reponse

    def appeler(self, methode, params):
        reponse = self._poster({
            "jsonrpc": "2.0",
            "id": self._prendre_id(),
            "method": methode,
            "params": params,
        })
        donnees = _lire_reponse_jsonrpc(reponse)
        if donnees.get("error"):
            erreur = donnees["error"] or {}
            message = str(erreur.get("message") or "erreur inconnue")[:300]
            raise ErreurHiggsfield(f"Le MCP Higgsfield a refuse l'appel : {message}")
        return donnees.get("result") or {}


def _texte_resultat(resultat):
    morceaux = []
    for bloc in resultat.get("content") or []:
        if isinstance(bloc, dict) and bloc.get("type") == "text" and bloc.get("text"):
            morceaux.append(bloc["text"])
    if morceaux:
        return "\n".join(morceaux)
    return json.dumps(resultat, ensure_ascii=False)[:4000]


def lister_outils_partages():
    """Outils reels du serveur, filtres sur l'allowlist des fonctions MCP-only."""
    token = _token_ou_erreur()
    with _SessionMCP(token) as session:
        resultat = session.appeler("tools/list", {})
    outils = []
    for outil in resultat.get("tools") or []:
        nom = outil.get("name")
        if nom in OUTILS_MCP_AUTORISES:
            outils.append({
                "nom": nom,
                "description": str(outil.get("description") or "")[:300],
                "schema": outil.get("inputSchema") or {},
            })
    return outils


def appeler_outil_partage(nom_outil, arguments):
    """Appelle un outil allowliste du compte partage. Renvoie le texte du resultat."""
    nom = (nom_outil or "").strip()
    if nom not in OUTILS_MCP_AUTORISES:
        raise ErreurHiggsfield(
            f"Outil MCP \"{nom}\" non autorise sur le compte partage Classinus."
        )
    if not isinstance(arguments, dict):
        raise ErreurHiggsfield("Les arguments de l'outil MCP doivent etre un objet JSON.")
    token = _token_ou_erreur()
    with _SessionMCP(token) as session:
        # Verification en direct : un outil absent du serveur n'est jamais appele.
        presents = {
            o.get("name") for o in (session.appeler("tools/list", {}).get("tools") or [])
        }
        if nom not in presents:
            raise ErreurHiggsfield(
                f"L'outil MCP \"{nom}\" n'est pas expose par le serveur Higgsfield en ce moment."
            )
        resultat = session.appeler("tools/call", {"name": nom, "arguments": arguments})
    if resultat.get("isError"):
        raise ErreurHiggsfield(
            "L'outil MCP Higgsfield a echoue : " + _texte_resultat(resultat)[:300]
        )
    return _texte_resultat(resultat)
