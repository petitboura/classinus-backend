"""
Mesure des tokens consommés par chaque appel au modèle (07/11/2026, demande Bourama : l'entrée
coûtait beaucoup trop cher et rien ne permettait de savoir où elle partait).

Chaque fournisseur rapporte ses tokens avec ses propres noms. Ce module les ramène tous à la
même forme et écrit UNE ligne de journal par appel, repérable avec « [USAGE] » dans les logs
Railway :

    [USAGE] modele=glm-5.3 entree=12400 cache_lu=9800 cache_ecrit=0 sortie=310 part_cache=79% messages=14 outils=22

Définitions, identiques pour tous les fournisseurs :
- entree      : tous les tokens d'entrée de l'appel, cache compris (c'est le chiffre facturé en gros) ;
- cache_lu    : la part de l'entrée relue depuis le cache du fournisseur (facturée beaucoup moins) ;
- cache_ecrit : la part écrite dans le cache (Claude seulement, facturée un peu plus que l'entrée) ;
- sortie      : tokens générés.

Un fournisseur qui ne dit rien sur le cache donne cache_lu=0 : c'est « inconnu ou aucun », pas
une preuve que le cache ne marche pas. Et un fournisseur qui ne renvoie aucun usage donne une
ligne « usage non rapporté », ce qui est déjà une information.
"""

import hashlib
import json
import logging


def _lire(objet, nom):
    """Valeur d'un champ, que l'objet soit un dict ou un objet à attributs ; None sinon."""
    if objet is None:
        return None
    if isinstance(objet, dict):
        return objet.get(nom)
    return getattr(objet, nom, None)


def _entier(valeur):
    try:
        return int(valeur or 0)
    except (TypeError, ValueError):
        return 0


def normaliser_usage(usage):
    """
    Ramène l'usage d'un fournisseur à {"entree", "cache_lu", "cache_ecrit", "sortie"}.
    None si usage est vide ou illisible.

    Formats reconnus (détectés d'après leurs champs, jamais d'après le nom du fournisseur) :
    - Anthropic : input_tokens EXCLUT le cache, avec cache_read_input_tokens et
      cache_creation_input_tokens à part ;
    - API Responses (GPT, Grok, Meta) : input_tokens INCLUT le cache, détail dans
      input_tokens_details.cached_tokens ;
    - Gemini : prompt_token_count, cached_content_token_count, candidates_token_count ;
    - Chat Completions (DeepSeek, Vultr, Baseten, Groq...) : prompt_tokens, avec
      prompt_tokens_details.cached_tokens, ou prompt_cache_hit_tokens chez DeepSeek.
    """
    if usage is None:
        return None

    # Anthropic : le champ cache_creation_input_tokens n'existe que chez lui.
    if _lire(usage, "cache_creation_input_tokens") is not None or _lire(usage, "cache_read_input_tokens") is not None:
        lu = _entier(_lire(usage, "cache_read_input_tokens"))
        ecrit = _entier(_lire(usage, "cache_creation_input_tokens"))
        return {
            "entree": _entier(_lire(usage, "input_tokens")) + lu + ecrit,
            "cache_lu": lu,
            "cache_ecrit": ecrit,
            "sortie": _entier(_lire(usage, "output_tokens")),
        }

    # Gemini
    if _lire(usage, "prompt_token_count") is not None:
        sortie = _entier(_lire(usage, "candidates_token_count")) + _entier(_lire(usage, "thoughts_token_count"))
        return {
            "entree": _entier(_lire(usage, "prompt_token_count")),
            "cache_lu": _entier(_lire(usage, "cached_content_token_count")),
            "cache_ecrit": 0,
            "sortie": sortie,
        }

    # API Responses
    detail_entree = _lire(usage, "input_tokens_details")
    if _lire(usage, "input_tokens") is not None:
        return {
            "entree": _entier(_lire(usage, "input_tokens")),
            "cache_lu": _entier(_lire(detail_entree, "cached_tokens")),
            "cache_ecrit": 0,
            "sortie": _entier(_lire(usage, "output_tokens")),
        }

    # Chat Completions
    if _lire(usage, "prompt_tokens") is not None:
        lu = _lire(_lire(usage, "prompt_tokens_details"), "cached_tokens")
        if lu is None:
            lu = _lire(usage, "prompt_cache_hit_tokens")  # DeepSeek direct
        return {
            "entree": _entier(_lire(usage, "prompt_tokens")),
            "cache_lu": _entier(lu),
            "cache_ecrit": 0,
            "sortie": _entier(_lire(usage, "completion_tokens")),
        }

    return None


def empreinte(objet):
    """
    Empreinte courte d'un contenu (4 caracteres hexa). Deux appels dont les empreintes d'outils et de
    tete sont identiques ont le meme debut : si le cache ne relit rien malgre cela, la cause est chez
    le fournisseur ; si elles changent d'un appel a l'autre, c'est NOTRE debut de requete qui bouge.
    """
    try:
        texte = objet if isinstance(objet, str) else json.dumps(objet, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:4]
    except Exception:
        return "????"


def empreintes_de_la_requete(messages, outils):
    """{"outils": ..., "tete": ..., "historique": ...} : empreintes du debut de la requete (voir empreinte)."""
    messages = messages or []
    premier = messages[0].get("content") if messages and isinstance(messages[0], dict) else ""
    historique = [m for m in messages[1:] if isinstance(m, dict) and m.get("role") != "system"]
    return {
        "empreinte_outils": empreinte(outils or []),
        "empreinte_tete": empreinte(premier or ""),
        "empreinte_debut_historique": empreinte(historique[:-1][:6]),
    }


def ligne_usage(modele, usage, **contexte):
    """Texte de la ligne de journal pour un appel. Séparé de journaliser_usage pour être testable."""
    mesure = normaliser_usage(usage)
    complement = "".join(f" {cle}={valeur}" for cle, valeur in contexte.items() if valeur is not None)
    if mesure is None:
        return f"[USAGE] modele={modele} usage non rapporté par le fournisseur{complement}"
    part = (100 * mesure["cache_lu"] // mesure["entree"]) if mesure["entree"] else 0
    return (
        f"[USAGE] modele={modele} entree={mesure['entree']} cache_lu={mesure['cache_lu']} "
        f"cache_ecrit={mesure['cache_ecrit']} sortie={mesure['sortie']} part_cache={part}%{complement}"
    )


def journaliser_usage(modele, usage, **contexte):
    """
    Écrit la ligne [USAGE] de l'appel. En warning, parce que le niveau info n'apparaît pas dans les
    logs de Railway (même raison que les lignes [ROUTE ...]). Ne lève jamais : une mesure ratée ne
    doit pas casser une réponse.
    """
    try:
        logging.warning(ligne_usage(modele, usage, **contexte))
    except Exception as erreur:  # pragma: no cover - garde-fou
        logging.warning(f"[USAGE] mesure impossible ({modele}) : {erreur}")


def _refus_stream_options(erreur):
    texte = str(erreur).lower()
    return "stream_options" in texte or "include_usage" in texte


def ouvrir_flux_avec_usage(creer, arguments):
    """
    Appelle creer(**arguments) en demandant au fournisseur de joindre l'usage au dernier morceau du
    flux (stream_options.include_usage, option standard de l'API Chat Completions). Sans cette
    demande, les fournisseurs compatibles OpenAI n'envoient AUCUN usage en streaming.

    Si le fournisseur refuse cette option, on rouvre sans elle : mesurer ne doit jamais empêcher de
    répondre. L'erreur est gérée ici, donc jamais vue par les replis Vultr/Baseten qui, eux,
    prendraient un refus de paramètre pour une panne du fournisseur.
    """
    if not arguments.get("stream") or "stream_options" in arguments:
        return creer(**arguments)
    try:
        return creer(**{**arguments, "stream_options": {"include_usage": True}})
    except Exception as erreur:
        if not _refus_stream_options(erreur):
            raise
        logging.warning(f"[USAGE] le fournisseur refuse stream_options, nouvel essai sans mesure : {erreur}")
        return creer(**arguments)
