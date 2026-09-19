"""
Routes propres à Notion, pour le sélecteur du bouton Applications : chercher
une page ou une base, lire les lignes d'une base, créer une page.

Tout passe par le serveur MCP de Notion (mcp.notion.com), jamais par l'API
classique de Notion. Le jeton obtenu par la connexion (connexions/notion.py)
est un jeton MCP : il est refusé par api.notion.com (erreur 401 constatée en
production sur l'ancienne version de ces routes).

La confirmation avant écriture (outils sensibles) ne s'applique pas ici : le
clic sur "Créer" dans le formulaire du sélecteur en tient lieu.
"""

import os
import re
import sys
import json
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import utilisateur_courant
from core.erreurs import erreur_api
import connexions.notion as notion

# mcp_tools importe ses voisins sans préfixe (from registre_outils import ...),
# ce qui ne marche que si core/ est dans le chemin de recherche. Même
# contournement que api/agents.py.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
from mcp_tools import _appeler_outil_async  # noqa: E402

URL_MCP_NOTION = "https://mcp.notion.com/mcp"

router = APIRouter(prefix="/api/connexions/notion", tags=["connexions-notion"])


def _entetes_ou_erreur(user_id):
    token = notion.obtenir_token_valide(user_id)
    if not token:
        raise erreur_api(400, "NOTION_NON_CONNECTE")
    return {"Authorization": f"Bearer {token}"}


def rechercher_pages_notion(user_id, q):
    """
    Cherche pages et bases visibles par la personne. Renvoie une liste de
    dictionnaires {"id", "titre", "type", "url"}. Utilisée aussi par la route
    mobile de recherche. Lève une erreur d'API si Notion ne répond pas.
    """
    entetes = _entetes_ou_erreur(user_id)
    try:
        brut = asyncio.run(
            _appeler_outil_async(URL_MCP_NOTION, "notion-search", {"query": q, "page_size": 20}, headers=entetes)
        )
        donnees = json.loads(brut)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"ERREUR RECHERCHE NOTION (MCP) : {e}")
        raise erreur_api(502, "NOTION_PAGES_INDISPONIBLE")

    return [
        {
            "id": r.get("id"),
            "titre": r.get("title") or "(sans titre)",
            "type": "database" if r.get("type") == "database" else "page",
            "url": r.get("url"),
        }
        for r in (donnees.get("results") or [])
        if r.get("url")
    ]


@router.get("/pages")
def pages_notion(q: str = "", utilisateur=Depends(utilisateur_courant)):
    # notion-search est une recherche par mots, pas un listing : sans texte
    # tapé, on renvoie une liste vide plutôt que d'inventer une requête.
    if not q.strip():
        return {"pages": []}
    trouvees = rechercher_pages_notion(utilisateur.id, q)
    return {"pages": [{"titre": p["titre"], "type": p["type"], "url": p["url"]} for p in trouvees]}


@router.get("/bases/lignes")
def lignes_base_notion(url: str, q: str = "", utilisateur=Depends(utilisateur_courant)):
    """
    Lit le contenu d'une base Notion. `url` est l'adresse de la base telle que
    renvoyée par /pages (type "database"), pas l'adresse d'une source de
    données : cette route fait la conversion.

    Étape 1 : notion-fetch sur la base, pour obtenir l'adresse de sa source de
    données (collection://...), présente dans une balise <data-source>.
    Étape 2 : notion-query-data-sources en SQL, 50 lignes au plus. Le texte
    tapé (`q`) filtre ensuite côté serveur sur toutes les valeurs de chaque
    ligne : pas de clause SQL construite à partir de ce que la personne tape,
    le schéma des colonnes étant inconnu à l'avance.
    """
    entetes = _entetes_ou_erreur(utilisateur.id)

    try:
        fetch_brut = asyncio.run(_appeler_outil_async(URL_MCP_NOTION, "notion-fetch", {"id": url}, headers=entetes))
    except Exception as e:
        logging.error(f"ERREUR FETCH BASE NOTION (MCP) : {e}")
        raise erreur_api(502, "NOTION_BASE_INDISPONIBLE")

    correspondance = re.search(r"collection://[0-9a-fA-F-]+", fetch_brut)
    if not correspondance:
        raise erreur_api(404, "NOTION_BASE_SANS_DATA_SOURCE")
    data_source_url = correspondance.group(0)

    try:
        query_brut = asyncio.run(
            _appeler_outil_async(
                URL_MCP_NOTION,
                "notion-query-data-sources",
                {
                    "data": {
                        "mode": "sql",
                        "data_source_urls": [data_source_url],
                        "query": f'SELECT * FROM "{data_source_url}" LIMIT 50',
                    }
                },
                headers=entetes,
            )
        )
        donnees = json.loads(query_brut)
    except Exception as e:
        logging.error(f"ERREUR REQUETE BASE NOTION (MCP) : {e}")
        raise erreur_api(502, "NOTION_BASE_INDISPONIBLE")

    lignes_brutes = donnees.get("rows") or donnees.get("results") or []
    q_normalise = q.strip().lower()

    lignes = []
    for ligne in lignes_brutes:
        if not isinstance(ligne, dict):
            continue
        # Le nom de la colonne titre varie d'une base à l'autre : on prend la
        # première valeur texte non vide plutôt que de deviner un nom fixe.
        titre = next((str(v) for v in ligne.values() if isinstance(v, str) and v.strip()), "(sans titre)")
        url_ligne = ligne.get("url") or ligne.get("Url") or ligne.get("URL")
        if q_normalise and not any(q_normalise in str(v).lower() for v in ligne.values() if v is not None):
            continue
        lignes.append({"titre": titre, "url": url_ligne, "proprietes": ligne})

    return {"lignes": lignes}


class CreationPageNotion(BaseModel):
    titre: str
    contenu: str = ""


@router.post("/pages")
def creer_page_notion(payload: CreationPageNotion, utilisateur=Depends(utilisateur_courant)):
    """
    Crée une page au niveau racine de l'espace Notion de la personne (titre et
    contenu seulement, pas de choix de parent). Elle la range ensuite elle-même.
    """
    if not payload.titre.strip():
        raise erreur_api(400, "TITRE_REQUIS")

    entetes = _entetes_ou_erreur(utilisateur.id)

    try:
        brut = asyncio.run(
            _appeler_outil_async(
                URL_MCP_NOTION,
                "notion-create-pages",
                {"pages": [{"properties": {"title": payload.titre}, "content": payload.contenu}]},
                headers=entetes,
            )
        )
        donnees = json.loads(brut)
    except Exception as e:
        logging.error(f"ERREUR CREATION PAGE NOTION (MCP) : {e}")
        raise erreur_api(502, "NOTION_CREATION_INDISPONIBLE")

    pages_creees = donnees.get("pages") or donnees.get("results") or []
    url_page = pages_creees[0].get("url") if pages_creees else None
    if not url_page:
        raise erreur_api(502, "NOTION_CREATION_INDISPONIBLE")

    return {"url": url_page}
