# Bambara voice (test "mouth")

[English version] · [Français](BOUCHE_BAMBARA.fr.md)

Status: test tool on branch `feat/bouche-bambara`, not deployed, not connected to the chat. Requested by Bourama on 12 November 2026 to compare Bambara text-to-speech voices by ear before choosing one for Classinus.

## What it is

A separate service that turns Bambara text into a WAV file, plus a relay in the main backend so an administrator can use it from a test page of the frontend (`/dev-demo-bouche`).

```
Browser (admin) -> POST /api/bouche/synthese (main backend, api/bouche.py)
                -> POST /synthese (bouche service, api/main_bouche.py, internal token)
                -> core/bouche_bambara.py -> voice model -> WAV
```

The voices run on CPU only. PyTorch and Transformers live only in the separate service (`Dockerfile.bouche`, `requirements-bouche.txt`), never in the main backend image. This follows the same pattern as the video montage service.

## Files

- `core/bouche_bambara.py`: voice catalogue (`VOIX`), request validation, lazy model loading, WAV encoding.
- `api/main_bouche.py`: the separate service (`/sante`, `/voix`, `/synthese`). Every route except `/sante` checks the internal token (`SUPABASE_SECRET`).
- `api/bouche.py`: admin-only relay in the main backend (`GET /api/bouche/voix`, `POST /api/bouche/synthese`).
- `Dockerfile.bouche`, `requirements-bouche.txt`: build of the separate service.
- `tests/test_bouche_bambara.py`: offline tests (no model download, no PyTorch needed).

## Voices in the catalogue

| Id | Model | Speakers | Licence status (read on the model card) |
|---|---|---|---|
| `bam_vits` | `RobotsMali/bam-vits` | 20 | Not checked. The card calls it an undertrained research checkpoint. |
| `mms_sudoping01` | `sudoping01/bambara-tts` | 1 | CC BY-NC 4.0: non-commercial only. Test use only, never in the paid product. |

The `ekodi` female voice (`ynnov/ekodi-bambara-tts-female`) is not in the catalogue yet: its model card could not be read, so its loading method and licence are unverified. Adding a voice means adding one entry to `VOIX` once its card has been read.

Licence statuses are what the model cards say, not legal advice. Check each one before any production use.

## Configuration

Separate service:

- `SUPABASE_SECRET`: the same internal token as the main service.
- `BOUCHE_VOIX_ACTIVES` (optional): comma-separated voice ids. All voices if absent.
- `BOUCHE_TEXTE_MAX` (optional, default 600): maximum text length in characters.
- `BOUCHE_SYNTHESES_MAX` (optional, default 1): simultaneous syntheses.
- `HF_HOME` (set in the Dockerfile to `/data/huggingface`): where model weights are cached. Attach a volume there to avoid downloading them again at each restart.

Main service:

- `BOUCHE_URL`: address of the bouche service without a path, for example `http://service-name.railway.internal:8000`. Without it, the test page answers "not connected" and nothing else changes.
- `BOUCHE_DELAI_S` (optional, default 180): maximum wait for a synthesis. The first use of a voice downloads its model, so it is slower.

## Data and account deletion

Nothing is stored: no table, no file. The text sent for synthesis is not kept. No change is needed in `core/purge_compte.py` or in the export of `api/profiles.py`.

## Known limits

- Nothing was run against the real models in the development environment (no access to Hugging Face). The tests use fake models. The first real run must be checked by ear and in the service logs.
- `bam_vits` lowercases the text before synthesis because its model card says the training text was lowercased. Compare with and without if the result sounds wrong.
- Quality is judged by ear, ideally by a Bambara speaker. No automatic score exists.
