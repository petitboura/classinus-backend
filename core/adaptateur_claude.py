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

from anthropic import Anthropic

try:
    from adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, texte_du_contenu,
    )
except ImportError:
    from core.adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, texte_du_contenu,
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
    """
    systeme = None
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
    return systeme, converti


class ClientClaude(ClientCompatible):
    def __init__(self, cle_api):
        super().__init__()
        self._client = Anthropic(api_key=cle_api, timeout=DELAI_APPEL_FOURNISSEUR_SECONDES, max_retries=1)

    def create(self, *, model, messages, tools=None, reasoning_effort=None, **_ignores):
        systeme, converti = _convertir_messages(messages)
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
        self._etat_dernier_tour = None
        return Flux(self._lire(arguments))

    def _lire(self, arguments):
        index_outil_par_bloc = {}
        nombre_appels = 0
        with self._client.messages.stream(**arguments) as flux_api:
            for evenement in flux_api:
                type_evenement = getattr(evenement, "type", "")
                if type_evenement == "content_block_start":
                    bloc = evenement.content_block
                    if getattr(bloc, "type", "") == "tool_use":
                        index_outil_par_bloc[evenement.index] = nombre_appels
                        yield morceau(appels=[fragment_appel(nombre_appels, bloc.id, bloc.name, "")])
                        nombre_appels += 1
                elif type_evenement == "content_block_delta":
                    delta = evenement.delta
                    type_delta = getattr(delta, "type", "")
                    if type_delta == "text_delta" and delta.text:
                        yield morceau(contenu=delta.text)
                    elif type_delta == "thinking_delta" and delta.thinking:
                        yield morceau(raisonnement=delta.thinking)
                    elif type_delta == "input_json_delta" and delta.partial_json:
                        index = index_outil_par_bloc.get(evenement.index)
                        if index is not None:
                            yield morceau(appels=[fragment_appel(index, arguments=delta.partial_json)])
            final = flux_api.get_final_message()
        if nombre_appels:
            self._etat_dernier_tour = {
                "blocs": [bloc.model_dump(exclude_none=True) for bloc in final.content],
            }
        yield morceau(fin=FINS_CLAUDE.get(final.stop_reason, final.stop_reason or "stop"))
