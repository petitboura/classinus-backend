"""
Adaptateur Baseten pour DeepSeek (29/10/2026, demande Bourama).

C'est le MEME DeepSeek qu'avant, vu par l'utilisateur : memes modeles dans le
selecteur (deepseek-v4-flash, deepseek-v4-pro), meme reprise de tour, meme
historique. Seule la route change : quand l'interrupteur est ON (colonne
baseten_actif de la ligne deepseek dans Supabase, table fournisseurs_llm),
les appels partent vers Baseten (https://inference.baseten.co/v1, cle
BASETEN_API_KEY) avec le slug du modele ; sinon ils partent en direct chez
DeepSeek comme avant, sans rien changer.

Repli automatique : si Baseten refuse pour une raison de credit, quota ou
cle (401/402/403/429 ou message explicite), l'appel repart aussitot en
direct, sans erreur pour l'utilisateur, et Baseten est mis de cote pour
10 minutes (disjoncteur : evite de retomber sur le refus a chaque message
tant que Bourama n'a pas remis du credit ou eteint l'interrupteur). Passe
ce delai, Baseten est reessaye tout seul.

La boucle d'agent (core/boucle_agent.py) continue d'envoyer l'identifiant
direct, traduit ici en slug Baseten : ni la reprise de tour, ni l'identite,
ni l'historique ne voient le slug. Meme appel que le SDK OpenAI
(client.chat.completions.create), comme les autres adaptateurs (voir
core/adaptateur_commun.py:ClientCompatible).
"""

import logging
import time

from openai import OpenAI

try:
    from adaptateur_commun import ClientCompatible
except ImportError:
    from core.adaptateur_commun import ClientCompatible

BASE_URL_BASETEN = "https://inference.baseten.co/v1"
BASE_URL_DEEPSEEK_DIRECT = "https://api.deepseek.com"

# Delai de mise a l'ecart de Baseten apres un refus de credit/quota/cle.
DELAI_REESSAI_BASETEN_SECONDES = 10 * 60

_baseten_epuise_jusqua = 0


def baseten_circuit_ouvert():
    """True tant que Baseten est mis a l'ecart (refus recent)."""
    return time.time() < _baseten_epuise_jusqua


def noter_baseten_epuise():
    """Met Baseten a l'ecart pour DELAI_REESSAI_BASETEN_SECONDES."""
    global _baseten_epuise_jusqua
    _baseten_epuise_jusqua = time.time() + DELAI_REESSAI_BASETEN_SECONDES


def reinitialiser_circuit_baseten():
    """Remet le disjoncteur a zero (tests)."""
    global _baseten_epuise_jusqua
    _baseten_epuise_jusqua = 0


# Statuts HTTP qui declenchent le repli vers DeepSeek direct : non
# authentifie (cle absente/invalide), paiement requis (credit epuise),
# interdit, quota/limite atteint. Tout autre statut remonte tel quel.
_STATUTS_REPLI_BASETEN = (401, 402, 403, 429)

# Mots d'un message d'erreur qui declenchent le repli meme sans statut
# lisible (SDK ou forme inattendue). En anglais : les API renvoient
# ces erreurs en anglais.
_MOTS_CLE_REPLI_BASETEN = (
    "credit", "quota", "payment", "billing", "insufficient",
    "balance", "funds", "unpaid", "limit exceeded",
)


def est_erreur_repli_baseten(erreur):
    """True si l'erreur Baseten merite le repli vers DeepSeek direct."""
    statut = getattr(erreur, "status_code", None)
    if statut is None:
        reponse = getattr(erreur, "response", None)
        statut = getattr(reponse, "status_code", None)
    try:
        statut = int(statut) if statut is not None else None
    except (TypeError, ValueError):
        statut = None
    if statut in _STATUTS_REPLI_BASETEN:
        return True
    return any(mot in str(erreur).lower() for mot in _MOTS_CLE_REPLI_BASETEN)


class ClientBaseten(ClientCompatible):
    """
    Client DeepSeek routable : Baseten quand c'est possible, direct sinon.

    correspondance_modeles : {identifiant direct: slug Baseten}, lu dans
    Supabase (colonne modele_id_baseten, voir core/fournisseurs_llm.py).
    cle_baseten None = interrupteur OFF ou cle absente : tout part en
    direct. cle_directe None = pas de repli possible (la premiere erreur
    Baseten remonte comme avant).
    """

    def __init__(self, correspondance_modeles, cle_baseten=None, cle_directe=None):
        super().__init__()
        self._correspondance = dict(correspondance_modeles or {})
        self._client_baseten = OpenAI(api_key=cle_baseten, base_url=BASE_URL_BASETEN) if cle_baseten else None
        self._client_direct = OpenAI(api_key=cle_directe, base_url=BASE_URL_DEEPSEEK_DIRECT) if cle_directe else None

    def _slug_pour(self, modele_id):
        if self._client_baseten is None or baseten_circuit_ouvert():
            return None
        return self._correspondance.get(modele_id)

    def create(self, **arguments):
        modele_id = arguments.get("model")
        slug = self._slug_pour(modele_id)
        if slug is not None:
            try:
                reponse = self._client_baseten.chat.completions.create(**{**arguments, "model": slug})
                # Log temporaire (staging) : quelle route a repondu. En
                # warning car le niveau info n'apparait pas dans les logs.
                logging.warning(f"[ROUTE DEEPSEEK] Baseten a repondu ({modele_id}, slug {slug})")
                return reponse
            except Exception as erreur:
                if self._client_direct is None or not est_erreur_repli_baseten(erreur):
                    raise
                noter_baseten_epuise()
                logging.warning(f"Baseten refuse DeepSeek ({modele_id}), repli direct : {erreur}")
        if self._client_direct is None:
            raise RuntimeError(f"{modele_id} : ni Baseten ni le direct ne sont disponibles")
        reponse = self._client_direct.chat.completions.create(**arguments)
        if slug is not None:
            motif = "repli apres refus Baseten"
        elif self._client_baseten is None:
            motif = "Baseten desactive ou cle absente"
        elif baseten_circuit_ouvert():
            motif = "Baseten mis de cote (refus recent)"
        else:
            motif = "modele sans slug Baseten"
        logging.warning(f"[ROUTE DEEPSEEK] DeepSeek direct a repondu ({modele_id}), motif : {motif}")
        return reponse
