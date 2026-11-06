"""Controle en lecture seule : les presets Marketing Studio de notre catalogue
existent-ils dans l'API Higgsfield ?

Notre catalogue (649 presets, copie dans presets_marketing_studio_ids.json) vient
du MCP Higgsfield. L'API directe expose sa propre liste de presets image
(GET /marketing-studio/image/presets). Ce module compare les deux listes pour
savoir si un preset_id de notre catalogue est accepte par l'API, avant de
brancher la generation. Il ne genere rien et ne depense aucun credit.
Il ne renvoie jamais la cle API.
"""
import json
import logging
import os
import time
from collections import Counter

import requests

from core.generation_video_higgsfield import BASE_URL, DELAI_SECONDES, _entetes
from core.higgsfield_requetes import ErreurHiggsfield

_FICHIER_IDS = os.path.join(os.path.dirname(__file__), "presets_marketing_studio_ids.json")
_PAGE = 100
_PAGES_MAX = 30
# Le resultat est garde quelques minutes : la route est publique et appelle Higgsfield avec la cle partagee.
_DUREE_CACHE = 300
_cache = {"a": 0.0, "valeur": None}


def _nos_presets() -> list[dict]:
    with open(_FICHIER_IDS, encoding="utf-8") as f:
        return json.load(f)


def _lister_presets_api() -> list[dict]:
    presets = []
    curseur = 0
    for _ in range(_PAGES_MAX):
        try:
            reponse = requests.get(
                f"{BASE_URL}/marketing-studio/image/presets",
                headers=_entetes(),
                params={"size": _PAGE, "cursor": curseur},
                timeout=DELAI_SECONDES,
            )
        except requests.RequestException as e:
            raise ErreurHiggsfield(f"Higgsfield ne repond pas ({e.__class__.__name__}).")
        if reponse.status_code != 200:
            raise ErreurHiggsfield(f"Higgsfield a refuse la liste des presets (code {reponse.status_code}).")
        corps = reponse.json() or {}
        presets.extend(corps.get("items") or [])
        curseur = corps.get("cursor")
        if curseur is None:
            return presets
    return presets


def controler_presets() -> dict:
    maintenant = time.time()
    if _cache["valeur"] is not None and maintenant - _cache["a"] < _DUREE_CACHE:
        return _cache["valeur"]

    nos = _nos_presets()
    api = _lister_presets_api()
    ids_api = {str(p.get("id")) for p in api if p.get("id")}
    ids_nos = [p["id"] for p in nos]
    trouves = [i for i in ids_nos if i in ids_api]
    par_type_nos = Counter(p["type"] for p in nos)
    trouves_par_type = Counter(p["type"] for p in nos if p["id"] in ids_api)

    resultat = {
        "presets_api": len(api),
        "presets_classinus": len(ids_nos),
        "presets_classinus_trouves_dans_api": len(trouves),
        "trouves_par_categorie": {t: {"trouves": trouves_par_type.get(t, 0), "sur": n} for t, n in par_type_nos.items()},
        "types_api": dict(Counter(str(p.get("type")) for p in api)),
        "groupes_api": dict(Counter(str((p.get("metadata") or {}).get("group_name")) for p in api).most_common(15)),
        "exemples_api": [
            {"id": p.get("id"), "nom": p.get("name"), "type": p.get("type")} for p in api[:3]
        ],
        "exemples_classinus_absents_de_api": [i for i in ids_nos if i not in ids_api][:3],
    }
    logging.info("CONTROLE PRESETS MARKETING STUDIO : %s", json.dumps(resultat, ensure_ascii=False))
    _cache["a"] = maintenant
    _cache["valeur"] = resultat
    return resultat
