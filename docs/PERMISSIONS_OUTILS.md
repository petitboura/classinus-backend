# Tool permissions

[English version] · [Français](PERMISSIONS_OUTILS.fr.md)

Per-person settings that decide what happens when the AI wants to use a tool of a connected app or of a custom MCP server. Added on 25 November 2026 (branch `feat/permissions-outils`).

## States

- **autoriser**: the tool runs without asking.
- **demander**: the person confirms every time (the chat confirmation card).
- **bloquer**: the tool is not run. The AI receives a clear refusal (French and English, `TEXTE_OUTIL_BLOQUE`) and explains that the tool is blocked and where to turn it back on.

## Categories and priority

Each app has two categories: `lecture` (read only) and `ecriture` (writes or deletes). A setting can be placed on a category or on one tool. Order of precedence: tool, then category, then default.

Defaults are the behavior before the feature: connected app = read allowed, write asked; custom MCP server = everything asked. Actions in `AUTORISATION_PERMANENTE_INTERDITE` can never be `autoriser`.

A group is the app name (`notion`, `vercel_mcp`...) or `custommcp_<6 hex characters of the server id>`. A category key is `categorie:<group>:<lecture|ecriture>`.

## Storage

Table `permissions_outils` (`user_id`, `cle`, `etat`, `nom_lisible`, dates), RLS on, `ON DELETE CASCADE` to `auth.users`. Only explicit settings are stored. Migration: `migrations/2026_11_24_permissions_outils.sql` (it also imports the old "Always allow" rows and the old custom server flag, which are kept but no longer read). The table is in `core/purge_compte.py` and in the data export.

## Code

- `core/permissions_outils.py`: pure logic and database access.
- `core/catalogue_permissions.py`: lists an app's tools and classifies them (read or write).
- `core/execution_outils.py`: `etat_permission_appel` applies the setting in the chat; blocked calls are refused before execution.
- `api/widgets_outils.py`: same rule for calls coming from a widget (`OUTIL_BLOQUE`, HTTP 403).
- `core/autorisations_outils.py`: the chat "Always allow" button writes `autoriser`.

## API

- `GET /api/permissions-outils/{group}`: two categories, each with its setting (`etat`, `etat_effectif`, `par_defaut`) and its tools.
- `PUT /api/permissions-outils/{group}` with `{"cle": ..., "etat": "autoriser" | "demander" | "bloquer" | null}`; `null` removes the setting. A custom server group must belong to the caller.
- Old routes `/api/autorisations-outils` and `/api/mcp-personnalises/{id}/autorisation-non-sensibles` still work.

Error codes (French and English in `core/erreurs.py` and `lib/erreurs.ts`): `OUTIL_BLOQUE`, `PERMISSIONS_OUTILS_*`.

## Tests

`python3 -m pytest test_permissions_outils.py test_permissions_outils_execution.py test_catalogue_permissions.py` (offline).
