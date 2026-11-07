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

## Interactive widgets (MCP-UI and MCP Apps)

An MCP tool can come with an interactive widget (Higgsfield, for example). The backend reads it in `core/ressources_ui.py` and sends it to the frontend as a `ressources_ui` event, separately from the text result, which stays as the fallback. The frontend shows it in an isolated iframe.

A server can announce a widget in two ways, and both are handled:

1. **In the tool result.** A content block whose URI starts with `ui://`. If the block has no content, the backend reads it with `resources/read` on the same session.
2. **On the tool definition (MCP Apps).** The field `_meta.ui.resourceUri`, returned by `tools/list`, with no `ui://` block in the result. The backend keeps this address in the tool's route (`widget_ui_uri`), built from the cached catalogue, so there is no extra network call per tool. After the call, it reads the content with `resources/read`. A `ui://` block present in the result takes priority, and an error result never shows the declared widget.

Rules that apply to both:

- Rendered types: `text/html` (including `text/html;profile=mcp-app`) and `text/uri-list`. Other types are ignored and the text remains.
- Size and count are capped (`CLASSINUS_MCP_UI_HTML_MAX_OCTETS`, `CLASSINUS_MCP_UI_MAX_PAR_RESULTAT`) and the content read has a timeout (`CLASSINUS_MCP_UI_DELAI_LECTURE_SECONDES`).
- The feature can be turned off with `CLASSINUS_MCP_UI_ACTIF=0`. Without a widget, a tool result is never modified.
- Servers added by the user (`connexions/mcp_personnalises.py`) do not display widgets yet.
- The frontend only lets a widget open a link or change its height. Calls to tools from inside a widget are refused.

Tests: `test_ressources_ui.py`.

## Add an integration

1. Review the OAuth or MCP protocol documented by the provider.
2. Add the connection flow and identity verification in the backend.
3. Store tokens server-side with strict per-user isolation.
4. Add the required migrations and verify access policies.
5. Add tests for connection, refresh, and failure cases.
6. Expose the tool to the AI engine only after verifying permissions and sensitive-operation controls.
