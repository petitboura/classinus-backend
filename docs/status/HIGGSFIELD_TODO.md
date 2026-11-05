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
