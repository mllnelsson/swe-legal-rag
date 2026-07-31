---
okf_version: "0.1"
---

# Överklagandenämnden Decision Search — Documentation

An OKF knowledge bundle for a Swedish-language semantic search and chat tool over
Överklagandenämnden legal decisions. Start here.

## Top-level

* [Product Requirements](prd.md) - Product requirements for a Swedish-language semantic search and chat tool over Överklagandenämnden legal decisions.
* [Architecture Overview](architecture.md) - The three-subsystem system architecture — ingestion pipeline, storage layer, and query/retrieval agent — and pointers to each area.
* [Testing Strategy](testing.md) - The two-level (unit + integration) testing approach — what to test, what to mock, and where tests live.
* [LLM Observability](observability.md) - How every LLM and embedding call is captured to file storage — the record schema, the correlation keys, and the wiring every process must do.

## Sections

* [Ingestion Pipeline](pipeline/) - The seven queue-driven ingestion workers and the shared worker patterns.
* [Retrieval](retrieval/) - The query/retrieval agent behind the chat endpoint.
* [Data Model](data-model/) - Tables, indexes, the repository layer, and schema design notes.
* [Backend Packages](packages/) - The uv workspace packages: shared, llm-core, ai, api.
* [API](api/) - The chat endpoint wire contract.
* [Frontend](frontend/) - The V1 streaming chat UI.
* [Decisions](decisions/) - Architecture decision records.
* [Playbooks](playbooks/) - Operational procedures for local dev and live testing.
* [Reference](reference/) - Crawl source, GCP layout, cost, and LLM pricing reference material.
