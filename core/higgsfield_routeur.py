"""Routeur Higgsfield : API d'abord, notre MCP en repli, jamais d'equivalent.

Le LLM exprime une capacite (core/higgsfield_capacites.py), ce module dit
par quelle voie elle passe. Choix deterministe, cote backend : le LLM ne
choisit ni le transport, ni une cle, ni le compte.
"""
from core.higgsfield_capacites import capacite_par_id


def choisir_voie(identifiant, api_disponible, mcp_disponible):
    """Renvoie {"capacite":..., "voie": "api"|"mcp"|"indisponible", "raison":...}.

    Les deux disponibilites sont injectees (booleens) pour rester testable
    sans reseau ni base.
    """
    capacite = capacite_par_id(identifiant)
    if capacite is None:
        return {
            "capacite": None,
            "voie": "indisponible",
            "raison": f"Capacite \"{identifiant}\" inconnue du registre Higgsfield.",
        }
    if capacite["voie"] == "api":
        if api_disponible:
            return {"capacite": capacite, "voie": "api", "raison": "Disponible via l'API Classinus."}
        return {
            "capacite": capacite,
            "voie": "indisponible",
            "raison": "L'API Higgsfield de Classinus n'est pas configuree cote serveur.",
        }
    # Capacite MCP-only : aucun repli API, ce ne serait pas la meme fonction.
    if mcp_disponible:
        return {"capacite": capacite, "voie": "mcp", "raison": "Fonction absente de l'API, servie par notre MCP partage."}
    return {
        "capacite": capacite,
        "voie": "indisponible",
        "raison": (
            "Fonction disponible uniquement via le MCP Higgsfield, et le compte "
            "partage de Classinus n'est pas connecte en ce moment."
        ),
    }
