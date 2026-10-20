"""
Briques communes des adaptateurs de fournisseurs (20/10/2026).

La boucle d'agent (core/boucle_agent.py:_agent_groq) parle le format Chat Completions : elle
appelle client.chat.completions.create(...) et lit des morceaux de la forme
chunk.choices[0].delta (content, tool_calls, reasoning) et chunk.choices[0].finish_reason.
Plutôt que de réécrire cette boucle (outils, confirmations, arrêt, répétitions, timeline) pour
chaque fournisseur, chaque adaptateur reçoit les mêmes arguments, appelle l'API native du
fournisseur (Responses pour GPT et Grok, Messages pour Claude, generateContent pour Gemini) et
renvoie des morceaux dans ce format. La boucle ne voit aucune différence.

Deux points communs à tous les adaptateurs :
- Les messages de la boucle sont au format OpenAI : system, user, assistant (avec tool_calls),
  tool (avec tool_call_id). Chaque adaptateur les convertit vers son format.
- Ce que le fournisseur doit revoir à l'identique au tour suivant (blocs de réflexion signés de
  Claude, éléments de raisonnement de GPT et Grok, signatures de pensée de Gemini) est rangé
  par l'adaptateur dans le message assistant lui-même, sous la clé "fournisseur_etat" (voir
  etat_dernier_tour). Il voyage donc avec messages_agent, y compris quand le tour est repris
  après une confirmation ou une limite d'outils (l'état de reprise passe par le frontend).
"""

import json
import types

# Délai par appel pour les modèles Claude, GPT, Gemini et Grok. Le délai court de la cascade
# (DELAI_MAX_PAR_APPEL, 10 s, voir core/constantes_agent.py) sert à basculer vite d'un modèle
# gratuit à l'autre ; ici il n'y a pas de modèle de secours, et un modèle qui réfléchit peut
# mettre bien plus de 10 s avant son premier mot.
DELAI_APPEL_FOURNISSEUR_SECONDES = 180

CLE_ETAT_FOURNISSEUR = "fournisseur_etat"

TEXTE_RESULTAT_VIDE = "Aucun résultat."


def morceau(contenu=None, appels=None, raisonnement=None, fin=None):
    """Un morceau de flux au format que lit la boucle d'agent."""
    delta = types.SimpleNamespace(
        content=contenu,
        tool_calls=appels,
        reasoning=raisonnement,
        reasoning_content=None,
    )
    choix = types.SimpleNamespace(delta=delta, finish_reason=fin)
    return types.SimpleNamespace(choices=[choix], usage=None)


def fragment_appel(index, identifiant=None, nom=None, arguments=None):
    """Un fragment d'appel d'outil : la boucle recolle id, nom et arguments morceau par morceau."""
    return types.SimpleNamespace(
        index=index,
        id=identifiant,
        function=types.SimpleNamespace(name=nom, arguments=arguments),
    )


def texte_du_contenu(contenu):
    """Texte d'un champ content, qui est une chaîne ou une liste de parties {"type": "text"}."""
    if contenu is None:
        return ""
    if isinstance(contenu, str):
        return contenu
    morceaux = []
    for partie in contenu:
        if isinstance(partie, dict) and partie.get("type") == "text":
            morceaux.append(partie.get("text") or "")
        elif isinstance(partie, str):
            morceaux.append(partie)
    return "\n".join(m for m in morceaux if m)


def arguments_en_dict(arguments):
    """Arguments d'un appel d'outil (chaîne JSON) en dictionnaire ; {} si vide ou illisible."""
    if isinstance(arguments, dict):
        return arguments
    try:
        valeur = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return {}
    return valeur if isinstance(valeur, dict) else {}


def noms_des_appels(messages):
    """Associe chaque identifiant d'appel d'outil à son nom, d'après les messages assistant."""
    noms = {}
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "assistant":
            for appel in message.get("tool_calls") or []:
                fonction = appel.get("function") or {}
                noms[appel.get("id")] = fonction.get("name") or ""
    return noms


def verifier_reponse_non_vide(a_repondu, fournisseur, fin):
    """
    Une réponse sans aucun mot ni appel d'outil (refus du fournisseur, coupure pendant la
    réflexion) ferait un message blanc sans trace : on la remonte comme une erreur, que le
    chat traite comme les autres (message d'erreur et journal avec la raison de fin).
    """
    if not a_repondu:
        raise RuntimeError(f"Réponse vide de {fournisseur} (fin : {fin})")


class Flux:
    """
    Flux de morceaux, avec close() : la boucle d'agent le ferme dès que la personne clique sur
    Arrêter (voir le jeton d'arrêt dans core/arret_tour.py). Fermer le générateur ferme aussi
    la connexion ouverte chez le fournisseur.
    """

    def __init__(self, generateur):
        self._generateur = generateur

    def __iter__(self):
        return self._generateur

    def close(self):
        try:
            self._generateur.close()
        except Exception:
            pass


class ClientCompatible:
    """
    Base des adaptateurs : expose client.chat.completions.create(...) comme le SDK OpenAI, et
    etat_dernier_tour() pour que la boucle range l'état du fournisseur dans le message assistant.
    """

    def __init__(self):
        self.chat = types.SimpleNamespace(completions=self)
        self._etat_dernier_tour = None

    def create(self, **arguments):
        raise NotImplementedError

    def etat_dernier_tour(self):
        """État à garder avec l'appel d'outil du dernier tour (dict JSON), ou None."""
        return self._etat_dernier_tour
