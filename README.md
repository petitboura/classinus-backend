# Classinus: Backend

[English version] · [Français](README.fr.md)

The backend for **[Classinus](https://classinus.com)**. This repository exposes the FastAPI API used by the frontend and hosts Classinus AI engines, tools, document processing, and MCP services.

The frontend is maintained separately: [classinus-frontend](https://github.com/petitboura/classinus-frontend).

[Français](README.fr.md)

## Responsibilities

- Application API and authentication.
- AI conversations, provider selection, and tool calls.
- Document search and RAG over indexed content and libraries.
- Account, history, file, notes, behavior, and skill management.
- OAuth connections and integrations with external services.
- Internal MCP services and public MCP servers.
- Media features, notifications, voice, and the live channel.

## Technical architecture

FastAPI · Python · Supabase (Auth, PostgreSQL, and storage) · MCP · AI providers · file and rendering services.

The API entry point is `api/main.py`. HTTP routes are organized in `api/`, while business logic and engines are mainly in `core/`.

## Run locally

Requirements: Python, pip, and a Supabase project configured for the target environment.

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required environment variables, then start the API:

```bash
uvicorn api.main:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health).

## Configuration

The basic service relies in particular on:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SECRET` | Supabase server secret; keep it on the backend only |
| `GROQ_API_KEY` | AI provider used by the main chat path |
| `GOOGLE_API_KEY` | Gemini and content embeddings |

Additional variables enable providers, connectors, notifications, and specialized services. The operational list is maintained in [docs/deployment/RAILWAY_DEPLOY.md](docs/deployment/RAILWAY_DEPLOY.md). Never publish secret values in this repository.

## Documentation

Full documentation index: [English](docs/README.md) · [Français](docs/README.fr.md).


| Guide | What it covers |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) · [Français](docs/ARCHITECTURE.fr.md) | API, engines, and service organization |
| [API](docs/API.md) · [Français](docs/API.fr.md) | Functional domains and routes |
| [AI and RAG](docs/IA_ET_RAG.md) · [Français](docs/IA_ET_RAG.fr.md) | Providers, orchestration, embeddings, and document search |
| [MCP and connectors](docs/MCP_ET_CONNECTEURS.md) · [Français](docs/MCP_ET_CONNECTEURS.fr.md) | MCP servers, OAuth, and integrations |
| [Data and security](docs/DONNEES_ET_SECURITE.md) · [Français](docs/DONNEES_ET_SECURITE.fr.md) | Supabase, migrations, authentication, and secrets |
| [Development](docs/DEVELOPPEMENT.md) · [Français](docs/DEVELOPPEMENT.fr.md) | Local environment, commands, and tests |
| [Deployment](docs/DEPLOIEMENT.md) · [Français](docs/DEPLOIEMENT.fr.md) | Railpack, Railway, and related services |
| [Technical code map](docs/CARTOGRAPHIE_TECHNIQUE.md) · [Français](docs/CARTOGRAPHIE_TECHNIQUE.fr.md) | Where to find code by feature |
| [Railway deployment checklist](docs/deployment/RAILWAY_DEPLOY.md) · [Français](docs/deployment/RAILWAY_DEPLOY.fr.md) | Environment variables and operational setup |

## Related repositories

- **Frontend:** [petitboura/classinus-frontend](https://github.com/petitboura/classinus-frontend)
- **Backend, this repository:** [petitboura/classinus-backend](https://github.com/petitboura/classinus-backend)
