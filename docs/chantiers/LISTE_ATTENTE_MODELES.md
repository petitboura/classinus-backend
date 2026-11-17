# Waiting list for "Coming soon" models

**English version** · [Version française](LISTE_ATTENTE_MODELES.fr.md)

Added on 16 November 2026 at Bourama's request. A fake door measures real demand before Claude, GPT and Gemini are plugged in. In the model picker these models appear greyed out with the "Coming soon" label. A click opens a sign up form for a paid waiting list. **No payment is taken**, and the form says so.

## What the form asks

The person must be signed in, so the email comes from the account. The form asks for a plan (Pro 10, Max 17 or Ultra 20 dollars per month, open to everyone), a profile (student, administration or developer), a consent tick, and two optional fields: country and WhatsApp. Plans and texts are not hard coded:

- Plans live in the `paliers_liste_attente` table (price, monthly credit, order, active flag).
- Form texts live in `textes_modeles_llm` under keys starting with `attente_`, in French and English.

## Tables

All three tables have row level security on and no policy: only the backend (Supabase secret key) reads and writes them. Rows linked to an account use `ON DELETE CASCADE` to `auth.users`, and are also listed in `core/purge_compte.py` and in the data export of `api/profiles.py`.

| Table | Role |
| --- | --- |
| `paliers_liste_attente` | The plans shown in the form. |
| `liste_attente_modeles` | ONE waiting list: one row per user (Bourama's decision of 17 November 2026, not one list per model). `modele_id` keeps the model clicked at sign up (the model of origin) and never changes afterwards. Unique on `user_id`. |
| `evenements_liste_attente` | The four funnel steps, for investor figures. |

The funnel steps are, in order: `selecteur_ouvert`, `modele_grise_clique`, `formulaire_ouvert`, `inscription_validee`. The last one is written only by the sign up itself, never by the client.

## Routes

All routes need a signed in user (`/api/liste-attente`).

| Route | What it does |
| --- | --- |
| `GET /config` | Plans, texts (French and English) and the user's active sign up (`inscription`, or null). |
| `POST /` | Creates the user's sign up, or updates it if there is one already (the model of origin is kept). |
| `POST /desinscription` | Marks the user's sign up as `desinscrit` and erases the WhatsApp number. No body needed. |
| `POST /evenement` | Records one funnel step. |

Errors use stable codes (`LISTE_ATTENTE_*` in `core/erreurs.py`) with a French and an English message.

## Code

- `core/liste_attente.py`: all the logic.
- `api/liste_attente.py`: the HTTP layer.
- `migrations/2026_11_16_liste_attente_modeles.sql`: tables, plans and texts.
- `migrations/2026_11_17_liste_attente_unique.sql`: one row per user, plan names (Pro, Max, Ultra), plan points and the texts rewritten for a single list.
- `test_liste_attente.py`: tests without network access.

## Reading the figures

Bourama reads the data from the Supabase dashboard (the backend key bypasses the row security). The most convincing figure is the conversion rate at each step, split by model clicked, plan chosen, profile and country.

## Known limits

- The model identifier is not checked against the catalogue: anyone signed in could send an unknown model name. It only creates a row for that person.
- The 30 addresses of `acces_anticipe_modeles` already see the models, so they never get a greyed out model and never reach the form.
- A legal check is still needed before a public launch, because the rules differ by country.
