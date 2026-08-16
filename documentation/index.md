---
okf_version: "0.1"
---

# Överklagandenämnden Decision Search — Documentation

An OKF knowledge bundle for a Swedish-language semantic search and chat tool over
Överklagandenämnden legal decisions. Start here.

## Top-level

* [Product Requirements](prd.md) - Product requirements for a Swedish-language semantic search and chat tool over Överklagandenämnden legal decisions.
* [Architecture Overview](architecture.md) - The three-subsystem system architecture — ingestion pipeline, storage layer, and the conversational agent — plus the three ways to query the corpus and pointers into each area.
* [Testing Strategy](testing.md) - The backend's two-level (unit + integration) testing approach — what to test, what to mock, how the split is enforced, the separate database integration tests run against — plus the frontend suite and the two tests that check the contract across the language boundary.
* [LLM Observability](observability.md) - How every LLM and embedding call is captured to a local file, one file per call, correlated by directory — the record schema, the correlation keys, and the wiring every process must do.

## Sections

* [Ingestion Pipeline](pipeline/) - The seven queue-driven ingestion workers and the shared worker patterns.
* [Retrieval](retrieval/) - The conversational agent behind the chat endpoint, and the deterministic search path (with opt-in query expansion) it and the search API share.
* [Data Model](data-model/) - Tables, indexes, the repository layer, and schema design notes.
* [Backend Packages](packages/) - The uv workspace packages: shared, llm-core, ai, agents, api.
* [API](api/) - The chat and sessions endpoints, the SQL agent, the health check, and the deterministic search/browse/traversal REST API — search, filters, documents, concepts and keywords.
* [Frontend](frontend/) - The React SPA: deterministic search and agent mode, the SSE client for the chat endpoint, plus the honesty rules it enforces and the generated-types workflow it builds on.
* [Decisions](decisions/) - Architecture decision records.
* [Playbooks](playbooks/) - Operational procedures for local dev, live testing, and the acceptance walkthrough.
* [Reference](reference/) - Crawl source, GCP layout, LLM/embedding configuration, cost, and LLM pricing reference material.
