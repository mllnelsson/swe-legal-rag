# Architecture: Överklagandenämnden Decision Search Tool

## High-Level Overview

Three major subsystems: **Ingestion Pipeline**, **Storage Layer**, **Query/Retrieval Agent**. All running on GCP, scale-to-zero where possible.

## 1. Ingestion Pipeline

Queue-driven (Pub/Sub), each step is a Cloud Run worker consuming from a topic and publishing to the next. Each step checkpoints its output so failures are resumable.

**Step 1 — Crawl:** Poll the public API, fetch PDF URLs. Deduplicate against known documents. Publish new document references to next topic. Checkpoint: document registry updated.

*Implementation:* One-shot worker (`worker-crawl`). Fetches HTML from `CRAWL_SOURCE_URL`, parses `<a href="*.pdf">` links with BeautifulSoup, resolves to absolute URLs, deduplicates order-preservingly. Deduplication against DB uses `get_by_source_url()` (checks before insert) and catches `IntegrityError` on the `documents.source_url` unique constraint for concurrent runs. Per-URL: creates `documents` row + `tasks` rows (crawl:completed, download:pending), commits, then publishes to the download topic.

**Step 2 — Download & Store Raw:** Download PDFs, store in GCS. Publish GCS URI. Checkpoint: PDF in bucket.

*Implementation:* Subscriber worker (`worker-download`). Consumes from the download topic. Storage key format: `documents/{document_id}/original.pdf`. Retry policy: up to `DOWNLOAD_MAX_RETRIES` attempts with exponential backoff (`2**attempt` seconds); HTTP 4xx raises immediately (not retryable), 5xx and network errors are retried. Rate limiting: `DOWNLOAD_RATE_LIMIT_DELAY` seconds sleep after each successful download. Idempotency: skips download if `document.gcs_uri` already set, still creates parse task and publishes.

**Step 3 — Parse & Extract Text:** PDF → structured text extraction. Publish extracted text. Checkpoint: raw text stored.

*Implementation:* Subscriber worker (`worker-parse`). pypdfium2 chosen as the PDF parsing library (Apache 2.0 license, unlike PyMuPDF/pymupdf4llm which is AGPL). The parser is wrapped in a `typing.Protocol`-based abstraction (`Parser(pdf_bytes: bytes) -> str`) so the underlying library is swappable without changing the service layer. Extracted text is stored in `documents.raw_text` as plain text with `"\n\n---\n\n"` page separators. Publishes to the `metadata` topic.

**Step 4 — Metadata Extraction:** Rule-based first, LLM fallback for missing fields only. Checkpoint: metadata record persisted.

*Implementation:* Subscriber worker (`worker-metadata`). Extraction strategy: per-field pure functions in `patterns.py` run regex patterns on the raw text first. LLM fallback (Gemini Flash or Haiku via `ai` package) is called only when `is_complete()` returns `False` (i.e., fields remain `None` after rule-based extraction). Rule-based results are never overwritten by LLM values. Regex patterns target: `Dnr`/`Diarienummer`/`ÖN` case numbers, Swedish date formats (ISO, `den 15 januari 2023`, abbreviated), decision language (`bifaller`/`avslår`/`avvisar överklagandet`), and `Ärende:`/`Ämne:`/`Kategori:` header lines. Metadata fields are freeform VARCHAR — no enum constraints. Missing metadata (all fields `None`) is a valid outcome, not a failure. Publishes to the `extract` topic.

**Step 5 — Entity & Reference Extraction:** Extract entities (legal concepts, roles, parishes, regulations) and cross-references to other decisions. LLM-assisted (cheap model) — one-time ingestion cost. Populates the graph-in-Postgres layer: `entities`, `document_entities`, `document_references`. Gives the retrieval agent entity-based pre-filtering and relationship traversal without a graph database. Checkpoint: entities and references persisted.

**Step 6 — Contextual Chunking:** Generate a document-level summary first, then chunk the document. Each chunk gets the summary prepended before embedding — the contextual retrieval trick. Gives every chunk awareness of the whole document's context. Checkpoint: chunks stored with parent doc reference.

**Step 7 — Embed & Index:** Embed chunks using a multilingual model with strong Swedish support (candidates: Cohere embed-multilingual, or open-source e5-multilingual for zero cost). Store embeddings + chunk text + metadata. Checkpoint: vectors indexed.

## 2. Storage Layer

Single Postgres instance (Cloud SQL) with pgvector extension. Four concerns, one database:

- **Document registry** — tracks ingestion state per document (which pipeline steps completed), stores metadata
- **Chunk store** — chunk text, parent document FK, positional info
- **Vector index** — pgvector embeddings on chunk table, plus GIN index on tsvector column for BM25-style full-text search in Swedish
- **Entity graph** — entities, document-entity mappings, and cross-references between decisions. GraphRAG concepts in relational tables — SQL joins replace graph traversal at this scale

PDFs in GCS bucket, served via signed URLs.

Why single Postgres? At 1000 docs this is not a scale problem. pgvector handles this trivially. You get hybrid search (vector + full text + structured SQL filters) in a single query. No need for a separate vector DB.

## 3. Query / Retrieval Agent

**Step 1 — Query Decomposition:** Agent (cheap LLM) analyzes the user's Swedish question. Extracts: implicit date filters, topic/category, decision type, entity references (roles, legal concepts, parishes), and the core semantic question. Outputs a structured query plan.

**Step 2 — Structured + Entity Pre-filter:** Narrows the candidate set using two paths: metadata filters (SQL WHERE on date, category, outcome) and entity-based filtering (join through `document_entities` to find documents involving specific entities). Also traverses `document_references` if the query implies precedent chains ("decisions that cite..." or follow-up questions about related rulings). This is the key trick — you're not doing semantic search across 1000 docs, you're searching across maybe 50-100 after filtering.

**Step 3 — Hybrid Retrieval:** On the filtered subset, run both vector similarity search (pgvector) and full-text search (Swedish tsvector) in parallel. Combine scores with reciprocal rank fusion (RRF).

**Step 4 — Rerank:** Optional but cheap — a cross-encoder or even another LLM call to rerank the top-k results for relevance. At this scale it's fast.

**Step 5 — Synthesis:** Feed top chunks + metadata to LLM. Generate Swedish answer with citations (case numbers, dates). Return source references so frontend can link to PDFs.

**Session context:** Keep conversation history in memory (or lightweight session store) so the agent can handle follow-ups like "what about after 2021?" without the user re-explaining.

## 4. Infrastructure / GCP Layout

- **Cloud Run** — API server, pipeline workers, frontend serving. All scale to zero.
- **Pub/Sub** — pipeline orchestration between steps
- **Cloud SQL (Postgres + pgvector)** — single small instance, the main standing cost
- **GCS** — PDF storage
- **Secret Manager** — API keys for LLM providers

## 5. Local Development Replacements

The architecture is designed so every GCP service has a local equivalent for free, fast iteration.

| GCP Service | Local Replacement | Notes |
|---|---|---|
| Cloud SQL (pgvector) | Docker Postgres + pgvector | `ankane/pgvector` image, identical SQL interface |
| Pub/Sub | In-process queue or Redis Streams | For dev, a simple Python queue or even synchronous calls between steps works. Redis if you want to test async behavior. |
| GCS | Local filesystem or MinIO | Store PDFs in a local directory. MinIO if you want S3-compatible API parity. |
| Cloud Run | Local Python process | Just run the workers directly. No containerization needed during dev. |
| Secret Manager | `.env` file | Standard dotenv pattern |

**Key principle:** abstract each external dependency behind a thin interface so swapping local ↔ GCP is a config change, not a code change. This means: a storage interface (GCS/local), a queue interface (Pub/Sub/local), and a database connection string swap.

## 6. Cost Estimate (Idle / Low Usage)

- Cloud SQL (db-f1-micro): ~$7-10/mo
- Cloud Run: ~$0 at idle (scale to zero)
- Pub/Sub: pennies at this volume
- GCS: pennies for ~1000 PDFs
- LLM API (query time): depends on usage, but a handful of queries/day on a cheap model is <$5/mo
- Embedding (one-time): <$1 if using API, $0 if open-source model
- **Total idle: ~$10-15/mo**

Scaling to 5000 docs: Cloud SQL stays the same, embedding cost scales linearly but is one-time, query costs unchanged.

## 7. Key Architectural Decisions

- **Rule-based metadata extraction first** — legal docs follow consistent templates, LLM is fallback not default
- **Contextual chunking over naive chunking** — document summary prepended to every chunk before embedding
- **Hybrid search (vector + BM25)** over pure vector — legal text benefits heavily from keyword matching
- **Agent-driven filtering over user-driven** — the LLM extracts structure from natural language
- **Single Postgres over separate vector DB** — simplicity at this scale, hybrid search in one query
- **Graph-in-Postgres over Neo4j** — entity relationships and cross-references as relational tables. SQL joins replace graph traversal. 80% of GraphRAG value at zero additional infrastructure cost
- **Queue-based pipeline over monolithic script** — resumability, observability, future scalability
- **Interface abstraction for all infra dependencies** — local dev parity via config swap
