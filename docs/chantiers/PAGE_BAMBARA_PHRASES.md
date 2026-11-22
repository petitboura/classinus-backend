# Bambara page: proactive phrases

**English version** · [Version française](PAGE_BAMBARA_PHRASES.fr.md)

Added on 22 November 2026 at Bourama's request, first built on staging. The Bambara page (`/bambara` in the frontend) used to stay silent until the person spoke, and while a tool worked nothing was said. The page now speaks on its own at six moments, so the person never faces silence. The person cannot read, so these phrases are spoken, never written on screen.

## The six moments

| Moment (`moment`) | When it plays |
| --- | --- |
| `accueil` | When the person arrives on the page. |
| `recherche_web` | When the AI starts a web search. |
| `recherche_videos` | When the AI starts searching or reading videos. |
| `recherche_images` | When the AI starts searching images. |
| `creation_image` | When the AI starts creating an image. |
| `outil_lent` | When a tool takes time: after a delay, then again at every interval, as long as a tool is still working. |

The memory tools have no phrase of their own, they are fast. Each tool moment plays at most once per request, the welcome once per visit, and only `outil_lent` can repeat.

## Where the texts live (Supabase)

Nothing is written in the code: not the phrases, not the delays. Two tables, shared by all accounts (no account data, so nothing to add to the account purge or to the export). Migration: `migrations/2026_11_22_page_bambara_phrases_proactives.sql`. Both tables have row level security on with no policy: only the backend reads and writes.

| Table | Content |
| --- | --- |
| `bambara_phrases_proactives` | One row per phrase: `moment`, `texte` (Bambara, read aloud), `texte_en` (English translation for the team), `actif`, and the stored audio (`audio_base64`, `audio_duree_ms`, `audio_empreinte`). |
| `bambara_phrases_reglages` | A single row: `delai_outil_lent_s` (6 by default) and `intervalle_outil_lent_s` (12 by default). |

Several phrases for the same moment are variants: the page draws one at random and never repeats the one that just played when there are several.

To add a phrase, insert a row. The audio is made by itself:

```sql
insert into public.bambara_phrases_proactives (moment, texte, texte_en)
values ('accueil', '<phrase in Bambara>', '<English translation>');

update public.bambara_phrases_reglages set delai_outil_lent_s = 6, intervalle_outil_lent_s = 12;
```

To remove a phrase without deleting it, set `actif` to false. The migration seeds no phrase: the Bambara texts are chosen and checked by Bourama.

## How the audio is made (the voice is a variable)

The voice is the same variable as the rest of the page, `VOIX_BAMBARA_VOIX` (`gemini_tts` by default, see `docs/chantiers/VOIX_BAMBARA.md`). Changing the variable changes the voice of all the phrases.

The audio is not made at every visit. The first time a phrase is requested, the server has the TTS read it once (`api/voix_bambara.py`, function `synthetiser_texte`, also used by the usual synthesis route) and keeps the file beside the text. `audio_empreinte` records the voice and the text it was made with:

- If the text or the voice changes, the audio is no longer valid and is redone by itself, in the background. A database trigger also clears it when `texte` is edited directly in Supabase.
- A phrase is offered again only once its audio is ready with the current voice and text.
- A phrase that fails is not retried for 60 seconds, and never stops the others.

## Routes (`api/bambara_phrases.py`, logic in `core/phrases_bambara.py`)

- `GET /api/bambara/phrases` returns the ready phrases (`id`, `moment`, `duree_ms`, `version`), the delays (`reglages`) and `en_preparation`, the number of phrases whose audio is being made. The audio is not in this answer, it is heavy. If some audio is missing, it is made in the background after the answer.
- `GET /api/bambara/phrases/{id}/audio?v={version}` returns the WAV file of a ready phrase, with `Cache-Control: private, max-age=31536000, immutable`: the browser keeps it, and `v` changes when the voice or the text changes. A phrase that is not ready, or was made with another voice, answers 404.

New error codes, in French and English (`core/erreurs.py`, `lib/erreurs.ts`): `BAMBARA_PHRASE_INTROUVABLE`. The frontend never shows an error: a phrase that cannot play is skipped.

## How the frontend plays them (see `docs/VOIX_BAMBARA.md` of the frontend repository)

- The page downloads one variant per moment in the background, the welcome first, one at a time so a slow connection is not slowed down further. The next variant is prepared as soon as one has played.
- A phrase is never cut by the arrival of the answer: the answer waits for the end of the phrase that is speaking. Only an explicit gesture of the person (stop, new conversation, replaying a message, starting a video, sending a written message) stops it.
- Phrases never overlap: one speaks at a time, the others wait their turn, and those that no longer make sense (the tool has finished) are removed before they start. The microphone is paused while a phrase speaks.
- The welcome is skipped, never delayed, if the browser does not allow sound yet or if the person touches the screen before it starts.

## Limits

- No phrase is seeded: until rows are added in Supabase, the page stays silent as before.
- The first visit after a phrase is added or its voice changes may not have its audio yet (it is made in the background). The page asks again up to three times, ten seconds apart.
- Some browsers, mostly on iPhone, only allow sound after a touch: the welcome may not play there.
- No test was run against the real TTS service during development. The Supabase migration was applied to the staging project only.

Tests: `python -m unittest test_phrases_bambara` (backend) and `npm run test:phrases-bambara` (frontend).
