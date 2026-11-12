"""Moteurs de traduction bambara : catalogue, chargement et traduction.

Ajouter un moteur revient à ajouter une entrée dans MOTEURS. Rien n'est écrit en dur
ailleurs : les identifiants de modèles se changent par variables d'environnement.
"""
import contextlib
import logging
import os
import threading
import time
from collections import OrderedDict

log = logging.getLogger("bambara-traduction")

LANGUES = ("fra", "eng", "bam")


def _entier(nom: str, defaut: int) -> int:
    try:
        return int(os.environ.get(nom, defaut))
    except ValueError:
        return defaut


def texte_max() -> int:
    return _entier("TEXTE_MAX", 600)


def tokens_max() -> int:
    return _entier("TOKENS_MAX", 256)


def moteurs_gardes() -> int:
    return max(1, _entier("MOTEURS_GARDES", 1))


MOTEURS = {
    "madlad": {
        "nom": "MADLAD-400 3B",
        "modele": os.environ.get("MADLAD_MODELE", "google/madlad400-3b-mt"),
        "famille": "balise",
        "balises": {"bam": "<2bm> ", "fra": "<2fr> ", "eng": "<2en> "},
        "sens": ["fra-bam", "eng-bam", "bam-fra", "bam-eng"],
        "note": "Modèle généraliste, la balise bambara <2bm> est à confirmer au premier essai.",
    },
    "nllb_bambara": {
        "nom": "NLLB Bambara (oza75)",
        "modele": os.environ.get("NLLB_BAMBARA_MODELE", "oza75/bm-nllb-1.3B-03"),
        "famille": "nllb",
        "codes": {"fra": "fra_Latn", "eng": "eng_Latn", "bam": "bam_Latn"},
        "sens": ["fra-bam", "eng-bam", "bam-fra", "bam-eng"],
        "note": "NLLB adapté au bambara. Licence du modèle de base à vérifier avant un usage commercial.",
    },
    "localenlp_eng_bam": {
        "nom": "LocaleNLP anglais vers bambara",
        "modele": os.environ.get("LOCALENLP_ENG_BAM_MODELE", "LocaleNLP/localenlp-eng-bam-0.03"),
        "famille": "balise",
        "balises": {"bam": ">>bam<< "},
        "sens": ["eng-bam"],
        "note": "Modèle Marian, anglais seulement.",
    },
    "localenlp_bam_eng": {
        "nom": "LocaleNLP bambara vers anglais",
        "modele": os.environ.get("LOCALENLP_BAM_ENG_MODELE", "LocaleNLP/localenlp-bam-eng-0.03"),
        "famille": "balise",
        "balises": {"eng": ">>eng<< "},
        "sens": ["bam-eng"],
        "note": "Modèle Marian, anglais seulement.",
    },
}


class ErreurTraduction(Exception):
    def __init__(self, code: str, statut: int = 400, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.statut = statut
        self.detail = detail


_verrou = threading.Lock()
_charges: "OrderedDict[str, tuple]" = OrderedDict()  # id moteur -> (tokenizer, modèle)
_echecs: dict = {}  # id moteur -> dernier message d'échec de chargement


def etat_moteurs() -> dict:
    return {
        i: {"nom": m["nom"], "modele": m["modele"], "charge": i in _charges, "echec": _echecs.get(i)}
        for i, m in MOTEURS.items()
    }


def lister_moteurs() -> dict:
    return {
        i: {"nom": m["nom"], "modele": m["modele"], "sens": m["sens"], "note": m["note"]}
        for i, m in MOTEURS.items()
    }


def charger(moteur_id: str):
    """Charge un moteur, et en décharge un autre si la limite de mémoire est atteinte."""
    if moteur_id in _charges:
        _charges.move_to_end(moteur_id)
        return _charges[moteur_id]
    while len(_charges) >= moteurs_gardes():
        ancien, _ = _charges.popitem(last=False)
        log.info("Déchargement de %s", ancien)
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    modele_id = MOTEURS[moteur_id]["modele"]
    jeton = os.environ.get("HF_TOKEN") or None
    precision = getattr(torch, os.environ.get("PRECISION", "bfloat16"))
    debut = time.time()
    log.info("Chargement de %s (%s)", moteur_id, modele_id)
    try:
        tok = AutoTokenizer.from_pretrained(modele_id, token=jeton)
        try:
            modele = AutoModelForSeq2SeqLM.from_pretrained(
                modele_id, dtype=precision, low_cpu_mem_usage=True, token=jeton
            )
        except TypeError:  # anciennes versions de transformers : l'argument s'appelait torch_dtype
            modele = AutoModelForSeq2SeqLM.from_pretrained(
                modele_id, torch_dtype=precision, low_cpu_mem_usage=True, token=jeton
            )
        modele.eval()
    except Exception as exc:
        _echecs[moteur_id] = str(exc)[:300]
        raise
    _echecs.pop(moteur_id, None)
    _charges[moteur_id] = (tok, modele)
    log.info("%s prêt en %.1f s", moteur_id, time.time() - debut)
    return _charges[moteur_id]


def _sans_gradient():
    try:
        import torch

        return torch.no_grad()
    except ImportError:
        return contextlib.nullcontext()


def traduire(moteur_id: str, source: str, cible: str, texte: str) -> dict:
    cfg = MOTEURS.get(moteur_id)
    if not cfg:
        raise ErreurTraduction("moteur_inconnu")
    sens = f"{source}-{cible}"
    if sens not in cfg["sens"]:
        raise ErreurTraduction("sens_non_gere")
    texte = (texte or "").strip()
    if not texte:
        raise ErreurTraduction("texte_vide")
    if len(texte) > texte_max():
        raise ErreurTraduction("texte_trop_long")
    try:
        with _verrou:
            tok, modele = charger(moteur_id)
            options = {}
            if cfg["famille"] == "nllb":
                tok.src_lang = cfg["codes"][source]
                entree = texte
                options["forced_bos_token_id"] = tok.convert_tokens_to_ids(cfg["codes"][cible])
            else:
                entree = cfg["balises"][cible] + texte
            lot = tok(entree, return_tensors="pt", truncation=True, max_length=512)
            debut = time.time()
            with _sans_gradient():
                sortie = modele.generate(**lot, max_new_tokens=tokens_max(), num_beams=4, **options)
            resultat = tok.decode(sortie[0], skip_special_tokens=True)
            duree = time.time() - debut
    except ErreurTraduction:
        raise
    except Exception as exc:
        log.exception("Échec de traduction")
        raise ErreurTraduction("echec_modele", 500, str(exc)[:300])
    return {"moteur": moteur_id, "sens": sens, "entree": texte, "sortie": resultat, "secondes": round(duree, 2)}
