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
try:
    from usage_llm import ouvrir_flux_avec_usage
except ImportError:
    from core.usage_llm import ouvrir_flux_avec_usage

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

# Effort de reflexion (22/11/2026) : le niveau choisi par la personne part TOUJOURS tel quel chez
# Vultr. Jusqu'ici "max" etait remplace par "high" sans rien dire (Vultr n'avait accepte que none,
# low, medium et high lors du test reel du 04/11/2026, "max" n'y avait jamais ete essaye, et la page
# Vultr du modele ne liste aucun niveau) : l'ecran affichait Maximum alors que le modele tournait
# au niveau en dessous. Si Vultr refuse un niveau (erreur 400 ou 422 qui parle d'effort), l'appel
# repart par la route habituelle, qui accepte le niveau choisi, sans mettre Vultr a l'ecart (Vultr
# n'est pas en panne, il ne connait seulement pas ce niveau). Sans route habituelle, l'erreur
# remonte : mieux vaut un refus visible qu'un effort modifie en silence.
_STATUTS_REFUS_EFFORT_VULTR = (400, 422)


def est_refus_effort_vultr(erreur):
    """True si Vultr refuse le niveau d'effort envoye (erreur 400 ou 422 dont le message parle d'effort)."""
    statut = getattr(erreur, "status_code", None)
    if statut is None:
        reponse = getattr(erreur, "response", None)
        statut = getattr(reponse, "status_code", None)
    try:
        statut = int(statut) if statut is not None else None
    except (TypeError, ValueError):
        statut = None
    return statut in _STATUTS_REFUS_EFFORT_VULTR and "effort" in str(erreur).lower()


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
        refus_effort = False
        if identifiant is not None:
            # L'effort choisi part tel quel : jamais modifie en silence (voir plus haut).
            arguments_vultr = {**arguments, "model": identifiant}
            # Sans autre route, le delai court de la cascade (10 s) couperait la reponse net
            # quand le premier mot tarde : meme patience que les fournisseurs sans repli.
            if self._client_habituel is None:
                arguments_vultr["timeout"] = DELAI_APPEL_FOURNISSEUR_SECONDES
            try:
                reponse = ouvrir_flux_avec_usage(self._client_vultr.chat.completions.create, arguments_vultr)
                # En warning car le niveau info n'apparait pas dans les logs de Railway.
                logging.warning(f"[ROUTE DEEPSEEK] Vultr a repondu ({modele_id}, identifiant {identifiant})")
                return reponse
            except Exception as erreur:
                if self._client_habituel is None:
                    raise
                if est_erreur_repli_vultr(erreur):
                    noter_vultr_ecarte()
                    logging.warning(f"Vultr refuse DeepSeek ({modele_id}), repli sur la route habituelle : {erreur}")
                elif est_refus_effort_vultr(erreur):
                    # Pas de mise a l'ecart : Vultr fonctionne, il ne connait pas ce niveau d'effort.
                    refus_effort = True
                    logging.warning(
                        f"Vultr refuse l'effort {arguments.get('reasoning_effort')} pour DeepSeek ({modele_id}), "
                        f"repli sur la route habituelle avec le meme effort : {erreur}"
                    )
                else:
                    raise
        if self._client_habituel is None:
            raise RuntimeError(f"{modele_id} : ni Vultr ni une autre route ne sont disponibles")
        if refus_effort:
            motif = "niveau d'effort refuse par Vultr"
        elif identifiant is not None:
            motif = "repli apres refus Vultr"
        elif vultr_circuit_ouvert():
            motif = "Vultr mis de cote (refus recent)"
        else:
            motif = "modele sans identifiant Vultr"
        logging.warning(f"[ROUTE DEEPSEEK] route habituelle a repondu ({modele_id}), motif : {motif}")
        return ouvrir_flux_avec_usage(self._client_habituel.chat.completions.create, arguments)
