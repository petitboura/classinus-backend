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
