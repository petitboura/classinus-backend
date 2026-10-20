"""
Adaptateur Gemini (Google) pour la boucle d'agent (20/10/2026).

API native generateContent en streaming (SDK google-genai, déjà utilisé ailleurs dans le
projet), pas la couche de compatibilité OpenAI : d'après la documentation, sur celle-ci le
réglage d'effort a peu d'effet visible. Réflexion : thinking_level low, medium ou high (voir
core/efforts_modeles.py). Gemini 3 et 4 réfléchissent toujours, il n'y a pas de « aucun ».

Les modèles Gemini 3 et 4 attachent des signatures de pensée à leurs parties et exigent de les
recevoir à l'identique avec les résultats d'outils : les parties du tour sont rangées telles
quelles dans fournisseur_etat (voir core/adaptateur_commun.py).
"""

import json

from google import genai
from google.genai import types

try:
    from adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, noms_des_appels, texte_du_contenu,
    )
except ImportError:
    from core.adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, TEXTE_RESULTAT_VIDE, ClientCompatible, Flux,
        arguments_en_dict, fragment_appel, morceau, noms_des_appels, texte_du_contenu,
    )

NIVEAUX_REFLEXION = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}

FINS_GEMINI = {"STOP": "stop", "MAX_TOKENS": "length"}


def _convertir_outils(outils):
    declarations = []
    for outil in outils or []:
        fonction = outil.get("function") or {}
        declarations.append(types.FunctionDeclaration(
            name=fonction.get("name"),
            description=fonction.get("description") or "",
            parameters_json_schema=fonction.get("parameters") or {"type": "object", "properties": {}},
        ))
    return [types.Tool(function_declarations=declarations)] if declarations else None


def _convertir_messages(messages):
    """
    Messages de la boucle vers (consigne système, contenus Gemini).

    Les résultats d'un même lot d'appels doivent arriver ensemble dans un seul message
    utilisateur, avant tout texte : ils sont donc rassemblés puis vidés au prochain message
    assistant.
    """
    noms = noms_des_appels(messages)
    systeme = None
    contenus = []
    resultats_en_attente = []
    textes_en_attente = []

    def vider():
        parties = resultats_en_attente + textes_en_attente
        if parties:
            contenus.append(types.Content(role="user", parts=list(parties)))
        resultats_en_attente.clear()
        textes_en_attente.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            texte = texte_du_contenu(message.get("content"))
            if systeme is None and not contenus and not textes_en_attente:
                systeme = texte
            elif texte:
                textes_en_attente.append(types.Part(text=f"[Consigne du système] {texte}"))
        elif role == "user":
            texte = texte_du_contenu(message.get("content"))
            if texte:
                textes_en_attente.append(types.Part(text=texte))
        elif role == "tool":
            identifiant = message.get("tool_call_id")
            resultats_en_attente.append(types.Part(function_response=types.FunctionResponse(
                id=identifiant,
                name=noms.get(identifiant) or "outil",
                response={"result": texte_du_contenu(message.get("content")) or TEXTE_RESULTAT_VIDE},
            )))
        elif role == "assistant":
            vider()
            etat = message.get(CLE_ETAT_FOURNISSEUR) or {}
            if message.get("tool_calls") and etat.get("parties"):
                parties = [types.Part.model_validate(partie) for partie in etat["parties"]]
            else:
                parties = []
                texte = texte_du_contenu(message.get("content"))
                if texte:
                    parties.append(types.Part(text=texte))
                for appel in message.get("tool_calls") or []:
                    fonction = appel.get("function") or {}
                    parties.append(types.Part(function_call=types.FunctionCall(
                        id=appel.get("id"),
                        name=fonction.get("name"),
                        args=arguments_en_dict(fonction.get("arguments")),
                    )))
            if parties:
                contenus.append(types.Content(role="model", parts=parties))
    vider()
    return systeme, contenus


class ClientGemini(ClientCompatible):
    def __init__(self, cle_api):
        super().__init__()
        self._client = genai.Client(
            api_key=cle_api,
            http_options=types.HttpOptions(timeout=DELAI_APPEL_FOURNISSEUR_SECONDES * 1000),
        )

    def create(self, *, model, messages, tools=None, reasoning_effort=None, **_ignores):
        systeme, contenus = _convertir_messages(messages)
        reflexion = {"include_thoughts": True}
        if reasoning_effort in NIVEAUX_REFLEXION:
            reflexion["thinking_level"] = NIVEAUX_REFLEXION[reasoning_effort]
        configuration = types.GenerateContentConfig(
            system_instruction=systeme or None,
            tools=_convertir_outils(tools),
            thinking_config=types.ThinkingConfig(**reflexion),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self._etat_dernier_tour = None
        return Flux(self._lire(model, contenus, configuration))

    def _lire(self, modele, contenus, configuration):
        parties_du_tour = []
        nombre_appels = 0
        fin = "stop"
        flux_api = self._client.models.generate_content_stream(
            model=modele, contents=contenus, config=configuration
        )
        for reponse in flux_api:
            candidats = reponse.candidates or []
            if not candidats:
                raison = getattr(getattr(reponse, "prompt_feedback", None), "block_reason", None)
                if raison:
                    raise RuntimeError(f"Requête bloquée par Gemini : {raison}")
                continue
            candidat = candidats[0]
            if candidat.finish_reason is not None:
                nom_fin = getattr(candidat.finish_reason, "name", str(candidat.finish_reason))
                fin = FINS_GEMINI.get(nom_fin, nom_fin.lower())
            for partie in (candidat.content.parts if candidat.content and candidat.content.parts else []):
                appel = partie.function_call
                if appel is not None:
                    identifiant = appel.id or f"appel_gemini_{nombre_appels}"
                    appel.id = identifiant
                    parties_du_tour.append(partie)
                    yield morceau(appels=[fragment_appel(
                        nombre_appels, identifiant, appel.name, json.dumps(appel.args or {}, ensure_ascii=False),
                    )])
                    nombre_appels += 1
                    continue
                parties_du_tour.append(partie)
                if partie.text:
                    if partie.thought:
                        yield morceau(raisonnement=partie.text)
                    else:
                        yield morceau(contenu=partie.text)
        if nombre_appels:
            fin = "tool_calls"
            self._etat_dernier_tour = {
                "parties": [p.model_dump(mode="json", exclude_none=True) for p in parties_du_tour],
            }
        yield morceau(fin=fin)
