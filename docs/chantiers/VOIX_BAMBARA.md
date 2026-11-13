# Bambara voice mode

**English version** · [Version française](VOIX_BAMBARA.fr.md)

Status: requested by Bourama on 13 November 2026, branch `feat/voix-bambara-chaine`.

## What it does

When voice mode is turned on, Classinus asks "Bambara or other?". "Other" keeps the current voice mode (Gemini Live), unchanged. "Bambara" starts this chain:

```
microphone -> Soloni (transcribes only) -> text -> Classinus AI (chat) -> reply -> Gemini voice -> speaker
```

Two separate services do the audio work, outside the main backend: `bambara-ecoute/` (Soloni) and `bambara-bouche/` (Gemini voice). The browser never calls them directly: it goes through the relay `api/voix_bambara.py` with its account token.

## Routes (relay, `api/voix_bambara.py`)

- `GET /api/voix-bambara/etat`: `{"disponible": bool, "texte_max": int}`. `disponible` is true only when both addresses are set. The frontend offers Bambara only then.
- `POST /api/voix-bambara/transcrire`: sends the recording (field `fichier`) to Soloni, returns `{"texte": ...}`.
- `POST /api/voix-bambara/synthese`: `{"texte": ...}` returns a WAV read by the Gemini voice.

## Instructions given to the AI

The frontend sends `client: "voix_bambara"` with every Bambara-mode message (same idea as `thonny`, see `core/prompt_voix_bambara.py`). The prompt then gets three notes in its variable part, and nothing else changes:

1. The text stays plain because it is read aloud: no written element (file, code, diagram, flashcard, quiz, table). Images and videos are allowed, see note 3.
2. The user understands only Bambara, can neither read nor write, and can only speak and listen: the AI answers in Bambara suited to speech.
3. Added on 14 November 2026: the AI must always favor visuals, images and videos, over voice alone, because they can be understood without reading.

### Tools always given in this mode

On every Bambara-mode message, the AI also gets these tools directly, without going through `demander_outils`: `tavily_search`, `rechercher_image`, `rechercher_video`, `lire_video`. `tavily_extract`, `tavily_crawl`, `tavily_map` and `tavily_research` are deliberately left out. The list is `OUTILS_TOUJOURS_VOIX_BAMBARA` in `core/prompt_voix_bambara.py`; it is wired in `core/main.py` through `_outils_memoire_toujours_disponibles(..., noms=...)` in `core/routage_outils.py`. Other clients are not affected.

## Configuration (environment variables of the main backend)

Nothing is hard-coded.

- `VOIX_BAMBARA_ECOUTE_URL`: address of the Soloni service, no path.
- `VOIX_BAMBARA_BOUCHE_URL`: address of the Gemini voice service, no path.
- `VOIX_BAMBARA_BOUCHE_TOKEN` (optional): sent in `X-Test-Token`, set it like the voice service's `TEST_ACCESS_TOKEN`.
- `VOIX_BAMBARA_VOIX` (optional): voice id, `gemini_tts` by default.
- `VOIX_BAMBARA_TEXTE_MAX` (optional, 600): maximum size of a chunk read aloud. Set it like the voice service's `TEXTE_MAX`.
- `VOIX_BAMBARA_AUDIO_MAX_MO` (optional, 10): maximum size of a recording.
- `VOIX_BAMBARA_DELAI_S` (optional, 120): maximum wait for a service.

Both services keep their own variables (see `docs/chantiers/TEST_BOUCHE_BAMBARA.md` and the `bambara-ecoute/` folder). The voice service needs `GOOGLE_API_KEY`.

## Data and account deletion

Nothing is stored: no table, no file. Audio and text only pass through. Nothing to add to `core/purge_compte.py` or to the export in `api/profiles.py`.

## Known limits

- Soloni has no access token of its own: its address must not be published, or it must be protected at network level.
- Transcription and voice quality are judged by ear, ideally by a Bambara speaker. No test was run against the real services during development: tests use fake services.
- The frontend side is described in `docs/VOIX_BAMBARA.md` in the classinus-frontend repository.
