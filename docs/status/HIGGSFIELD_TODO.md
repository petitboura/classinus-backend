# Higgsfield: backend status for branch `feature/higgsfield-catalogue-generation`

[English version] · [Français](HIGGSFIELD_TODO.fr.md)

For frontend status, see the `docs/status/HIGGSFIELD_TODO.md` in `classinus-frontend`.

## Already implemented

- `api/higgsfield.py` is connected in `api/main.py` (router `/api/higgsfield`).
- Schemas: `DemandeVideo`, `Image`, `Genjutsu`, and `Estimation`; rate limit `10/min`; `reserver_generation`; `lancer_generation`, `statut_generation`, `annuler_generation`, and `estimer_cout`.
- Best-effort library save when the job reaches its completed status.

## Remaining backend work (optional before merge)

- Verify `HIGGSFIELD_API_KEY` / `HIGGSFIELD_API_BASE_URL` in the Render/Railway environment (production and staging).
- Verify CORS for R2 upload URLs returned to the frontend.
- Optional: add a Higgsfield webhook if polling proves unreliable. Not a priority.

## Server-side tracking (6 November 2026)

- Every launch (`POST /api/higgsfield/video|image|genjutsu`) is recorded in the `higgsfield_generations` table (migration `migrations/2026_11_06_higgsfield_generations.sql`; RLS on, no policy, rows removed with the account).
- A background loop in `api/main.py` (`_boucle_suivi_higgsfield`, every 5 seconds) runs `core/higgsfield_suivi.py`: it asks Higgsfield for the status, saves the result to the user's library exactly once, then sends the notification (type `action_ia_terminee`, link `/higgsfield`) and the push. It works with the app closed, and a server restart loses nothing because the state lives in the database.
- A generation still running after 2 hours is marked as failed (`delai_depasse`).
- `GET /api/higgsfield/statut/{id}` now reads the database and checks ownership (404 otherwise); the old `titre` parameter and the library save inside this call were removed. New `GET /api/higgsfield/generations` lists the user's recent generations. `POST /annuler/{id}` also checks ownership.
- Account export and purge include the new table.

## Soul 2.0 (7 November 2026)

- `core/higgsfield_catalogue.py`: new image model `soul` (endpoint `higgsfield-ai/soul/v2/standard`, formats 1:1, 9:16, 16:9, 4:3, 3:4, 2:3 and 3:2, quality 720p or 1080p, no reference images). Schema read on docs.higgsfield.ai on 7 November 2026.
- `core/higgsfield_requetes.py`: `construire_requete_image` takes `style_id`. It is accepted only for Soul and must be a UUID; the General style applies when it is empty. Soul refuses reference images, the format `auto` and the qualities `1k` and `2k` with a clear message, and grok refuses `style_id`.
- `api/higgsfield.py`: `POST /api/higgsfield/image` and `POST /api/higgsfield/estimation` accept `style_id`. The defaults of `format_image` and `qualite` are now empty (the default of the model applies), because grok and soul do not share the same values.
- `core/outils_higgsfield.py`: the chat tool `generer_image_higgsfield` knows `soul` and `style_id`, with the same empty defaults.
- Tests: `test_higgsfield_requetes.py`, class `TestRequeteSoul`.
- Not checked: the list of Soul styles (`GET /v1/text2image/soul-styles/v2`) was not called. Only the identifier of the General style is confirmed by the documentation; the two others (Warm ambient and Y2K studio) come from the Higgsfield MCP catalogue.

## English error messages (7 November 2026)

- `core/higgsfield_messages_en.py` translates every `ErreurHiggsfield` message. `api/higgsfield.py` sends the French text as `detail` and the English one as `detail_en` under the stable code `HIGGSFIELD_REQUETE_INVALIDE` (or `HIGGSFIELD_ID_INVALIDE`); the other Higgsfield codes have French and English messages in `core/erreurs.py` and `lib/erreurs.ts` in the frontend.
- The chat tool keeps the French messages: the AI relays them in the language of the conversation.
- Test: `test_higgsfield_messages_en.py` triggers each error and checks that the English version exists.
