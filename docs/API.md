# Classinus API

[English version] · [Français](API.fr.md)

[English version] · [Français](API.fr.md)

## Entry point

The FastAPI application is created in `api/main.py`. Application routes are mounted through dedicated routers. Exact paths must be checked in the relevant router: this guide describes functional areas rather than duplicating a route list that changes with the code.

The public health endpoint is `GET /health`. `GET /health/me` requires user authentication.

## Exposed domains

| Domain | Main modules |
|---|---|
| Chat and conversations | `api/chat.py`, `api/historique.py`, active-mode, persona, and guide routes |
| Accounts and profiles | `api/auth.py`, `api/profiles.py`, `api/agents.py` |
| Files and documents | `api/uploads.py`, `api/fichiers_r2.py`, `api/fichiers_archive.py`, `api/fichiers_externes.py` |
| Libraries | `api/bibliotheque_utilisateur.py`, `api/bibliotheque_publique.py`, folders, comments, stars, and counters |
| Memory, behaviors, and skills | `api/memoire_eleve.py`, `api/comportements_etudiants.py`, `api/skills.py` |
| Generation and media | `api/generation.py`, `api/higgsfield.py`, `api/rendu_animation.py`, link previews |
| Connections | `api/connexions.py`, `api/connexions_notion.py`, `api/connexions_github.py` |
| Real-time and devices | real-time channel, application-agent channel, Gemini Live, and mobile devices |
| Notifications and reminders | `api/notifications.py`, `api/notifications_push.py`, timers |
| Feedback and moderation | feedback, reports, and audits |

The exact set of mounted routers is listed in the application assembly section of `api/main.py`.

## MCP servers

MCP services are exposed on paths separate from the REST API. Their list and authentication modes are described in [MCP and connectors](MCP_ET_CONNECTEURS.md).

## Image download unlocked by sharing (Higgsfield)

A generated image can only be downloaded once the app reports a finished share. Videos are never locked.

- `POST /api/higgsfield/partage-termine/{request_id}`: the app reports the finished share of a finished image. Records `partage_termine_a` on the generation row.
- `GET /api/higgsfield/telecharger/{request_id}`: returns the file as an attachment. An image that was not shared gets `403 TELECHARGEMENT_PARTAGE_REQUIS`.
- `GET /api/higgsfield/statut/{request_id}` and `GET /api/higgsfield/generations` now include `telechargement_debloque`.

The signal comes from the app: it pushes people to share, it does not protect a secret. Logic lives in `core/higgsfield_telechargement.py`; migration `migrations/2026_11_09_higgsfield_partage_telechargement.sql`.

## Add or modify a route

1. Identify the functional domain and existing router in `api/`.
2. Put reusable logic in `core/` rather than concentrating business logic in the router.
3. Apply the appropriate authentication and derive identity from the authenticated context.
4. Add or update the related tests.
5. If the change affects the Supabase schema, add a SQL migration in `migrations/` and apply it to the target environment before relying on it.
