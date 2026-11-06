# Classinus: Backend

[English version] · [Français](README.fr.md)

The backend for **[Classinus](https://classinus.com)**. This repository exposes the FastAPI API used by the frontend and hosts Classinus AI engines, tools, document processing, and MCP services.

The frontend is maintained separately: [classinus-frontend](https://github.com/petitboura/classinus-frontend).

[Français](README.fr.md)

## Hackathon: Vultr Agent Rush ("Blast Radius Zero")

Classinus agents can run code and drive a real web browser. To keep the blast radius at zero, every one of those actions happens inside a sealed box on a **Vultr server**: whatever the model does, or whatever a malicious page tries, it cannot reach a real secret, the internal network, or any site the person did not approve.

### Vultr services used

| Vultr service | What it does here |
|---|---|
| **Cloud Compute** (instance `classinus-vultr`, Frankfurt, 4 vCPU / 8 GB, Ubuntu 24.04) | Control center. Runs the sealed-box service ([`boites_service`](boites_service/README.md)) and the Classinus backend, deployed with **Coolify** (Vultr marketplace app). |
| **Serverless Inference** (OpenAI-compatible API) | The agent's LLM calls: DeepSeek, GLM, Qwen, Nemotron and Muse models, selected in the chat model picker. |
| **Firewall group** | Attached to the server to restrict who can reach the sandbox service port. |

### How a request flows

```
Person -> Classinus chat -> backend API -> Vultr Serverless Inference (model decides which tool to call)
                                   |
                                   v
                    sandbox service on the Vultr server
                      |                          |
              code box (Docker)        browser box (Docker + Chromium/Playwright)
                      \__________________________/
                         egress proxy (allow-list, ports 80/443 only)
```

### Containment (what is enforced on every box)

- One Docker container per conversation, non-root user, all Linux capabilities dropped, `no-new-privileges`, read-only filesystem.
- Memory, swap, CPU, process count and disk limits; every command is killed after its time limit.
- **No secret inside the box**: no Classinus key, no Vultr key. The box only knows its proxy address.
- The box network is internal: no route to the Internet. The only way out is the proxy, domain by domain, ports 80 and 443, public addresses only (no internal network, no link-local range).
- Destroying a box deletes its container and its volume; idle boxes are paused automatically.

Details and the full table: [`boites_service/README.md`](boites_service/README.md).

### Human approval and the allow-list

- The agent is told which sites are reachable (the list is part of the tool description) and asks for access **before** trying any other site.
- A request for a new site shows a confirmation card ("Access to site ..."). The person must confirm; there is no "always allow" for it. Dangerous or malformed domains are refused, and the number of extra domains per conversation is capped.
- In the browser, the final action (sending a form, paying, deleting, publishing) also needs the person's approval before it runs.
- The browser returns screenshots to the vision model so it can check what it sees; failed or empty pages send no image.

### Try it (demo scenario)

1. Ask the agent: "Open wikipedia.org in the browser." Wikipedia is not on the allow-list, so the agent asks for access and you see the confirmation card.
2. Approve: the page opens and the agent describes the screenshot.
3. Ask it to fill and send a form: the agent fills it, then waits for your approval before the final submit. Refuse, and nothing is sent.

### Configuration

| Variable | Purpose |
|---|---|
| `VULTR_INFERENCE_API_KEY` | Vultr Serverless Inference key |
| `VULTR_INFERENCE_BASE_URL` | Optional override of the inference address |
| `EXECUTION_CODE_FOURNISSEUR=docker` | Use the Vultr sandboxes instead of the previous provider |
| `BOITES_URL`, `BOITES_TOKEN` | Address and token of the sandbox service on the Vultr server |

### Known limits

- Files in a box live in memory (tmpfs): restarting the Vultr server erases workspaces.
- The previous sandbox provider (E2B) stays available through configuration so production never depends on a single switch; if Vultr inference refuses a call (credit, quota, key), the call falls back to the usual route for 10 minutes.

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
