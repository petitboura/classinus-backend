"""
Adaptateur Claude (Anthropic) pour la boucle d'agent (20/10/2026).

API Messages en streaming, avec les outils natifs de Claude. Réflexion : Claude 5.5 réfléchit
en mode adaptatif, et l'intensité se règle avec output_config.effort (low, medium, high,
xhigh, max, selon le modèle, voir core/efforts_modeles.py). Il n'existe pas de « aucun » : la
réflexion adaptative ne se coupe pas sur ces modèles, donc l'effort « aucun » n'est jamais
proposé pour Claude.

Les blocs de réflexion renvoyés par Claude sont signés et doivent revenir à l'identique avec
les résultats d'outils : ils sont rangés dans fournisseur_etat (voir core/adaptateur_commun.py).
"""

import os

from anthropic import Anthropic

try:
    from adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, texte_du_contenu, verifier_reponse_non_vide,
    )
except ImportError:
    from core.adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, texte_du_contenu, verifier_reponse_non_vide,
    )

# max_tokens est obligatoire chez Anthropic et compte aussi la réflexion : assez large pour
# qu'un effort élevé ne coupe pas la réponse.
MAX_TOKENS_SORTIE_CLAUDE = 16000

FINS_CLAUDE = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length"}


def _convertir_outils(outils):
    convertis = []
    for outil in outils or []:
        fonction = outil.get("function") or {}
        convertis.append({
            "name": fonction.get("name"),
            "description": fonction.get("description") or "",
            "input_schema": fonction.get("parameters") or {"type": "object", "properties": {}},
        })
    return convertis


def _convertir_messages(messages):
    """
    Messages de la boucle vers (système, messages Anthropic).

    Anthropic n'a pas de rôle système dans les messages : le premier message système devient le
    paramètre system, les consignes ajoutées en cours de route deviennent du texte côté
    utilisateur. Les résultats d'outils reviennent dans un message utilisateur, avant tout texte.

    Renvoie aussi l'indice du dernier message de l'HISTORIQUE (juste avant la première consigne
    système ajoutée en cours de route, voir core/main.py : la partie variable du prompt vient
    après l'historique), ou None. C'est là que le cache se pose pour que l'historique soit relu
    d'un message à l'autre au lieu d'être refacturé.
    """
    systeme = None
    fin_historique = None
    converti = []
    resultats_en_attente = []
    textes_en_attente = []

    def vider():
        contenu = resultats_en_attente + textes_en_attente
        if contenu:
            converti.append({"role": "user", "content": list(contenu)})
        resultats_en_attente.clear()
        textes_en_attente.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            texte = texte_du_contenu(message.get("content"))
            if systeme is None and not converti and not textes_en_attente:
                systeme = texte
            elif texte:
                if fin_historique is None and converti:
                    fin_historique = len(converti) - 1
                textes_en_attente.append({"type": "text", "text": f"[Consigne du système] {texte}"})
        elif role == "user":
            texte = texte_du_contenu(message.get("content"))
            if texte:
                textes_en_attente.append({"type": "text", "text": texte})
        elif role == "tool":
            resultats_en_attente.append({
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id"),
                "content": texte_du_contenu(message.get("content")) or TEXTE_RESULTAT_VIDE,
            })
        elif role == "assistant":
            vider()
            blocs = []
            etat = message.get(CLE_ETAT_FOURNISSEUR) or {}
            if message.get("tool_calls") and etat.get("blocs"):
                blocs = list(etat["blocs"])
            else:
                texte = texte_du_contenu(message.get("content"))
                if texte:
                    blocs.append({"type": "text", "text": texte})
                for appel in message.get("tool_calls") or []:
                    fonction = appel.get("function") or {}
                    blocs.append({
                        "type": "tool_use",
                        "id": appel.get("id"),
                        "name": fonction.get("name"),
                        "input": arguments_en_dict(fonction.get("arguments")),
                    })
            if blocs:
                converti.append({"role": "assistant", "content": blocs})
    vider()
    return systeme, converti, fin_historique


# Cache de prompt (07/11/2026, demande Bourama : l'entrée coûtait beaucoup trop cher).
# Chez Anthropic le cache couvre tout ce qui précède un marqueur, dans l'ordre outils, puis
# système, puis messages. Relu, ce début est facturé environ 10 % du prix normal ; l'écrire coûte
# un peu plus que le prix normal, une fois.
#   CLAUDE_CACHE_PROMPT : "0" coupe tout le cache (par défaut actif).
#   CLAUDE_CACHE_TTL    : "5m" (défaut) ou "1h" (écriture plus chère, utile si les tours sont espacés).
TYPES_BLOCS_AVEC_CACHE = {"text", "tool_use", "tool_result"}


def _cache_actif():
    return os.getenv("CLAUDE_CACHE_PROMPT", "1").strip() != "0"


def _controle_cache():
    controle = {"type": "ephemeral"}
    if os.getenv("CLAUDE_CACHE_TTL", "5m").strip() == "1h":
        controle["ttl"] = "1h"
    return controle


def _marquer_dernier_bloc(message):
    """
    Pose le marqueur de cache sur le dernier bloc du message, dans une COPIE du bloc : ces blocs
    viennent de fournisseur_etat, qui voyage avec messages_agent et ne doit jamais être modifié.
    Sans effet si le dernier bloc n'accepte pas de marqueur (blocs de réflexion).
    """
    contenu = message.get("content")
    if not isinstance(contenu, list) or not contenu:
        return
    dernier = contenu[-1]
    if not isinstance(dernier, dict) or dernier.get("type") not in TYPES_BLOCS_AVEC_CACHE:
        return
    contenu[-1] = {**dernier, "cache_control": _controle_cache()}


def poser_points_de_cache(arguments, fin_historique):
    """
    Pose au plus 4 marqueurs (le maximum d'Anthropic) sur la requête :
    1. le dernier outil : le cache des outils survit à un changement du prompt système ;
    2. le prompt système, qui couvre aussi les outils ;
    3. la fin de l'historique : la conversation passée est relue au tour suivant ;
    4. le dernier message : chaque étape d'outil relit tout ce qui précède et n'ajoute que le nouveau.
    """
    if not _cache_actif():
        return arguments
    outils = arguments.get("tools")
    if outils:
        outils[-1] = {**outils[-1], "cache_control": _controle_cache()}
    systeme = arguments.get("system")
    if isinstance(systeme, str) and systeme:
        arguments["system"] = [{"type": "text", "text": systeme, "cache_control": _controle_cache()}]
    messages = arguments.get("messages") or []
    if fin_historique is not None and 0 <= fin_historique < len(messages) - 1:
        # Copie du message : le contenu converti est reconstruit à chaque appel, mais on évite de
        # partager la liste avec une autre structure.
        messages[fin_historique] = {**messages[fin_historique], "content": list(messages[fin_historique].get("content") or [])}
        _marquer_dernier_bloc(messages[fin_historique])
    if messages:
        messages[-1] = {**messages[-1], "content": list(messages[-1].get("content") or [])}
        _marquer_dernier_bloc(messages[-1])
    return arguments


class ClientClaude(ClientCompatible):
    def __init__(self, cle_api):
        super().__init__()
        self._client = Anthropic(api_key=cle_api, timeout=DELAI_APPEL_FOURNISSEUR_SECONDES, max_retries=1)

    def create(self, *, model, messages, tools=None, reasoning_effort=None, **_ignores):
        systeme, converti, fin_historique = _convertir_messages(messages)
        arguments = {
            "model": model,
            "max_tokens": MAX_TOKENS_SORTIE_CLAUDE,
            "messages": converti,
            # Le résumé de la réflexion est demandé pour l'afficher à l'écran, comme celle de
            # DeepSeek ; sans lui, Claude 5.5 ne renvoie que la signature.
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        if systeme:
            arguments["system"] = systeme
        if tools:
            arguments["tools"] = _convertir_outils(tools)
        if reasoning_effort:
            # Par extra_body : fonctionne quelle que soit la version du SDK installée.
            arguments["extra_body"] = {"output_config": {"effort": reasoning_effort}}
        poser_points_de_cache(arguments, fin_historique)
        self._etat_dernier_tour = None
        return Flux(self._lire(arguments))

    def _lire(self, arguments):
        index_outil_par_bloc = {}
        nombre_appels = 0
        a_repondu = False
        with self._client.messages.stream(**arguments) as flux_api:
            for evenement in flux_api:
                type_evenement = getattr(evenement, "type", "")
                if type_evenement == "content_block_start":
                    bloc = evenement.content_block
                    if getattr(bloc, "type", "") == "tool_use":
                        a_repondu = True
                        index_outil_par_bloc[evenement.index] = nombre_appels
                        yield morceau(appels=[fragment_appel(nombre_appels, bloc.id, bloc.name, "")])
                        nombre_appels += 1
                elif type_evenement == "content_block_delta":
                    delta = evenement.delta
                    type_delta = getattr(delta, "type", "")
                    if type_delta == "text_delta" and delta.text:
                        a_repondu = True
                        yield morceau(contenu=delta.text)
                    elif type_delta == "thinking_delta" and delta.thinking:
                        yield morceau(raisonnement=delta.thinking)
                    elif type_delta == "input_json_delta" and delta.partial_json:
                        index = index_outil_par_bloc.get(evenement.index)
                        if index is not None:
                            yield morceau(appels=[fragment_appel(index, arguments=delta.partial_json)])
            final = flux_api.get_final_message()
        verifier_reponse_non_vide(a_repondu, "Claude", final.stop_reason)
        if nombre_appels:
            self._etat_dernier_tour = {
                "blocs": [bloc.model_dump(exclude_none=True) for bloc in final.content],
            }
        yield morceau(fin=FINS_CLAUDE.get(final.stop_reason, final.stop_reason or "stop"), usage=getattr(final, "usage", None))
