# Bambara page: profiles, history and kept items

**English version** · [Version française](PAGE_BAMBARA_PROFILS.fr.md)

Added on 18 November 2026 at Bourama's request, first built on staging and meant to be improved afterwards. The Bambara page (`/bambara` in the frontend) now has a row of buttons at the top: new profile, new conversation (a simple "+"), history, and kept items. Each video and image also has a heart to keep it.

## What is stored

| Table | Content |
| --- | --- |
| `bambara_profils` | A person using the account: last name and first name only. |
| `bambara_conversations` | One row per conversation with its first message (written text, or only a "spoken" flag). |
| `bambara_audios` | The first spoken message of a conversation (WAV in base64, duration, bars of the bubble), kept apart so the history list stays light. |
| `bambara_gardes` | Videos and images kept by a person (type, address, title, thumbnail). |

Migration: `migrations/2026_11_18_page_bambara_profils_historique.sql`. Every table follows the account with `ON DELETE CASCADE`, has row level security on with no policy (only the backend reads and writes), and is part of the account purge (`core/purge_compte.py`). The conversations, profiles and kept items are in the data export; the audio is left out because it is too heavy.

When no profile is chosen, conversations and kept items belong to a shared space of the account (`profil_id` empty).

## Routes (`api/bambara_profils.py`, logic in `core/bambara_profils.py`)

- `GET /api/bambara/profils`, `POST /api/bambara/profils` (last name, first name; 20 profiles at most per account).
- `GET /api/bambara/conversations?profil_id=` lists the 30 latest conversations with their first message.
- `PUT /api/bambara/conversations/{id}/premier-message` keeps the first message once; calling it again changes nothing. The audio is refused beyond about 1.5 MB.
- `GET /api/bambara/conversations/{id}/audio` returns the first spoken message.
- `GET /api/bambara/gardes?profil_id=`, `POST /api/bambara/gardes`, `DELETE /api/bambara/gardes/{id}`. Keeping the same item twice returns the same row.

Errors use stable `BAMBARA_*` codes with French and English messages (`core/erreurs.py`, `lib/erreurs.ts` in the frontend). The page never shows an error on screen.

## Known limits of this first version

- The audio is stored in the database (base64). Moving it to object storage is the durable choice if volume grows.
- The history only lists first messages. Reopening a past conversation is not built.
- Tests: `test_bambara_profils.py`.
