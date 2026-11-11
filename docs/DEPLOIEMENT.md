# Backend deployment

[English version] · [Français](DEPLOIEMENT.fr.md)

[English version] · [Français](DEPLOIEMENT.fr.md)

## API deployment

The production configuration documented in this repository uses Railway and Railpack:

- `Procfile` defines the Uvicorn command for the API.
- `railpack.json` describes the required system packages.
- `requirements.txt` contains the Python dependencies.
- `api/main.py` is the FastAPI entry point.

The operational checklist and environment-variable list are maintained in [`RAILWAY_DEPLOY.md`](./deployment/RAILWAY_DEPLOY.md). Consult it before changing a service or its configuration, then compare it with the Railway dashboard. This file records configuration observed at a particular time; it is not live access to the infrastructure.

## Separate video montage service

The repository also contains `api/main_montage.py` and `Dockerfile.montage` for the separate montage service. The main backend can delegate montage work to it when `MONTAGE_VIDEO_URL` is configured. The service-specific settings and variables are described in `RAILWAY_DEPLOY.md`.

## Separate Bambara voice service (test)

The repository also contains `api/main_bouche.py` and `Dockerfile.bouche` for a separate Bambara text-to-speech test service. It is not part of the production deployment yet. See [`BOUCHE_BAMBARA.md`](./BOUCHE_BAMBARA.md) for its variables and limits.

## Docker and test environments

The root `Dockerfile` describes a Docker build separate from the Railpack build. Its comments note its use for Docker builds and test environments. Do not assume that the main Railway production deployment uses this Dockerfile; verify the build configuration of the actual service.

## Pre-deployment checklist

1. Verify the branch and commit to deploy.
2. Verify the environment variables for the target environment. Do not copy secrets into Git.
3. Apply the required Supabase migrations before enabling the related code.
4. Verify external services and OAuth callback URLs.
5. Check the build, startup logs, and `/health`.
6. Test sensitive features in the destination environment.

Rolling back the code does not automatically restore the database. Check migration compatibility separately.
