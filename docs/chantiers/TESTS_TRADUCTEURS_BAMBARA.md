# Bambara translator tests

[English version] · [Français](TESTS_TRADUCTEURS_BAMBARA.fr.md)

Temporary folder `bambara-tests/`, isolated from the rest of the backend (no existing code changed, nothing deployed). To be deleted after the tests.

## Purpose
A small server with a test page: pick an engine and a direction, write a sentence, read the result. A Bambara speaker rates each result (Understood, Half, Wrong). The table can be copied or downloaded as CSV, to compare with Kooma.

## Engines
| Engine | Model | Directions |
|---|---|---|
| MADLAD-400 3B | `google/madlad400-3b-mt` | French or English to Bambara, Bambara to French or English |
| LocaleNLP English to Bambara | `LocaleNLP/localenlp-eng-bam-0.03` | English to Bambara |
| LocaleNLP Bambara to English | `LocaleNLP/localenlp-bam-eng-0.03` | Bambara to English |

The LocaleNLP ids were checked on Hugging Face. For MADLAD, the Bambara tag `<2bm>` still has to be confirmed at the first test.

## Settings (environment variables)
- `MAX_LOADED_MODELS` (default 1), `MODEL_DTYPE` (default bfloat16), `MAX_NEW_TOKENS`, `MAX_INPUT_CHARS`, `PORT`.
- `MADLAD_MODEL`, `LOCALENLP_ENG_BAM_MODEL`, `LOCALENLP_BAM_ENG_MODEL` to swap a model.
- `TEST_ACCESS_TOKEN`: when set, translation requires this token (open the page with `?token=VALUE`).
- `HF_TOKEN`: only if a model requires a Hugging Face login.

## Memory and speed
About 8 GB of memory for MADLAD in bfloat16, no GPU. A few seconds per sentence. The first translation of each engine downloads the model.

## Run
`docker build -t bambara-tests ./bambara-tests`, with a volume mounted on `/data` to keep the downloaded models.
