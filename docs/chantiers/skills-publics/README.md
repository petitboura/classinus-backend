# Public skills (backend)

**English version** · [Version française](README.fr.md)

Chantier of 24 November 2026, requested by Bourama: publish a skill publicly, let the AI search public skills and propose adding one, and let the AI know when the author updates a skill. The author can already edit, delete and share a skill, so the catalogue now rests on the real `skills` table (files in R2) instead of the old `comportements_publics` table.

## How it works

- **Publish.** A skill with `visibilite = 'public'` is in the catalogue. A description is required (it is what makes the skill findable). Withdrawing sets it back to private; copies already added by others stay with them.
- **Add.** Adding creates an independent copy with its own R2 files, tracked in `skill_activations` (source, copy, version copied, sync time).
- **Update.** Each edit of a public skill raises `version_publique`. The copy never changes by itself. The AI warns once (system prompt block "MISES À JOUR DE SKILLS PUBLICS DISPONIBLES"), proposes the update, and replaces the copy only after the user clearly agrees (tool `gerer_comportement_public`, action `mettre_a_jour`). The report says whether the user edited the copy locally.
- **AI tool.** `gerer_comportement_public` actions: `chercher`, `consulter`, `activer`, `publier`, `retirer`, `mises_a_jour`, `mettre_a_jour`. Publish, withdraw and update need platform confirmation (`OUTILS_SENSIBLES`).
- **Routes.** `/api/skills-publics` (search, detail, publish, withdraw, add, updates list, update copy). Old catalogue ids still resolve through `legacy_public_id`.

## Code map

- `core/skills_publics.py`: all the logic, shared by the page and the AI.
- `api/skills_publics.py`: routes. `api/skills.py`: version bump on edit.
- `migrations/2026_11_24_skills_publics.sql`: new columns and `skill_activations`.
- `scripts/migrer_skills_vers_r2.py`: moves legacy rows and relinks the old activations (dry run by default, `--executer` to write).
- Tests: `test_skills_publics.py`, `test_migration_skills.py`.

## Account deletion and export

`skill_activations` is purged with the account (`core/purge_compte.py`) and exported (`skills_publics_ajoutes` in `api/profiles.py`). Foreign keys cascade to `auth.users`.

## Status

Applied on STAGING. Production still needs, in this order: the migration SQL, the migration script (dry run, then `--executer`, needs R2 access), then backend, then frontend. The old table and old route stay until Bourama validates.
