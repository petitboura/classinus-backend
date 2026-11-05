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

## Tools

Tools are registered and filtered by registry and permission modules, especially `core/registre_outils.py`, `core/mcp_tools.py`, and specialized execution modules. Some calls require explicit approval and server-side safeguards.

## Embeddings and RAG

Two vector-search use cases are distinct:

- `core/retriever.py`: retrieves indexed content used by the AI engine.
- `core/bibliotheque_rag.py`: searches the user's personal file library.

Vectorization and text chunking are shared through `core/embeddings.py`. SQL migrations and related RPC functions are part of the Supabase contract.

## Indexing

Processing and indexing tools are mainly in `indexers/`, `core/`, and `scripts/`. Before adding an indexer, identify its target storage, corresponding vector-search function, and document access rules.
