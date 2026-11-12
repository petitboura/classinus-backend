# Bambara translator test (isolated folder)

[English version] · [Français](TEST_TRADUCTION_BAMBARA.fr.md)

Temporary folder `bambara-traduction/`, isolated from the rest of the backend (no existing code changed). Same principle as `bambara-ecoute/` and `bambara-bouche/`: one folder, one deployment that serves both the test page and the translators. To be deleted after the tests.

## Purpose

A small server with a single test page. Pick an engine and a direction, write a sentence, read the result. A Bambara speaker rates each result with three buttons (Understood, Half, Wrong). The table can be copied or downloaded as CSV, to compare with Kooma. The page and the translators share one address, so there is no CORS issue and no mixed content. The page is in French and English.

## Engines

| Id | Model | Directions | Note (read from the model cards, not legal advice) |
|---|---|---|---|
| `madlad` | `google/madlad400-3b-mt` | French or English to Bambara, Bambara to French or English | General-purpose model. The Bambara tag `<2bm>` has to be confirmed at the first try. |
| `nllb_bambara` | `oza75/bm-nllb-1.3B-03` | French or English to Bambara, Bambara to French or English | NLLB adapted to Bambara. Derives from `facebook/nllb-200-distilled-1.3B`: check the license before any commercial use. A neighboring model by the same author asks to accept conditions, set `HF_TOKEN` if the download is refused. |
| `localenlp_eng_bam` | `LocaleNLP/localenlp-eng-bam-0.03` | English to Bambara | Marian model, English only. |
| `localenlp_bam_eng` | `LocaleNLP/localenlp-bam-eng-0.03` | Bambara to English | Marian model, English only. |

Adding an engine means adding an entry to `MOTEURS` in `moteurs.py`.

## Settings (environment variables)

- `PORT` (8000 by default).
- `TEXTE_MAX` (600 by default): maximum text length in characters. `TOKENS_MAX` (256 by default): maximum translation length.
- `MOTEURS_GARDES` (1 by default): number of models kept in memory at once. 1 is the leanest, another model is unloaded when a new one is requested.
- `PRECISION` (`bfloat16` by default): `float32` if memory allows.
- `PRECHARGER_MOTEURS`: comma-separated ids to load at startup. Empty by default, since with a single model kept, preloading everything would make no sense.
- `MADLAD_MODELE`, `NLLB_BAMBARA_MODELE`, `LOCALENLP_ENG_BAM_MODELE`, `LOCALENLP_BAM_ENG_MODELE`: to swap a model.
- `TEST_ACCESS_TOKEN`: when set, `/moteurs` and `/traduire` require it. Open the page with `?token=VALUE`.
- `HF_TOKEN`: only if a model requires a Hugging Face login.
- `HF_HOME` (set to `/data/hf` in the Dockerfile): folder where model weights are kept. Mount a volume on `/data`.

## Deploy on Coolify

Dockerfile build pack, base directory `/bambara-traduction`, port 8000, domain starting with `https://` (so Coolify requests a real certificate), persistent volume on `/data`. Health check path: `/etat`. Plan about 8 GB of memory for MADLAD in `bfloat16`, no GPU: a few seconds per sentence, and the first translation of each engine downloads the model.

## Limits

- Nothing was run with the real models where this was written (no Hugging Face access). The tests use fake models. Check the first real try in the page and in the logs: a loading or memory failure shows on the page, with its detail.
- No published comparison between these engines for Bambara translation was found. Scores in Bambara studies are low overall: only a speaker's judgment on real sentences can decide.
- No account, no database, nothing is kept. Anyone with the address can use the translators, unless `TEST_ACCESS_TOKEN` is set.

## Run the tests

From the folder: `python3 -m unittest test_app` (no model downloaded, PyTorch not needed).
