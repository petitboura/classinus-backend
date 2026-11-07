# Permanent instructions for Claude in this repository

[English version] · [Français](CLAUDE.fr.md)

## Never use double hyphens ("--") in user-visible text

Bourama strongly dislikes double hyphens used as a substitute for an em dash in any text shown to a user. In practice, never use them in:
- Error messages returned by the API (`erreur_api`, exceptions, etc.).
- Text returned by MCP tools to the AI for delivery in chat (`core/serveur_mcp_espace.py`, `core/serveur_mcp_generation.py`).
- Any dynamic label, name, or description stored in the database for display (skills, behaviors, plugins, etc.).

They are acceptable in code itself (comments and docstrings), which users do not see. Intentional Markdown separators such as `"\n\n---\n\n"` are also acceptable: they are horizontal rules, not em dashes.

When an em dash would otherwise appear in visible text, use a comma, period, parentheses, or rewrite the sentence. Example fixed on 20 August 2026:
`f"(Source : {nom} -- {url})"` → `f"(Source : {nom}, {url})"`.

This is a standing instruction. Check all user-visible text before delivery without waiting for Bourama to repeat the rule.

## Every new piece of user data must be deleted when the account is deleted

An issue was identified on 12 October 2026: account deletion (`api/profiles.py`, function `supprimer_mon_compte`) removed only a small subset of user data. Almost no tables had foreign keys with cascading deletion to the account, so anything not listed manually remained in the database: library and files, Notion and Google tokens, screen-time data, reminders, QCM answers, and more. Google Play and Tunisian law 2004-63 require the deletion of data associated with an account.

Apply this rule without waiting for Bourama to repeat it. Whenever you create a table, column, or storage file containing user data (columns such as `user_id`, `owner_id`, `proprietaire_id`, `etudiant_id`, `auteur_id`, etc.), include all of the following in the same delivery:

1. Add it to `core/purge_compte.py` (the `_TABLES_SIMPLES` list, or a dedicated step if files or non-cascading links are involved).
2. Add it to the `exporter_mes_donnees` export in `api/profiles.py`.
3. Prefer `ON DELETE CASCADE` to `auth.users` in the migration. Never create a foreign key to an account without cascading deletion; it blocks account deletion and can cause `PROFIL_FERMETURE_PARTIELLE`.
4. Verify the actual database schema (foreign keys and columns), not just the code. Code does not reliably reveal every column.
5. If data is intentionally retained (such as `journal_actions`, which is retained for security), disclose that in the Privacy Policy.

No account-linked table may be delivered without passing these checks.

## Documentation: always up to date, always organized, always translated

Bourama's decision from 4 November 2026. This rule is mandatory: apply it every time, without asking and without waiting for him to repeat it.

- **Always up to date.** Whenever code, behavior, configuration, or a decision changes, update the affected documentation in the same change.
- **Never leave a mess.** Never drop a loose Markdown file at the repository root. Every new document goes in `docs/`, or in a themed subfolder (for example `docs/chantiers/`, `docs/specs/`) once a topic grows. Create a new document or a new folder whenever it keeps things clear; do not ask first.
- **Always organized.** Every new document is added to the index in `docs/README.md` and `docs/README.fr.md` in the same change. When you edit an old document still at the root (see that index), move it into `docs/` and fix every reference to it, in code comments and in other documents.
- **Always translated.** Every document exists in English (default, `.md`) and French (`.fr.md`), with the language switch line at the top of both. Update both versions together, never only one.
- Only `README`, `CLAUDE`, and their `.fr.md` versions stay at the root.
- Never write a secret, token, or password in documentation.


### Operational documentation that must remain beside its source

- Do not move `skills_plateforme/<slug>/SKILL.md` or `SKILL.fr.md`. The synchronization script `scripts/synchroniser_skills_plateforme.py` reads skills from that exact directory structure to publish runtime instructions.
- Do not move `LISEZ_MOI_NE_JAMAIS_REUTILISER.md` or its French companion out of `_desactive_programme/` and `_desactive_roles_hierarchie/`. These are safety markers placed next to disabled code and must remain there.

## Everything user-visible must exist in English, or the work is not finished

Bourama's order from 7 November 2026. It is a rule, not a question: never ask whether to translate.

- Every text a person can read must exist in English as well as French: interface labels, catalogue data (names, descriptions, effect texts), texts prefilled in a field and sent to a model, error messages, and documentation.
- Catalogue and data texts carry their English version next to the French one (for example `descriptionEn`), and the screen picks one from the language chosen in Settings. Backend errors go through a stable code with a French and an English message (`core/erreurs.py` and `lib/erreurs.ts`).
- If a text lives in Supabase, add its English version there too.
- A task that adds or changes visible text without its English version is not finished.
