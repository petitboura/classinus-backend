# Plan unlock per person

[English version] · [Version française](DEBLOCAGE_PALIERS.fr.md)

Added on 25 November 2026 at Bourama's request. An administrator can unlock a person's plan, with or without an end date. Later, a payment webhook will call the same function: **no payment method is connected in this step.**

## Rule: Classinus has exactly one agent

Classinus is not a multi-agent platform. There is **one single agent**. A plan, a subscription or an unlock belongs to **the person**, never to an agent. The rule is written in three places so nobody has to ask again: the comment on the `agents` table in Supabase, `CLAUDE.md` (and `CLAUDE.fr.md`), and this document.

## Table `deblocages_paliers`

Row level security is on with no policy: only the backend (Supabase secret key) reads and writes. `ON DELETE CASCADE` to `auth.users`, and the table is listed in `core/purge_compte.py` and in the data export (`api/profiles.py`).

| Column | Role |
| --- | --- |
| `user_id` | The person who receives the plan. |
| `palier` | A plan name from `modeles_llm.palier` (essentiel, pro, premium, max, ultra). No database constraint: the code validates it, so adding a plan needs no migration. |
| `source` | `manuel` today, `paiement` once the webhook exists. |
| `accorde_par`, `motif` | Who granted it and why (500 characters at most). |
| `debut`, `expire_le` | Start, and an optional end. Without `expire_le`, the unlock lasts until it is revoked. |
| `revoque_le` | Filled by a revocation. The row stays (history). |

An unlock is **active** when `revoque_le` is empty and `expire_le` is empty or in the future. A person's plan is the **highest** of their active unlocks, in the plan order of the Supabase configuration. Unlocks add up: granting a new one removes none.

## Routes (accounts with `profiles.role = 'admin'` only)

All require a sign-in token. To name the person, give either `user_id` or `email` (only one of the two).

| Route | What it does |
| --- | --- |
| `GET /api/admin/deblocages-paliers?user_id=...` or `?email=...` | The active unlocks and the highest unlocked plan (`palier_debloque`). |
| `POST /api/admin/deblocages-paliers` | Body: `user_id` or `email`, `palier`, `expire_le` (optional ISO date; without a time zone it is read as UTC), `motif` (optional). Grants the plan. |
| `POST /api/admin/deblocages-paliers/revoquer` | Body: `user_id` or `email`. Revokes all the person's active unlocks. |

Errors use stable `DEBLOCAGE_*` codes (`core/erreurs.py`) with a French and an English message.

## Unlock from the Supabase dashboard

Without using the route, insert a row in `deblocages_paliers`: `user_id`, `palier`, and `expire_le` if needed. Leave `source` as `manuel` (the default). To revoke, fill `revoque_le`.

## Naming an administrator

The routes require `profiles.role = 'admin'` for the calling account. No account has this role by default: set it by hand in the `profiles` table.

## Code

- `core/deblocage_paliers.py`: all the logic (`debloquer`, `revoquer`, `deblocages_actifs`, `palier_debloque_de`, `etat`). The future webhook will call `debloquer(..., source="paiement")`.
- `api/deblocage_paliers.py`: the HTTP layer.
- `core/fournisseurs_llm.py`: `ordre_des_paliers()` gives the plan order; `modeles_bientot_pour_agent(..., avec_verrous_palier=True)` adds the locked models.
- `migrations/2026_11_25_deblocages_paliers.sql`: the table and the rule comment on `agents`.
- `test_deblocage_paliers.py`: tests with no network access.

## Model access: the person's plan

Decided by Bourama on 25 November 2026: **everyone sees all models and all plans**, those above their subscription are **greyed out with the lock** (like "Coming soon" models; the Max badge stays as it is today), and each person only gets what their plan allows.

- **Which plan?** The person's highest active unlock (`core/deblocage_paliers.py`, `palier_pour_modeles`). Without an unlock, a visitor with no account or a person with no subscription gets the **lowest plan**. If the database does not answer, we also fall back to the lowest: we never give more than we know.
- **The list** (`GET /api/agents/{id}`, `api/agents.py`): `modeles_disponibles` holds what the person's plan lets them choose. `modeles_bientot` holds the "Coming soon" models **and** those from a plan above theirs (same shape, so the frontend shows them greyed with the lock with no change; a click opens the same flow as today). Function: `modeles_bientot_pour_agent(..., avec_verrous_palier=True)` in `core/fournisseurs_llm.py`.
- **The check** (`api/chat.py`, `_resoudre_modele_force`): the model sent by the client is revalidated server side with the person's plan. A greyed model can never be forced.
- **The agent's plan** (`agents.palier_debloque`) no longer decides people's access: there is only one agent. `distributeur_debloque` is still read (it says which providers are open). The agent creation and edit screens (creator only) are unchanged.
- **The `specialise` plan** (early access) is never granted by an unlock: it stays reserved to the `acces_anticipe_modeles` table.

## What is NOT done yet

- Monthly plan credits are not handled here.
- No webhook and no payment provider.
- No screen: the administrator uses the routes or Supabase.

## Known limits

- The email search goes through accounts page by page (up to 10,000 accounts). Beyond that, use `user_id`.
- A person can hold several active unlocks: to shorten an end date, revoke then grant again.
