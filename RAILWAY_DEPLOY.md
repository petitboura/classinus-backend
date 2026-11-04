# Railway deployment checklist

[English version] · [Français](RAILWAY_DEPLOY.fr.md)

Prepared by inspecting the actual code (searching for `get_secret("...")` throughout the repository) and the actual Railway configuration of the `web` service (project `adequate-joy`, domain `web-production-16d21.up.railway.app`). This was not guessed.

Since Streamlit was fully removed on 25 July 2026, this repository has only one production service: the FastAPI API (`api/main.py`), built by Railpack (`railpack.json` at the repository root; `nixpacks.toml` no longer exists).

[English version] · [Français](RAILWAY_DEPLOY.fr.md)

## Environment variables currently configured on Railway

| Variable | Used by |
|---|---|
| `SUPABASE_URL` | Entire project (13 files) |
| `SUPABASE_SECRET` | Entire project (13 files) |
| `GROQ_API_KEY` | `core/main.py`, `core/proactivite.py`, `core/generation_audio.py`, `api/uploads.py` |
| `GOOGLE_API_KEY` | `core/main.py` (Gemini fallback), `core/embeddings.py` |
| `NOTION_TOKEN` | `indexers/index_notion.py`, `core/diagnostic.py`, `core/configuration.py` |
| `GITHUB_TOKEN` | `core/main.py`, `core/serveur_mcp_github.py` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | `connexions/oauth_generique.py`, `core/main.py` (per-agent GitHub OAuth connection) |
| `TAVILY_API_KEY` | `core/registre_outils.py` (web search tool) |
| `CLOUDCONVERT_API_KEY` | `core/conversion_pdf.py` (Word/Excel/PowerPoint PDF previews) |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY_PEM_B64` | `core/notifications_push.py` (generated once with `scripts/generer_cles_vapid.py`) |
| `VERCEL_API_TOKEN` | `core/generation_site.py` (deployment of generated websites) |
| `URL_RETOUR_APP` | `connexions/notion.py`, `connexions/oauth_generique.py`, `api/agents.py` (OAuth callback; must match the actual public API deployment URL) |
| `RAILPACK_BUILD_APT_PACKAGES` / `RAILPACK_DEPLOY_APT_PACKAGES` | Native Railpack configuration (see `railpack.json`) |
| `RAILPACK_PYTHON_PLAYWRIGHT_INSTALL` | Set to `1` to install the browser used for animation video rendering (`core/rendu_animation_processus.py`). Railpack no longer does this by default since version 0.35. |

## Optional variable: class-tech tool server URL

- `CLASSTECH_URL_MCP`: full address of the diagnostic MCP server, read by `core/registre_outils.py`. If missing or empty, the default is `https://class-tech.up.railway.app/mcp/diagnostic` (the `class-tech` service in the Granink project). Set it only if the server address changes. On the class-tech side, `MCP_HOTE_PUBLIC` must contain the public host; otherwise the server rejects calls as DNS-rebinding protection.

## Variable to add before enabling E2B

- `E2B_API_KEY`: E2B server key, read by `core/outils_execution_code.py`. Configure it only on Railway, never in the frontend.

Before enabling this branch, run `migrations/2026_10_23_execution_code_e2b.sql` in the correct Supabase project and verify that `gerer_execution_code` is enabled in `registre_outils_plateforme`.

The USD 100 cap is an application-level safeguard based on estimated cost. It does not replace a billing limit configured directly with E2B. Classinus does not impose an arbitrary concurrency cap; the E2B account's capacity limits are authoritative.

## Configured variable intentionally unused by the code

- `HF_API_TOKEN`: present on Railway, but currently not referenced anywhere in the code. Hugging Face integration is planned but not connected yet. A payment method/card is required to enable it on Hugging Face, and that is not available yet. Leave the variable as it is for now and revisit it when a payment method is available.

## Obsolete variables (do not carry them forward)

These are no longer read anywhere in the current code:

- `OPENROUTER_API_KEY` (replaced by `GOOGLE_API_KEY` during the Gemini migration).
- `NOTION_PAGE_ID` (replaced by the `agents.notion_page_id` column for multi-agent support).
- `AGENT_ID` (previously a fallback secret before multi-agent support; the app now gets the agent from the authenticated user, not from a URL).

## Railway configuration files in this repository

- `Procfile`: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`.
- `railpack.json`: system apt packages (ffmpeg for video extraction, Pango/Cairo/GDK-Pixbuf for WeasyPrint).
- `requirements.txt`: the single Python dependency file at the repository root.

## Open item recorded in this document

The per-agent subdomain (`son-agent.djiguigne.com`) requires a wildcard DNS record (`*.djiguigne.com`) after the custom domain is connected to Railway. The app would also need to read the agent from the request subdomain instead of the authenticated user. This work has not started.

## Separate video montage service (3 November 2026)

A second Railway service uses the same repository and the `main` branch. It handles video montage only, so the main chat service is no longer slowed down by montage work.

- **Build:** set `RAILWAY_DOCKERFILE_PATH=Dockerfile.montage` on this service. Slow dependencies (ffmpeg, Node, Remotion packages, and the Remotion rendering browser) are installed while building the image.
- **Service variables:** `SUPABASE_URL`, `SUPABASE_SECRET` (the same internal token as the main service), and the main service's R2 variables for video storage. Optional: `MONTAGE_SIMULTANES` (default 2), `MONTAGE_ATTENTE_MAX_S` (default 600).
- **Connection:** set `MONTAGE_VIDEO_URL` on the main service to the montage service's address without a path, for example `http://service-name.railway.internal:8000`. Without this variable, montage runs in the main service as before. Removing the variable is enough to revert.
- Heavy AI tools (Whisper transcription, Demucs separation, Real-ESRGAN) are not included.
- The montage service must also deploy the `main` branch.
