# Backend Packages

* [Backend Packages Overview](overview.md) - The uv workspace layout, package dependency graph, and the layered Model→Repo→Service→Endpoint architecture.
* [llm-core Package](llm-core.md) - The standalone, project-agnostic LLM abstraction — provider Protocol, config/factory, Gemini and OpenAI-compatible providers, and the service layer.
* [ai Package](ai.md) - Project-specific LLM logic — prompt templates, domain DTOs, service functions, per-task model selection, and the embedding abstraction.
* [shared Package](shared.md) - The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, logging setup, and the storage/queue infrastructure abstractions.
* [agents Package](agents.md) - The stateless LLM-tool-loop agents that answer questions the deterministic retrieval API cannot — today, the text-to-SQL agent behind POST /api/sql — package structure, and how the semantic-model/schema/guard/sandbox/tools modules compose into run_sql_agent.
* [api Package](api.md) - The FastAPI application, the chat retrieval service layer, and the deterministic search/browse/traversal REST API — query planner, retriever, answerer, session service, search/document/concept services, and their routes.
