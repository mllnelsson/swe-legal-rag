# Backend Packages

* [Backend Packages Overview](overview.md) - The uv workspace layout, package dependency graph, and the layered Model→Repo→Service→Endpoint architecture.
* [llm-core Package](llm-core.md) - The standalone, project-agnostic LLM abstraction — provider Protocol, config/factory, Gemini and OpenAI-compatible providers, and the service layer.
* [ai Package](ai.md) - Project-specific LLM logic — prompt templates, domain DTOs, service functions, per-task model selection, and the embedding abstraction.
* [shared Package](shared.md) - The single source of truth for data and database access — models, DTOs, enums, errors, the task envelope, config, and the storage/queue infrastructure abstractions.
* [api Package](api.md) - The FastAPI application and retrieval service layer — query planner, retriever, answerer, session service, and the chat route.
