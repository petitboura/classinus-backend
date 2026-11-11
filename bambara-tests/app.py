"""Serveur de test des traducteurs bambara (temporaire, a supprimer apres les tests).

Deux familles de modeles, toutes les valeurs viennent de variables d'environnement
ou du dictionnaire ENGINES ci-dessous (modifiable sans toucher a la logique).
"""
import os
import time
import threading
import logging
from collections import OrderedDict

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bambara-tests")

# Combien de modeles gardes en memoire en meme temps (1 = le plus sobre en RAM).
MAX_LOADED = int(os.getenv("MAX_LOADED_MODELS", "1"))
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "2000"))
DTYPE = os.getenv("MODEL_DTYPE", "bfloat16")  # bfloat16 (economise la RAM) ou float32
ACCESS_TOKEN = os.getenv("TEST_ACCESS_TOKEN", "")  # si defini, exige l'en-tete x-access-token
HF_TOKEN = os.getenv("HF_TOKEN") or None

# Chaque moteur : identifiant du modele, famille, et pour chaque paire de langues
# la balise a placer devant le texte.
ENGINES = {
    "madlad": {
        "label": "MADLAD-400 3B",
        "model": os.getenv("MADLAD_MODEL", "google/madlad400-3b-mt"),
        "family": "t5",
        "tags": {"bam": "<2bm> ", "fra": "<2fr> ", "eng": "<2en> "},
        "pairs": ["fra-bam", "eng-bam", "bam-fra", "bam-eng"],
    },
    "localenlp_eng_bam": {
        "label": "LocaleNLP eng vers bam",
        "model": os.getenv("LOCALENLP_ENG_BAM_MODEL", "LocaleNLP/localenlp-eng-bam-0.03"),
        "family": "marian",
        "tags": {"bam": ">>bam<< "},
        "pairs": ["eng-bam"],
    },
    "localenlp_bam_eng": {
        "label": "LocaleNLP bam vers eng",
        "model": os.getenv("LOCALENLP_BAM_ENG_MODEL", "LocaleNLP/localenlp-bam-eng-0.03"),
        "family": "marian",
        "tags": {"eng": ">>eng<< "},
        "pairs": ["bam-eng"],
    },
}

app = FastAPI(title="Tests traducteurs bambara")
_lock = threading.Lock()
_loaded: "OrderedDict[str, tuple]" = OrderedDict()  # engine_id -> (tokenizer, model)


class TranslateIn(BaseModel):
    engine: str
    source: str  # fra, eng ou bam
    target: str  # fra, eng ou bam
    text: str


def _check_access(token):
    if ACCESS_TOKEN and token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="access_denied")


def _load(engine_id: str):
    """Charge un modele (et en decharge un autre si la limite de RAM est atteinte)."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    if engine_id in _loaded:
        _loaded.move_to_end(engine_id)
        return _loaded[engine_id]
    while len(_loaded) >= MAX_LOADED:
        old_id, _ = _loaded.popitem(last=False)
        log.info("Dechargement de %s", old_id)
    cfg = ENGINES[engine_id]
    log.info("Chargement de %s (%s)", engine_id, cfg["model"])
    t0 = time.time()
    dtype = getattr(torch, DTYPE)
    tok = AutoTokenizer.from_pretrained(cfg["model"], token=HF_TOKEN)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        cfg["model"], torch_dtype=dtype, low_cpu_mem_usage=True, token=HF_TOKEN
    )
    model.eval()
    _loaded[engine_id] = (tok, model)
    log.info("%s pret en %.1f s", engine_id, time.time() - t0)
    return _loaded[engine_id]


@app.get("/health")
def health():
    return {"status": "ok", "loaded": list(_loaded.keys()), "max_loaded": MAX_LOADED}


@app.get("/engines")
def engines():
    return {
        k: {"label": v["label"], "model": v["model"], "pairs": v["pairs"]}
        for k, v in ENGINES.items()
    }


@app.post("/translate")
def translate(body: TranslateIn, x_access_token: str = Header(default=None)):
    _check_access(x_access_token)
    cfg = ENGINES.get(body.engine)
    if not cfg:
        return JSONResponse({"error": "unknown_engine"}, status_code=400)
    pair = f"{body.source}-{body.target}"
    if pair not in cfg["pairs"]:
        return JSONResponse({"error": "unsupported_pair", "pairs": cfg["pairs"]}, status_code=400)
    text = body.text.strip()
    if not text:
        return JSONResponse({"error": "empty_text"}, status_code=400)
    if len(text) > MAX_INPUT_CHARS:
        return JSONResponse({"error": "text_too_long", "max": MAX_INPUT_CHARS}, status_code=400)
    try:
        import torch
        with _lock:
            tok, model = _load(body.engine)
            prompt = cfg["tags"][body.target] + text
            inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
            t0 = time.time()
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, num_beams=4)
            result = tok.decode(out[0], skip_special_tokens=True)
            elapsed = time.time() - t0
        return {"engine": body.engine, "pair": pair, "input": text, "output": result, "seconds": round(elapsed, 2)}
    except Exception as exc:  # erreur technique : loguee, message clair cote page
        log.exception("Echec de traduction")
        return JSONResponse({"error": "model_failure", "detail": str(exc)[:300]}, status_code=500)


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
