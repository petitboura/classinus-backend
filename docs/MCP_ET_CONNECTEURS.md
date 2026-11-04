# MCP and connectors

[English version] · [Français](MCP_ET_CONNECTEURS.fr.md)

Classinus uses MCP at two levels: internal servers consumed by its own engines, and public servers that an external client can connect to using the user's identity.

## MCP servers exposed by the API

Mounts are configured in `api/main.py`. Current paths include:

| Path | Purpose |
|---|---|
| `/mcp/generation` | generation tools used by the application |
| `/mcp/execution-code` | code execution |
| `/mcp/video` | video tools |
| `/mcp/github` | GitHub tools |
| `/mcp/netlify` | Netlify tools |
| `/mcp/public` | public MCP server for document resources |
| `/mcp/espace` | public MCP server for the user's space |

Verify paths, transports, and security settings in `api/main.py` and the `core/serveur_mcp_*.py` modules.

## Public MCP and authentication

The public `/mcp/public` and `/mcp/espace` servers rely on Supabase OAuth as described in `core/mcp_auth_public.py`. The token presented by an external client is verified before its calls are associated with an account.

Public configuration uses, among other values, `URL_RESOURCE_SERVER_PUBLIC` and the OAuth callback URL. Enabling OAuth 2.1 / Dynamic Client Registration in Supabase is an operational prerequisite separate from the code. Check [`RAILWAY_DEPLOY.md`](./deployment/RAILWAY_DEPLOY.md) and the Supabase dashboard before activating a new instance.

## Account connectors

Connection routes are organized in `connexions/` and `api/connexions*`. The backend manages OAuth start, status, and completion flows. Account tokens must remain server-side and be stored separately by user and provider.

Providers referenced by the code and migrations include Notion, GitHub, Higgsfield, Vercel, Railway, and Supabase. Availability depends on OAuth configuration and applied migrations.

## Add an integration

1. Review the OAuth or MCP protocol documented by the provider.
2. Add the connection flow and identity verification in the backend.
3. Store tokens server-side with strict per-user isolation.
4. Add the required migrations and verify access policies.
5. Add tests for connection, refresh, and failure cases.
6. Expose the tool to the AI engine only after verifying permissions and sensitive-operation controls.
