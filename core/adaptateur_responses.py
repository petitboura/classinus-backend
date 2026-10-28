"""
Adaptateur GPT (OpenAI), Grok (xAI) et Meta pour la boucle d'agent (20/10/2026, Meta le 28/10/2026 sur staging en Bientôt).

Les trois fournisseurs parlent l'API Responses (POST /v1/responses), avec le même SDK openai :
seule l'adresse change pour xAI et Meta. Pourquoi Responses et pas Chat Completions :
- GPT-6 : OpenAI indique que les appels d'outils passent par Responses (voir le diagnostic du
  20/10/2026, sources secondaires, à confirmer au premier test réel).
- Grok : xAI déclare Chat Completions obsolète pour ses modèles à raisonnement, car il ne sait
  pas rendre le raisonnement chiffré du tour précédent ; chaque tour d'outil l'oublierait.
- Meta : même API Responses (https://api.meta.ai/v1). Identifiants standards seulement,
  jamais "-contributor" : ces variantes entraîneraient les modèles Meta avec les données
  reçues, et les échanges des élèves ne doivent pas servir à entraîner des modèles.

Le raisonnement est renvoyé au modèle à chaque tour d'outil (éléments reasoning rangés dans
fournisseur_etat, voir core/adaptateur_commun.py). OpenAI et Meta sont appelés sans stockage (store=false) :
les échanges des élèves ne restent pas chez le fournisseur.
"""

import json
import logging

from openai import BadRequestError, OpenAI

try:
    from adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, ClientCompatible, Flux,
        fragment_appel, morceau, texte_du_contenu, verifier_reponse_non_vide,
    )
except ImportError:
    from core.adaptateur_commun import (
        CLE_ETAT_FOURNISSEUR, DELAI_APPEL_FOURNISSEUR_SECONDES, ClientCompatible, Flux,
        fragment_appel, morceau, texte_du_contenu, verifier_reponse_non_vide,
    )

ADRESSE_XAI = "https://api.x.ai/v1"
ADRESSE_META = "https://api.meta.ai/v1"

TYPES_ELEMENTS_A_REJOUER = ("reasoning", "function_call")


def _convertir_outils(outils):
    """Outils au format Chat Completions vers le format Responses (à plat)."""
    convertis = []
    for outil in outils or []:
        fonction = outil.get("function") or {}
        convertis.append({
            "type": "function",
            "name": fonction.get("name"),
            "description": fonction.get("description") or "",
            "parameters": fonction.get("parameters") or {"type": "object", "properties": {}},
            "strict": False,
        })
    return convertis


def _convertir_messages(messages, rejouer_raisonnement_sans_chiffrement):
    """
    Messages de la boucle vers (instructions, éléments d'entrée) de l'API Responses.

    Le premier message système devient les instructions ; les consignes système ajoutées en
    cours de route (rattrapage, répétition) restent des messages système dans l'entrée.
    """
    instructions = None
    entree = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            texte = texte_du_contenu(message.get("content"))
            if instructions is None and not entree:
                instructions = texte
            elif texte:
                entree.append({"role": "system", "content": texte})
        elif role == "user":
            entree.append({"role": "user", "content": texte_du_contenu(message.get("content"))})
        elif role == "assistant":
            texte = texte_du_contenu(message.get("content"))
            if texte:
                entree.append({"role": "assistant", "content": texte})
            appels = message.get("tool_calls") or []
            etat = message.get(CLE_ETAT_FOURNISSEUR) or {}
            elements = etat.get("elements") or []
            if appels and elements:
                for element in elements:
                    if element.get("type") == "reasoning" and not (
                        element.get("encrypted_content") or rejouer_raisonnement_sans_chiffrement
                    ):
                        continue
                    entree.append(element)
            else:
                for appel in appels:
                    fonction = appel.get("function") or {}
                    entree.append({
                        "type": "function_call",
                        "call_id": appel.get("id"),
                        "name": fonction.get("name"),
                        "arguments": fonction.get("arguments") or "{}",
                    })
        elif role == "tool":
            entree.append({
                "type": "function_call_output",
                "call_id": message.get("tool_call_id"),
                "output": texte_du_contenu(message.get("content")) or "Aucun résultat.",
            })
    return instructions, entree


def _en_dict(element):
    if hasattr(element, "model_dump"):
        return element.model_dump(exclude_none=True)
    return dict(element)


class ClientResponses(ClientCompatible):
    """
    `fournisseur` : "openai", "xai" ou "meta". Les différences entre eux sont isolées ici :
    adresse, stockage et chiffrement du raisonnement, résumé du raisonnement.
    """

    def __init__(self, cle_api, fournisseur):
        super().__init__()
        self.fournisseur = fournisseur
        if fournisseur == "xai":
            adresse = ADRESSE_XAI
        elif fournisseur == "meta":
            adresse = ADRESSE_META
        else:
            adresse = None
        self._client = OpenAI(
            api_key=cle_api, base_url=adresse, timeout=DELAI_APPEL_FOURNISSEUR_SECONDES, max_retries=1,
        )

    def _arguments_requete(self, modele, instructions, entree, outils, effort, avec_resume):
        arguments = {"model": modele, "input": entree, "stream": True}
        if instructions:
            arguments["instructions"] = instructions
        if outils:
            arguments["tools"] = outils
        raisonnement = {}
        if effort:
            raisonnement["effort"] = effort
        if self.fournisseur in ("openai", "meta"):
            # Sans stockage chez le fournisseur, le raisonnement ne se retrouve qu'en le demandant
            # chiffré, pour le renvoyer au tour suivant.
            arguments["store"] = False
            arguments["include"] = ["reasoning.encrypted_content"]
            if avec_resume:
                raisonnement["summary"] = "auto"
        if raisonnement:
            arguments["reasoning"] = raisonnement
        return arguments

    def _ouvrir(self, modele, instructions, entree, outils, effort):
        """
        Ouvre le flux. Le résumé du raisonnement est refusé par OpenAI aux organisations non
        vérifiées : dans ce cas on rouvre sans résumé plutôt que de faire échouer le message.
        """
        # Résumé du raisonnement : OpenAI seulement (Meta ne le propose pas, à confirmer au test réel).
        avec_resume = self.fournisseur == "openai"
        try:
            return self._client.responses.create(
                **self._arguments_requete(modele, instructions, entree, outils, effort, avec_resume)
            )
        except BadRequestError as erreur:
            texte = str(erreur).lower()
            if avec_resume and ("summary" in texte or "verif" in texte):
                logging.warning(f"Résumé du raisonnement refusé par OpenAI, nouvel essai sans résumé : {erreur}")
                return self._client.responses.create(
                    **self._arguments_requete(modele, instructions, entree, outils, effort, False)
                )
            raise

    def create(self, *, model, messages, tools=None, reasoning_effort=None, **_ignores):
        # max_completion_tokens, timeout et stream de la boucle sont volontairement ignorés :
        # la réserve de 4096 jetons de la cascade tronquerait un modèle qui réfléchit, et le
        # délai de 10 s est trop court (voir core/adaptateur_commun.py).
        # Meta, comme xAI : seul le raisonnement chiffré est rejoué entre les tours d'outils.
        instructions, entree = _convertir_messages(
            messages, rejouer_raisonnement_sans_chiffrement=(self.fournisseur == "openai")
        )
        flux_api = self._ouvrir(model, instructions, entree, _convertir_outils(tools), reasoning_effort)
        self._etat_dernier_tour = None
        return Flux(self._lire(flux_api))

    def _lire(self, flux_api):
        elements = []
        index_par_element = {}
        arguments_diffuses = set()
        nombre_appels = 0
        fin = "stop"
        a_repondu = False
        try:
            for evenement in flux_api:
                type_evenement = getattr(evenement, "type", "")
                if type_evenement == "response.output_text.delta":
                    if evenement.delta:
                        a_repondu = True
                        yield morceau(contenu=evenement.delta)
                elif type_evenement in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
                    if evenement.delta:
                        yield morceau(raisonnement=evenement.delta)
                elif type_evenement == "response.output_item.added":
                    element = evenement.item
                    if getattr(element, "type", "") == "function_call":
                        a_repondu = True
                        index_par_element[element.id] = nombre_appels
                        yield morceau(appels=[fragment_appel(nombre_appels, element.call_id, element.name, "")])
                        nombre_appels += 1
                elif type_evenement == "response.function_call_arguments.delta":
                    index = index_par_element.get(evenement.item_id)
                    if index is not None and evenement.delta:
                        arguments_diffuses.add(evenement.item_id)
                        yield morceau(appels=[fragment_appel(index, arguments=evenement.delta)])
                elif type_evenement == "response.output_item.done":
                    element = evenement.item
                    type_element = getattr(element, "type", "")
                    if type_element in TYPES_ELEMENTS_A_REJOUER:
                        elements.append(_en_dict(element))
                    if type_element == "function_call" and element.id not in arguments_diffuses:
                        index = index_par_element.get(element.id)
                        if index is not None and element.arguments:
                            yield morceau(appels=[fragment_appel(index, arguments=element.arguments)])
                elif type_evenement == "response.incomplete":
                    fin = "length"
                elif type_evenement in ("response.failed", "error"):
                    raise RuntimeError(_message_erreur(evenement))
        finally:
            if hasattr(flux_api, "close"):
                try:
                    flux_api.close()
                except Exception:
                    pass
        verifier_reponse_non_vide(a_repondu, {"openai": "OpenAI", "xai": "xAI", "meta": "Meta"}.get(self.fournisseur, self.fournisseur), fin)
        if nombre_appels:
            fin = "tool_calls"
            self._etat_dernier_tour = {"elements": elements}
        yield morceau(fin=fin)


def _message_erreur(evenement):
    reponse = getattr(evenement, "response", None)
    erreur = getattr(reponse, "error", None) if reponse is not None else None
    if erreur is not None:
        return f"{getattr(erreur, 'code', '')} {getattr(erreur, 'message', '')}".strip()
    return str(getattr(evenement, "message", None) or json.dumps(_en_dict(evenement), default=str)[:300])
