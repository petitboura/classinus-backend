"""
Adaptateur Vultr pour DeepSeek (04/11/2026, hackathon Vultr Agent Rush, demande Bourama).

C'est le MEME DeepSeek qu'avant, vu par l'utilisateur : memes modeles dans le selecteur, meme
reprise de tour, meme historique. Seule la route change, exactement comme pour Baseten : quand
l'interrupteur est ON (colonne vultr_actif de la ligne deepseek dans Supabase, table
fournisseurs_llm), les appels des modeles qui ont un identifiant Vultr (colonne modele_id_vultr de
modeles_llm) partent vers Vultr Serverless Inference (cle VULTR_INFERENCE_API_KEY). Les autres
modeles, et tous les appels quand l'interrupteur est OFF, suivent la route habituelle (Baseten ou
DeepSeek en direct), sans rien changer.

Repli automatique : si Vultr refuse pour une raison de credit, quota, cle ou modele retire
(401/402/403/404/429 ou message explicite), l'appel repart aussitot par la route habituelle, sans
erreur pour l'eleve, et Vultr est mis de cote pour 10 minutes (disjoncteur : evite de retomber sur
le refus a chaque message tant que Bourama n'a pas remis du credit ou eteint l'interrupteur).
Passe ce delai, Vultr est reessaye tout seul.

La boucle d'agent continue d'envoyer l'identifiant direct de DeepSeek, traduit ici en identifiant
Vultr : ni la reprise de tour, ni l'identite, ni l'historique ne voient l'identifiant Vultr.
Meme appel que le SDK OpenAI (client.chat.completions.create), comme les autres adaptateurs (voir
core/adaptateur_commun.py:ClientCompatible).
"""

import logging
import time

try:
    from adaptateur_commun import ClientCompatible, DELAI_APPEL_FOURNISSEUR_SECONDES
except ImportError:
    from core.adaptateur_commun import ClientCompatible, DELAI_APPEL_FOURNISSEUR_SECONDES

# Delai de mise a l'ecart de Vultr apres un refus de credit, quota, cle ou modele.
DELAI_REESSAI_VULTR_SECONDES = 10 * 60

_vultr_ecarte_jusqua = 0


def vultr_circuit_ouvert():
    """True tant que Vultr est mis a l'ecart (refus recent)."""
    return time.time() < _vultr_ecarte_jusqua


def noter_vultr_ecarte():
    """Met Vultr a l'ecart pour DELAI_REESSAI_VULTR_SECONDES."""
    global _vultr_ecarte_jusqua
    _vultr_ecarte_jusqua = time.time() + DELAI_REESSAI_VULTR_SECONDES


def reinitialiser_circuit_vultr():
    """Remet le disjoncteur a zero (tests)."""
    global _vultr_ecarte_jusqua
    _vultr_ecarte_jusqua = 0


# Statuts HTTP qui declenchent le repli : non authentifie (cle absente ou invalide), paiement
# requis (credit epuise), interdit, modele introuvable (identifiant retire par Vultr), quota ou
# limite atteint. Tout autre statut remonte tel quel.
_STATUTS_REPLI_VULTR = (401, 402, 403, 404, 429)

# Mots d'un message d'erreur qui declenchent le repli meme sans statut lisible (SDK ou forme
# inattendue). En anglais : les API renvoient ces erreurs en anglais.
_MOTS_CLE_REPLI_VULTR = (
    "credit", "quota", "payment", "billing", "insufficient",
    "balance", "funds", "unpaid", "limit exceeded", "model not found",
)

# Niveaux d'effort que Vultr a acceptes lors du test reel du 04/11/2026 (none, low, medium, high).
# DeepSeek en direct accepte aussi "max", jamais essaye chez Vultr : on l'envoie comme "high",
# le niveau le plus proche deja verifie, plutot que de risquer un refus au premier message.
_EFFORT_MAX_DEEPSEEK = "max"
_EFFORT_VULTR_POUR_MAX = "high"


def est_erreur_repli_vultr(erreur):
    """True si l'erreur Vultr merite le repli vers la route habituelle."""
    statut = getattr(erreur, "status_code", None)
    if statut is None:
        reponse = getattr(erreur, "response", None)
        statut = getattr(reponse, "status_code", None)
    try:
        statut = int(statut) if statut is not None else None
    except (TypeError, ValueError):
        statut = None
    if statut in _STATUTS_REPLI_VULTR:
        return True
    return any(mot in str(erreur).lower() for mot in _MOTS_CLE_REPLI_VULTR)


class ClientVultrDeepseek(ClientCompatible):
    """
    Client DeepSeek routable : Vultr quand c'est possible, route habituelle sinon.

    correspondance_modeles : {identifiant direct: identifiant Vultr}, lu dans Supabase (colonne
    modele_id_vultr, voir core/fournisseurs_llm.py).
    client_vultr : client OpenAI deja pointe sur Vultr (voir fournisseurs_llm.creer_client_vultr).
    client_habituel : ce que creer_client_deepseek aurait renvoye sans Vultr (client Baseten ou
    direct), ou None s'il n'y a aucune autre route : la premiere erreur Vultr remonte alors.
    """

    def __init__(self, correspondance_modeles, client_vultr, client_habituel=None):
        super().__init__()
        self._correspondance = dict(correspondance_modeles or {})
        self._client_vultr = client_vultr
        self._client_habituel = client_habituel

    def _identifiant_pour(self, modele_id):
        if self._client_vultr is None or vultr_circuit_ouvert():
            return None
        return self._correspondance.get(modele_id)

    def create(self, **arguments):
        modele_id = arguments.get("model")
        identifiant = self._identifiant_pour(modele_id)
        if identifiant is not None:
            arguments_vultr = {**arguments, "model": identifiant}
            if arguments_vultr.get("reasoning_effort") == _EFFORT_MAX_DEEPSEEK:
                arguments_vultr["reasoning_effort"] = _EFFORT_VULTR_POUR_MAX
            # Sans autre route, le delai court de la cascade (10 s) couperait la reponse net
            # quand le premier mot tarde : meme patience que les fournisseurs sans repli.
            if self._client_habituel is None:
                arguments_vultr["timeout"] = DELAI_APPEL_FOURNISSEUR_SECONDES
            try:
                reponse = self._client_vultr.chat.completions.create(**arguments_vultr)
                # En warning car le niveau info n'apparait pas dans les logs de Railway.
                logging.warning(f"[ROUTE DEEPSEEK] Vultr a repondu ({modele_id}, identifiant {identifiant})")
                return reponse
            except Exception as erreur:
                if self._client_habituel is None or not est_erreur_repli_vultr(erreur):
                    raise
                noter_vultr_ecarte()
                logging.warning(f"Vultr refuse DeepSeek ({modele_id}), repli sur la route habituelle : {erreur}")
        if self._client_habituel is None:
            raise RuntimeError(f"{modele_id} : ni Vultr ni une autre route ne sont disponibles")
        if identifiant is not None:
            motif = "repli apres refus Vultr"
        elif vultr_circuit_ouvert():
            motif = "Vultr mis de cote (refus recent)"
        else:
            motif = "modele sans identifiant Vultr"
        logging.warning(f"[ROUTE DEEPSEEK] route habituelle a repondu ({modele_id}), motif : {motif}")
        return self._client_habituel.chat.completions.create(**arguments)
