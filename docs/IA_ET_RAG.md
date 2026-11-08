# AI providers and document retrieval

[English version] · [Français](IA_ET_RAG.fr.md)

## Chat orchestration

`core/main.py` exposes the entry point for the conversation engine. Orchestration uses specialized modules for prompt construction, history, tool routing, model calls, and persistence.

The default chat path and premium providers are separate paths. Details are in `core/main.py`, `core/fournisseurs_llm.py`, and the related adapters.

## Providers

The repository contains adapters for several provider families, including Groq, Google Gemini, Anthropic Claude, OpenAI, xAI/Grok, DeepSeek, and Meta. A provider is available only when its configuration and credentials are present and access is authorized.

Model IDs and display labels can be configured in Supabase. Catalogues and versions change, so do not hard-code a model list in this documentation as if it were permanent.

Core variables found in the repository:

- `GROQ_API_KEY`
- `GOOGLE_API_KEY`

Additional providers use their own variables. See [`RAILWAY_DEPLOY.md`](./deployment/RAILWAY_DEPLOY.md) for the current operational list.

## Prompt caching and token metering

Every tool step resends the whole context (system prompt, tools, history, tool results) to the model, so input is the dominant cost. Providers only reuse from their cache the **identical beginning** of a request, billed much lower. The first byte that changes makes everything after it billable again.

**Prompt layout** (`core/construction_system_prompt.py`, assembled in `core/main.py`):

1. first system message: the **stable** part (platform, agent page, skills, connections, configuration, memory, modes);
2. the conversation history;
3. second system message: the **variable** part (blocks that depend on the message or the screen, date and time, tool journal, progress note);
4. the current question.

Any new prompt block that changes from one message to the next goes **after** `MARQUEUR_PARTIE_VARIABLE`, never before.

**Per-provider cache**:

| Provider | Mechanism |
|---|---|
| Claude | `cache_control` markers set by `core/adaptateur_claude.py` (last tool, system, end of history, last message). `CLAUDE_CACHE_PROMPT=0` turns it off, `CLAUDE_CACHE_TTL=1h` extends the lifetime (default 5 min) |
| GPT, Grok | automatic cache; a stable `prompt_cache_key` is sent by `core/adaptateur_responses.py`. `CACHE_PROMPT_CLE=0` turns it off |
| Meta, Gemini, DeepSeek, GLM, Qwen, NVIDIA | provider-side automatic cache, nothing to send: only a stable beginning matters |

**Metering** (`core/usage_llm.py`): one `[USAGE]` line per call in the Railway logs: `entree` (input), `cache_lu` (cache read), `cache_ecrit` (cache written), `sortie` (output), `part_cache`, message and tool counts, and three fingerprints (`empreinte_outils`, `empreinte_tete`, `empreinte_debut_historique`). If the fingerprints stay the same between calls but `cache_lu` stays at 0, the cause is on the provider side; if they change, the beginning of our request is moving. Forced-conclusion and re-read calls are not metered yet.

**Tools obtained with `demander_outils`**: the tool list sent to the provider no longer changes during a turn. It comes before the system prompt and the history, so extending it made everything re-read at full price (a third of the tokens not read from cache in the production logs of 2026-11-08). Found tools arrive as a **sheet** (name, role, parameters) in the `demander_outils` result, and the model calls them through the fixed `appeler_outil(nom, arguments)` tool. The server unwraps the call before running it (`deballer_appels_appeler_outil`, in `core/routage_outils.py`): chat cards, approvals, limits, journal and repetition detection only see the real tool. An unknown name or a missing required argument sends the reason back to the model. The tools the turn started with are still called directly, and `garder_outils` keeps an obtained tool for the next message, where it becomes direct. The `garder_outils` definition is fixed (no more `enum` of names): its names are checked server-side by `_valider_noms_a_garder`.

## Tools

Tools are registered and filtered by registry and permission modules, especially `core/registre_outils.py`, `core/mcp_tools.py`, and specialized execution modules. Some calls require explicit approval and server-side safeguards.

## Embeddings and RAG

Two vector-search use cases are distinct:

- `core/retriever.py`: retrieves indexed content used by the AI engine.
- `core/bibliotheque_rag.py`: searches the user's personal file library.

Vectorization and text chunking are shared through `core/embeddings.py`. SQL migrations and related RPC functions are part of the Supabase contract.

## Indexing

Processing and indexing tools are mainly in `indexers/`, `core/`, and `scripts/`. Before adding an indexer, identify its target storage, corresponding vector-search function, and document access rules.
