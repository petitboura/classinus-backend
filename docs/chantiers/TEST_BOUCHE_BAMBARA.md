# Bambara voice test (isolated folder)

[English version] · [Français](TEST_BOUCHE_BAMBARA.fr.md)

Temporary folder `bambara-bouche/`, isolated from the rest of the backend (no existing code changed). Same principle as `bambara-ecoute/`: one folder, one deployment that serves both the test page and the voices. To delete after the tests.

## Role

A small server with a single test page. You type a Bambara sentence and listen to each voice, one card per voice, or all of them in turn with "Tout écouter". Each card shows the licence status of the model and whether the model card calls it experimental. Because the page and the voices are served by the same address, there is no CORS and no mixed content problem.

## Voices

| Id | Model | Speakers | Licence status (read on the model card) |
|---|---|---|---|
| `bam_vits` | `RobotsMali/bam-vits` | 20 | Not checked. The card calls it an undertrained research checkpoint. |
| `mms_sudoping01` | `sudoping01/bambara-tts` | 1 | CC BY-NC 4.0: non-commercial only, test use only. |

The `ekodi` female voice is not in the catalogue: its model card could not be read, so its loading method and licence are unverified. Adding a voice means adding one entry to `VOIX` in `voix.py`. Licence statuses are what the cards say, not legal advice.

## Settings (environment variables)

- `PORT` (default 8000).
- `VOIX_ACTIVES`: comma-separated voice ids, all voices if absent.
- `TEXTE_MAX` (default 600): maximum text length in characters.
- `SYNTHESES_MAX` (default 1): simultaneous syntheses.
- `PRECHARGER` (default 1): set to 0 to load each voice at first use instead of at startup.
- `TEST_ACCESS_TOKEN`: if set, `/voix` and `/synthese` require it. Open the page with `?token=VALUE`.
- `HF_HOME` (set to `/data/hf` in the Dockerfile): where model weights are kept. Mount a volume on `/data`.

## Deploy on Coolify

Build pack Dockerfile, base directory `/bambara-bouche`, port 8000, domain starting with `https://` (so Coolify requests a real certificate), persistent volume on `/data`. Health check path: `/etat`.

## Limits

- Nothing was run against the real models where this was written (no access to Hugging Face). The tests use fake models. Check the first real run by ear and in the logs; load failures appear on the page.
- `bam_vits` lowercases the text before synthesis because its card says the training text was lowercased. Compare with and without if the result sounds wrong.
- No account, no database, nothing stored. Anyone with the address can use the voices unless `TEST_ACCESS_TOKEN` is set.

## Run the tests

From the folder: `python3 -m unittest test_app`.
