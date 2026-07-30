---
type: Decision
title: Architectural Decision Register
description: The consolidated register of accepted system-shaping decisions — retrieval, storage, pipeline, data-layer, and library choices.
tags: [architecture, decisions, register]
timestamp: 2026-07-26T00:00:00Z
---

# Architectural Decision Register

A consolidated register of the system-shaping decisions. Embedding decisions have their
own records: [model](/decisions/embedding-model.md),
[hosting](/decisions/embedding-hosting.md), [dimension](/decisions/embedding-dimension.md);
the mandatory crawl [tag filter](/decisions/tag-filter.md) is also separate. All entries
below are **Accepted**.

## Retrieval and extraction

- **Rule-based metadata extraction first** — legal docs follow consistent templates; the
  LLM is a fallback, not the default. See [metadata worker](/pipeline/metadata.md).
- **Contextual chunking over naive chunking** — a document summary is prepended to every
  chunk before embedding. See [chunk worker](/pipeline/chunk.md).
- **Hybrid search (vector + BM25) over pure vector** — legal text benefits heavily from
  keyword matching. See [retrieval agent](/retrieval/agent.md).
- **Agent-driven filtering over user-driven** — the LLM extracts structure from natural
  language rather than exposing manual filters in V1.
- **Appendices are labelled, not dropped** — a decision PDF contains the decision it
  reviewed; that text stays searchable but is marked so it can never be cited as the
  nämnd's own. See [appendices are labelled, not dropped](/decisions/appendix-segmentation.md).
- **Body-first retrieval over one vector index** — appendix scoping is a `WHERE`
  predicate on the existing HNSW index, applied as a hard filter rather than a ranking
  penalty. See [body-first retrieval](/decisions/body-first-retrieval.md).

## Storage and graph

- **Single Postgres over a separate vector DB** — simplicity at this scale; hybrid search
  (vector + full text + structured SQL) in one query.
- **Graph-in-Postgres over Neo4j** — entity relationships and cross-references as
  relational tables ([entities](/data-model/entities.md),
  [document_entities](/data-model/document-entities.md),
  [document_references](/data-model/document-references.md)); SQL joins replace graph
  traversal. ~80% of GraphRAG value at zero additional infrastructure cost.

## Pipeline and infrastructure

- **Queue-based pipeline over a monolithic script** — resumability, observability, future
  scalability. See [pipeline overview](/pipeline/overview.md).
- **Interface abstraction for all infra dependencies** — storage, queue, LLM, embedding
  are swappable via config for local-dev parity. See
  [GCP layout](/reference/gcp-layout.md).
- **No LLM proxy container** — containerizing `ai`/`llm-core` as a service was considered
  as a way to give every worker its own container without each owning a private trace
  file. It solves neither half. What keeps the workers in one process is the `sync`
  queue, whose broker is a module-level singleton dispatching in-process — a proxy does
  nothing for that. And traces were never the obstacle: one storage key plus an exclusive
  `flock` per append already lets many processes share one stream. Against that, a proxy
  adds a hop on the <5 s streaming chat path and diverges from Cloud Run, where each
  service calls the provider directly. See [observability](/observability.md).
- **Local Postgres is platform-dependent, `DATABASE_URL` is not** — Compose on Linux,
  Homebrew `postgresql@17` on macOS, where Docker Desktop would only add a VM. Creating a
  `postgres` superuser role on the native install makes one connection string work
  everywhere, so no code, config or test fixture knows which platform it is on. Nothing
  else in the stack ever required Docker: storage is the filesystem, the queue is
  in-process, MinIO and Redis were already optional. See
  [local dev](/playbooks/local-dev.md).

## Data layer and libraries

- **Function-based data layer + Protocol-injected namespaces** — repos and worker
  services are modules of functions, not classes. The rationale and the load-bearing
  injection seam are in [repositories](/data-model/repositories.md).
- **StrEnum vocabularies need no migration; DTO fields stay `str`** — the finite
  vocabularies live in `shared/enums.py` as `StrEnum`; since a member *is* the stored
  text, adopting them changed no bytes and needed no Alembic migration. DB-facing DTO
  fields stay typed `str` (avoiding ~76 call-site rewrites pydantic+pyright would force
  for enum-typed fields), while business logic constructs and compares with the enums;
  enum-typing is kept only in the extraction models, where it also constrains the LLM's
  structured-output schema. See [data model design notes](/data-model/design-notes.md).
- **pypdfium2 over PyMuPDF for parsing** — pypdfium2 is Apache 2.0 licensed; PyMuPDF /
  pymupdf4llm is AGPL. See [parse worker](/pipeline/parse.md).
