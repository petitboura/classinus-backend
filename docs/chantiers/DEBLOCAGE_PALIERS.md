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
- `core/fournisseurs_llm.py`: `ordre_des_paliers()` gives the plan order.
- `migrations/2026_11_25_deblocages_paliers.sql`: the table and the rule comment on `agents`.
- `test_deblocage_paliers.py`: tests with no network access.

## What is NOT done yet

- **The unlocked plan does not change chat model access yet.** Today access comes from `agents.palier_debloque` and `distributeur_debloque`, and the single agent is set to the highest plan: everyone already sees everything. Wiring the person's plan to model access is the next step, to be decided with Bourama (it removes access to higher-plan models for anyone without an unlock).
- Monthly plan credits are not handled here.
- No webhook and no payment provider.
- No screen: the administrator uses the routes or Supabase.

## Known limits

- The email search goes through accounts page by page (up to 10,000 accounts). Beyond that, use `user_id`.
- A person can hold several active unlocks: to shorten an end date, revoke then grant again.
