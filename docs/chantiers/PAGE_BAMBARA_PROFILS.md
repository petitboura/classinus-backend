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

## Voice sign-up journey (22 November 2026)

The `+` button of the profile panel no longer opens written fields: it starts a full-screen sign-up journey made only of voices and images (frontend `components/bambara/ParcoursInscriptionBambara.tsx`, logic in `lib/useParcoursBambara.ts`).

1. **Name.** A voice asks for the name, the person says it, Soloni transcribes it, and the person can replay their own voice and also the voice of Classinus saying that name (speech synthesis), to hear what it will sound like when Classinus says it.
2. **Woman or man.** Two large pictures to touch, no text.
3. **Introduction (optional).** The person can say a few words about themselves, or skip with an arrow.

At each step a voice explains what to do. **None of those sentences is written in the code**: they are read by speech synthesis from the Supabase table `bambara_parcours_textes`, written by the team. A missing sentence is skipped and the step plays without a voice instruction.

| Key | When it is read |
| --- | --- |
| `nom_demande` | First step, asking for the name. |
| `nom_reecoute` | After the name is transcribed and Classinus has said it, explaining to replay, confirm or redo. |
| `genre_demande` | Second step, asking to choose woman or man. |
| `presentation_demande` | Third step, inviting the person to speak about themselves (optional). |
| `fin` | After the profile is saved. |

Table `bambara_parcours_textes`: `cle`, `langue` (`bm` for Bambara, the language of the voice), `texte` (what the voice reads), `texte_fr` and `texte_en` (what it means, for the team, never read), `actif`. Add or edit rows in Supabase; no deployment is needed.

Storage: `bambara_profils` gets `genre` (`femme` or `homme`) and `presentation` (up to 2000 characters). The spoken name is stored in `prenom` and `nom` is left empty (the check now accepts 0 to 60 characters). Migration: `migrations/2026_11_22_bambara_parcours_inscription.sql`. The new columns follow the profile, so the account purge and the data export already cover them.

Routes: `POST /api/bambara/profils/parcours` (name, `genre`, optional `presentation`) and `GET /api/bambara/parcours/textes?langue=bm`. New error codes `BAMBARA_NOM_PARLE_INVALIDE`, `BAMBARA_PROFIL_GENRE_INVALIDE`, `BAMBARA_PRESENTATION_INVALIDE`, in French and English. Tests: `test_bambara_parcours.py`.
