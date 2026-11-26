# Model unlock for everyone or for a list of addresses

[English version] · [Version française](DEBLOCAGE_MODELES.fr.md)

Added on 26 November 2026 at Bourama's request. An administrator can open **one specific model** to everyone or to a list of email addresses, with or without an end date. It complements the [plan unlock](DEBLOCAGE_PALIERS.md): there a whole plan is unlocked for a person, here a single model.

## What a model unlock does

The model becomes **selectable** (and accepted by the chat) for the targeted people, even if it is:
- above their plan (it is no longer greyed out with the lock), or
- marked "Coming soon", whether the model or its provider.

What is still required, nothing else is bypassed:
- **The API key** of the provider (or the Vultr / Baseten one for models served only by them). Without a key the model stays closed.
- **The provider must be opened by the single agent** (`distributeur_debloque`).
- **The `specialise` plan (early access) is never opened** this way: it stays reserved to the `acces_anticipe_modeles` table.

A model unlock gives that model only: the other models of the same provider or plan stay as before.

## Table `deblocages_modeles`

Row level security is on with no policy: only the backend reads and writes.

| Column | Role |
| --- | --- |
| `modele_id` | The model id (`modeles_llm.modele_id`, for example `claude-opus-5-5`). The code checks it against the configuration, no database constraint. |
| `email` | **Empty = everyone**, including a visitor without an account. Otherwise an address, lowercase with no spaces. It can be added before the person has an account. |
| `accorde_par`, `motif` | Who granted it and why (500 characters at most). |
| `debut`, `expire_le` | Start, and an optional end. Without `expire_le`, the unlock lasts until it is revoked. |
| `revoque_le` | Filled by a revocation. The row stays (history). |

An unlock is **active** when `revoque_le` is empty and `expire_le` is empty or in the future. Unlocks add up: granting one that is already active creates no duplicate.

**Delay**: the backend reads the table with the model configuration (cache of about one minute). An unlock or a revocation takes effect in under a minute.

## Routes (accounts with `profiles.role = 'admin'` only)

| Route | What it does |
| --- | --- |
| `GET /api/admin/deblocages-modeles` (or `?modele_id=...`) | The active unlocks, grouped by model: `tous` (true/false) and the list of `adresses`. |
| `POST /api/admin/deblocages-modeles` | Body: `modele_id`, **a single target**: `tous: true` OR `adresses: [...]` (200 at most per call), then `expire_le` (optional ISO date; without a time zone it is read as UTC) and `motif` (optional). Response: `ajoutes` and `deja_actifs`. |
| `POST /api/admin/deblocages-modeles/revoquer` | Body: `modele_id` and the same target (`tous: true` OR `adresses`). Response: `revoques`. |

Errors use stable `DEBLOCAGE_MODELE_*` and `DEBLOCAGE_*` codes (`core/erreurs.py`), in French and English.

## Unlock from the Supabase dashboard

Insert a row in `deblocages_modeles`: `modele_id`, and `email` (leave empty for everyone), plus `expire_le` if needed. To revoke, fill `revoque_le`. Note: through Supabase, the check that the model exists and that the address is well written is not done (the database only enforces lowercase with no spaces).

## Personal data

The table holds email addresses. When an account is deleted, the rows of its address are deleted (`core/purge_compte.py`, `_purger_deblocages_modeles`) and they appear in its data export (`api/profiles.py`). "Everyone" rows (empty address) are tied to nobody and stay.

## Code

- `core/fournisseurs_llm.py`: `_lire_deblocages_modeles` (read with the configuration), `modeles_disponibles_pour_agent` (the unlock is applied there), `ids_des_modeles`.
- `core/deblocage_modeles.py`: writing and reading the table.
- `api/deblocage_modeles.py`: the HTTP layer.
- `migrations/2026_11_26_deblocages_modeles.sql`: the table.
- `test_deblocage_modeles.py`: tests with no network access.

## Known limits

- No screen: the administrator uses the routes or Supabase.
- There is no way to unlock "all models of a provider" at once: an unlock targets one model.
- The per-provider early access list (`acces_anticipe_modeles`) stays separate and is unchanged.
