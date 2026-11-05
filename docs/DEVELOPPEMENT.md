# Backend development

[English version] · [Français](DEVELOPPEMENT.fr.md)

[English version] · [Français](DEVELOPPEMENT.fr.md)

## Prerequisites

- Python and pip.
- A Supabase project dedicated to the development environment.
- Credentials for the services required by the feature being tested.

## Install dependencies

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

## Environment variables

The repository does not use one shared example file for every integration. Configure values in the local environment and never commit them.

The core variables for starting the service are `SUPABASE_URL`, `SUPABASE_SECRET`, `GROQ_API_KEY`, and `GOOGLE_API_KEY`. Providers, OAuth connections, notifications, and media services require additional variables. See [`RAILWAY_DEPLOY.md`](./deployment/RAILWAY_DEPLOY.md) and the relevant module's code.

## Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

Check [http://localhost:8000/health](http://localhost:8000/health).

## Tests and checks

Tests are split between `tests/` and root-level `test_*.py` files. Run the test for the changed domain, followed by relevant regression tests.

A dedicated pre-deployment script is available:

```bash
python scripts/predeploiement.py
```

This script performs configured pre-deployment operations, including official-skill synchronization and a Gemini Live check. It does not replace the full test suite or migration validation.

## Change the schema

PostgreSQL changes must be described in a versioned SQL file under `migrations/`. Apply the migration to the target environment, then verify route behavior and RLS policies before deploying code that depends on the change.
