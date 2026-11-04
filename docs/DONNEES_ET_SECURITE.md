# Data and security

[English version] · [Français](DONNEES_ET_SECURITE.fr.md)

## Supabase

The backend uses Supabase for authentication, PostgreSQL, and associated storage. The core server variables are `SUPABASE_URL` and `SUPABASE_SECRET`.

`SUPABASE_SECRET` is a privileged credential. It must never be exposed to the browser, committed to the repository, or included in a mobile or desktop application.

The frontend uses a separate public anon key. A public key is not a replacement for authentication or database access policies.

## Authentication

Protected routes use backend authentication dependencies, especially those in `api/auth.py`. A user's identity must be derived from the validated token, not from an arbitrary ID supplied in the request body.

Public MCP servers have their own token verification and OAuth configuration, documented in [MCP and connectors](MCP_ET_CONNECTEURS.md).

## RLS and data isolation

Row Level Security (RLS) policies, constraints, and SQL functions are an integral part of data security. They are defined or modified by files in `migrations/`.

Before changing a table or function:

1. Read the existing migrations related to it.
2. Verify RLS policies, foreign keys, constraints, and RPC functions.
3. Add a versioned, repeatable migration whenever possible.
4. Test with an authorized user and with another user who must not have access.
5. Apply the migration to the relevant environment before deploying code that depends on it.

The use of a privileged server role is not a reason to remove application-level access controls.

## Secrets and configuration

AI provider, OAuth, push-notification, and storage secrets are configured in the backend runtime environment. The names and uses found in the repository are tracked in [`RAILWAY_DEPLOY.md`](./deployment/RAILWAY_DEPLOY.md).

Never commit real secrets, put a private key in a frontend `NEXT_PUBLIC_*` variable, return a stored integration token to the client, accept a client-provided `user_id` as proof of identity, or expose data belonging to another account.

## Files and storage

File flows use different modules depending on their source and destination, including uploads, libraries, R2 files, and external file relays. Verify read/write permissions and file ownership whenever adding a route or tool.
