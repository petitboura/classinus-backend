# Backend technical code map

[English version] · [Français](CARTOGRAPHIE_TECHNIQUE.fr.md)

[English version] · [Français](CARTOGRAPHIE_TECHNIQUE.fr.md)

This page is a navigation map of the codebase. It groups modules by responsibility and shows where to start for different kinds of changes. Exhaustive file lists and chronological notes are intentionally avoided.

## Find the right place quickly

| What you want to change | Start here |
|---|---|
| HTTP route | **api/**, then the relevant router |
| Chat behavior | **api/chat.py**, **core/main.py** |
| Prompt and context | **core/construction_system_prompt.py**, **core/configuration.py** |
| AI provider | **core/fournisseurs_llm.py**, **core/adaptateur_*.py** |
| Tool available to the AI | **core/registre_outils.py**, **core/mcp_tools.py** |
| Document search | **core/embeddings.py**, **core/retriever.py**, **core/bibliotheque_rag.py** |
| Files and storage | **api/uploads.py**, **core/bibliotheque_fichiers.py**, **core/stockage_r2.py** |
| OAuth or MCP connector | **connexions/**, **core/serveur_mcp_*.py** |
| Mobile or real-time feature | **api/canal_*.py**, **core/canal_*.py** |
| Video and media processing | **api/main_montage.py**, **api/rendu_animation.py**, **core/generation_*** |
| Supabase schema | **migrations/** |
| Background task | **api/main.py**, then the task's module |

## 1. Overall architecture

The typical request path is:

**Classinus frontend → FastAPI API → domain router → business logic in core/ → Supabase and external services.**

The entry point is **api/main.py**. It creates the FastAPI application, configures middleware, starts lifecycle tasks, and mounts HTTP routers and MCP transports.

## 2. Main repository areas

| Directory | Role |
|---|---|
| **api/** | HTTP entry points and application assembly |
| **core/** | business logic, AI orchestration, tools, RAG, storage, and tasks |
| **connexions/** | OAuth and connections to external services |
| **indexers/** | document and content indexing |
| **migrations/** | Supabase schema changes |
| **scripts/** | operations, synchronization, and checks |
| **skills_plateforme/** | official Classinus skills |
| **tests/** and **test_*.py** files | unit tests and regression scenarios |

## 3. Conversation lifecycle

1. **API entry:** **api/chat.py** receives the request and manages the response stream.
2. **Engine:** **core/main.py** orchestrates the conversation turn.
3. **Context:** **core/construction_system_prompt.py**, **core/historique_conversation.py**, and configuration modules prepare the required information.
4. **Model and tools:** **core/fournisseurs_llm.py**, adapters, and routing modules select generation and authorized tools.
5. **Persistence:** **core/persistance_echanges.py** and **core/persistance_tours.py** handle storage and continuity.

The processing is split across multiple modules. Change the dedicated module for the relevant step instead of concentrating all logic in the HTTP router or main engine.

## 4. Functional domains

### API and accounts

Routers live in **api/**. They cover profiles, authentication, chat, history, libraries, files, behaviors, memory, connections, notifications, and real-time features.

To add an endpoint, start from the router for the relevant domain and place reusable logic in **core/**.

### AI engine and adapters

- **core/main.py:** chat orchestration.
- **core/boucle_agent.py:** agent execution loop.
- **core/construction_system_prompt.py:** prompt preparation.
- **core/fournisseurs_llm.py:** provider availability and routing.
- **core/adaptateur_*.py**, **core/clients_outils_llm.py:** provider API adapters.
- **core/efforts_modeles.py:** model reasoning-effort levels.

Provider availability depends on configuration, credentials, and access rules. The model catalogue can change independently of the code.

### Tools and permissions

- **core/registre_outils.py:** tool catalogue.
- **core/mcp_tools.py:** discovery and calls to external MCP tools.
- **core/autorisations_outils.py**, **core/execution_outils.py:** permissions and execution. Actions listed in `AUTORISATION_PERMANENTE_INTERDITE` (`core/registre_outils.py`: the final browser action and network access from the code box) always ask for confirmation: no "Always allow" button, nothing saved, and any stored permission for them is ignored.
- **core/outils_*.py:** capabilities grouped by domain.

Sensitive operations must retain their confirmation controls and server-side checks.

### Documents, library, and search

| Need | Modules |
|---|---|
| Embeddings and chunking | **core/embeddings.py** |
| Engine document retrieval | **core/retriever.py** |
| Personal-library RAG | **core/bibliotheque_rag.py** |
| Public-catalogue RAG | **core/catalogue_public_rag.py** |
| Files and folders | **core/bibliotheque_fichiers.py**, **core/dossiers_bibliotheque.py** |
| PDF and Notion indexing | **indexers/index_documents.py**, **indexers/index_notion.py** |
| Object storage | **core/stockage_r2.py** |

Personal, public, and general document pipelines are not interchangeable. Check ownership, scope, storage, and search function before reusing a pipeline.

### Connectors and MCP servers

OAuth flows are mainly in **connexions/**. MCP servers are implemented in **core/serveur_mcp_*.py**, and their endpoints are assembled in **api/main.py**.

| MCP path | Service |
|---|---|
| **/mcp/generation** | generation tools |
| **/mcp/execution-code** | code execution |
| **/mcp/video** | video tools |
| **/mcp/github** | GitHub tools |
| **/mcp/netlify** | Netlify tools |
| **/mcp/public** | public document MCP server |
| **/mcp/espace** | public user-space MCP server |

Public servers use dedicated OAuth token verification. Do not confuse these public endpoints with internal MCP servers used by the Classinus engine.

### Mobile, real-time, and PC

Starting points include **api/appareils_mobiles.py**, **api/canal_temps_reel.py**, **api/canal_agent_applicatif.py**, and their corresponding modules in **core/**.

Deferred mobile actions, folder exploration, PC screen reading, and controlled desktop actions use separate modules. Identify the channel involved before extending a behavior.

### Media and heavy processing

File generation is split across **core/generation_*** modules. Video processing also has dedicated entry points, including **api/main_montage.py** and **api/rendu_animation.py**. The separate montage service and its configuration are described in the [deployment guide](DEPLOIEMENT.md).

## 5. Data and security

Supabase provides authentication, PostgreSQL, and the storage services used by the backend.

- Core server variables: **SUPABASE_URL** and **SUPABASE_SECRET**.
- SQL migrations are stored in **migrations/**.
- RLS policies, constraints, foreign keys, and RPC functions are part of each feature's contract.
- Provider and OAuth secrets must remain in the backend environment.

Every schema change must be delivered with its migration, tested in the appropriate environment, and applied before deploying code that depends on it.

## 6. Background tasks

The FastAPI lifecycle is managed from **api/main.py**. Background tasks handle deferred processing, notifications, reminders, indexing, and synchronization.

To modify a task, locate its business-logic module and verify how it is started and stopped. Do not launch a second concurrent loop without checking the existing mechanism.

## 7. Tests

Python tests are at the repository root and in **tests/**. They cover AI adapters, chat flows, tools and permissions, MCP servers, libraries, documents, mobile features, and media processing.

Run the tests related to the changed feature, followed by the relevant regression scenarios. **python scripts/predeploiement.py** is a pre-deployment check; it does not replace the test suite.

## Related guides

- [Overall architecture](ARCHITECTURE.md)
- [API domains and routes](API.md)
- [AI providers and RAG](IA_ET_RAG.md)
- [MCP and connectors](MCP_ET_CONNECTEURS.md)
- [Data and security](DONNEES_ET_SECURITE.md)
- [Local development](DEVELOPPEMENT.md)
- [Deployment](DEPLOIEMENT.md)
- [Railway checklist](./deployment/RAILWAY_DEPLOY.md)
