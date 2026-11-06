"""
Adaptateur Vultr pour les modeles servis UNIQUEMENT par Vultr Serverless Inference (04/11/2026,
demande Bourama) : Z.ai (GLM), Alibaba (Qwen), NVIDIA (Nemotron) et Muse Glimmer de Meta.

Contrairement a DeepSeek (core/adaptateur_vultr_deepseek.py, ou Vultr n'est qu'une route avec repli),
ces modeles n'ont pas d'autre route : Vultr est leur seul chemin, une erreur remonte telle quelle.
Meme appel que le SDK OpenAI (client.chat.completions.create), comme les autres adaptateurs : la
boucle d'agent (outils, memoire, confirmations, bouton Arreter) n'y voit aucune difference.

L'identifiant envoye a Vultr est celui de la colonne modele_id_vultr de Supabase, confronte au vrai
catalogue (GET /v1/models, cache 10 minutes) : si Vultr a ajoute un suffixe de date a l'identifiant
(comme deepseek-v4.1-flash-1017), le suffixe est retrouve tout seul. Aucun identifiant n'est
invente : sans correspondance dans le catalogue, l'identifiant de Supabase part tel quel et c'est
la reponse de Vultr qui dit ce qui ne va pas.

Aucun reglage d'effort de reflexion n'est envoye (jamais verifie chez Vultr pour ces modeles).
"""

import logging
import time

try:
    from adaptateur_commun import ClientCompatible, DELAI_APPEL_FOURNISSEUR_SECONDES
except ImportError:
    from core.adaptateur_commun import ClientCompatible, DELAI_APPEL_FOURNISSEUR_SECONDES

DUREE_CACHE_CATALOGUE_SECONDES = 10 * 60

_catalogue = {"ids": None, "expire_a": 0}


def _lire_catalogue(client_vultr):
    """Identifiants du catalogue Vultr (cache 10 minutes). None si la liste n'est pas lisible."""
    maintenant = time.time()
    if _catalogue["ids"] is not None and _catalogue["expire_a"] > maintenant:
        return _catalogue["ids"]
    try:
        ids = [m.id for m in client_vultr.models.list().data if getattr(m, "id", None)]
    except Exception as erreur:
        logging.warning(f"Catalogue Vultr illisible, identifiants envoyes tels quels : {erreur}")
        return _catalogue["ids"]
    if ids:
        _catalogue["ids"] = ids
        _catalogue["expire_a"] = maintenant + DUREE_CACHE_CATALOGUE_SECONDES
    return ids or None


def reinitialiser_catalogue_vultr():
    """Vide le cache du catalogue (tests)."""
    _catalogue["ids"] = None
    _catalogue["expire_a"] = 0


def resoudre_identifiant_vultr(client_vultr, identifiant):
    """
    Identifiant exact du catalogue Vultr pour l'identifiant reglé dans Supabase : l'identifiant
    lui-meme s'il existe, sinon celui qui le prolonge par un suffixe (le plus recent par ordre
    alphabetique, les suffixes de date se classent bien), sinon l'identifiant inchange.
    """
    ids = _lire_catalogue(client_vultr)
    if not ids or identifiant in ids:
        return identifiant
    prolonges = sorted(i for i in ids if i.startswith(identifiant + "-"))
    if prolonges:
        return prolonges[-1]
    logging.warning(f"Identifiant {identifiant} absent du catalogue Vultr")
    return identifiant


class ClientVultr(ClientCompatible):
    """
    Client des modeles "Vultr seul".

    correspondance_modeles : {identifiant du selecteur: identifiant Vultr}, lu dans Supabase
    (colonne modele_id_vultr, voir core/fournisseurs_llm.py:correspondance_vultr_seul).
    client_vultr : client OpenAI deja pointe sur Vultr (fournisseurs_llm.creer_client_vultr).
    """

    def __init__(self, correspondance_modeles, client_vultr):
        super().__init__()
        self._correspondance = dict(correspondance_modeles or {})
        self._client_vultr = client_vultr

    def create(self, **arguments):
        modele_id = arguments.get("model")
        identifiant = self._correspondance.get(modele_id, modele_id)
        identifiant = resoudre_identifiant_vultr(self._client_vultr, identifiant)
        arguments_vultr = {**arguments, "model": identifiant}
        # Pas de reglage d'effort : jamais verifie chez Vultr pour ces modeles.
        arguments_vultr.pop("reasoning_effort", None)
        # Pas de modele de secours : meme patience que les autres fournisseurs sans repli.
        # Affectation directe et non setdefault (06/11/2026) : la boucle d'agent envoie toujours
        # le delai court de la cascade (10 s), donc setdefault ne s'appliquait jamais et un modele
        # qui reflechit plus de 10 s avant son premier mot (glm-5.3) tombait en timeout.
        # Meme correction que pour Baseten et Vultr DeepSeek.
        arguments_vultr["timeout"] = DELAI_APPEL_FOURNISSEUR_SECONDES
        reponse = self._client_vultr.chat.completions.create(**arguments_vultr)
        logging.warning(f"[ROUTE VULTR] Vultr a repondu ({modele_id}, identifiant {identifiant})")
        return reponse
