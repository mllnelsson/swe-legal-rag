# Backend Packages

* [Backend Packages Overview](overview.md) - The uv workspace layout, package dependency graph, and the layered Model→Repo→Service→Endpoint architecture.
* **agent-kit** — the domain-free agent core (`agent_kit` + `agent_kit.llm`) is an external, pinned git dependency, not a workspace package; see [how this repo consumes it](overview.md#package-dependency-graph).
* [ai Package](ai.md) - Project-specific LLM logic — Swedish prompt templates, domain DTOs, service functions, per-task model selection, and the embedding abstraction, layered over the agent-kit core.
* [shared Package](shared.md) - The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, logging setup, and the storage/queue infrastructure abstractions.
* [agents Package](agents.md) - The LLM-tool-loop agents that answer questions the deterministic retrieval API cannot — the text-to-SQL agent behind POST /api/sql and the conversational agent behind POST /api/chat — their module layout, and the injected-toolset seam that keeps the dependency running api to agents.
* [api Package](api.md) - The FastAPI application and the deterministic search/browse/traversal REST API — search/document/concept/keyword services, the session service, the chat toolset the conversational agent is driven through, and their routes.
