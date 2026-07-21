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

*Implementation:* Subscriber worker (`worker-metadata`). Extraction strategy: per-field pure functions in `patterns.py` run regex patterns on the raw text first. LLM fallback (Gemini Flash or Haiku via `ai` package) is called only when `is_complete()` returns `False` (i.e., fields remain `None` after rule-based extraction). Rule-based results are never overwritten by LLM values. Regex patterns target: `Ärendenummer: ÖN <case number>` for case numbers, `Meddelat <YYYY-MM-DD>` for decision dates, decision language (`bifaller`/`avslår`/`avvisar överklagandet`) for outcomes, and the line two positions after a `Svenska kyrkans överklagandenämnd` heading for category. A broader pattern set (`Dnr`/`Diarienummer` case numbers, Swedish textual/abbreviated dates, `Ärende:`/`Ämne:`/`Kategori:` header lines) was implemented and then deprecated in favor of this narrower, verified set — the LLM fallback covers documents that don't match these exact formats. Metadata fields are freeform VARCHAR — no enum constraints. Missing metadata (all fields `None`) is a valid outcome, not a failure. Publishes to the `extract` topic.

**Step 5 — Entity & Reference Extraction:** Extract entities (legal concepts, roles, parishes, regulations) and cross-references to other decisions. LLM-assisted (cheap model) — one-time ingestion cost. Populates the graph-in-Postgres layer: `entities`, `document_entities`, `document_references`. Gives the retrieval agent entity-based pre-filtering and relationship traversal without a graph database. Checkpoint: entities and references persisted.

**Step 6 — Contextual Chunking:** Generate a document-level summary first (Gemini Flash via `ai.summarize_document()`), then chunk the document. Each chunk gets the summary prepended before embedding — the contextual retrieval trick. Gives every chunk awareness of the whole document's context. Checkpoint: chunks stored with parent doc reference.

*Implementation:* Subscriber worker (`worker-chunk`). Token-based chunking: ~500 tokens per chunk, ~50 token overlap, tiktoken `cl100k_base` encoding. Sentence-aware boundaries: splits on sentence-ending punctuation (`[.!?]` followed by whitespace) or blank lines, never mid-sentence. Overlap is implemented by rewinding — trailing sentences totalling ≤ 50 tokens are retained as the start of the next chunk. Contextual retrieval pattern: `summary\n\n---\n\nchunk_text` stored in `contextual_text`. The `chunk_text` column retains the raw text for user-facing citations. Idempotency: existing chunks are deleted before re-inserting. Publishes to the embed topic.

**Step 7 — Embed & Index:** Embed chunks using `intfloat/multilingual-e5-large` (1024 dimensions). Store as pgvector `VECTOR(1024)`. Swedish full-text index via `tsvector` column. Terminal pipeline step — no downstream queue. Checkpoint: embeddings stored.

*Implementation:* Subscriber worker (`worker-embed`). Embeds `contextual_text` (falls back to `chunk_text` if None) in a single batch call via the `ai.EmbeddingProvider` abstraction. Local provider (`sentence-transformers`) used by default — no API key required. Updates the `embedding` column via bulk UPDATE. The `tsv` (tsvector) column is `GENERATED ALWAYS AS (to_tsvector('swedish', chunk_text)) STORED` — PostgreSQL populates it automatically at chunk INSERT time; the embed worker does not touch it. HNSW index for ANN vector search, GIN index for full-text search, both functional after embed completes.

*Query-time embedding:* The same model is used at query time — the API server embeds the user's question via the same `EmbeddingProvider` abstraction before running vector similarity search. Ingestion and query embeddings **must** come from the same model; mismatched models produce incompatible vector spaces.

## 2. Storage Layer

Single Postgres instance (Cloud SQL) with pgvector extension. Four concerns, one database:

- **Document registry** — tracks ingestion state per document (which pipeline steps completed), stores metadata
- **Chunk store** — chunk text, parent document FK, positional info
- **Vector index** — pgvector `VECTOR(1024)` embeddings on chunk table, plus GIN index on tsvector column for BM25-style full-text search in Swedish
- **Entity graph** — entities, document-entity mappings, and cross-references between decisions. GraphRAG concepts in relational tables — SQL joins replace graph traversal at this scale

PDFs in GCS bucket, served via signed URLs.

Why single Postgres? At 1000 docs this is not a scale problem. pgvector handles this trivially. You get hybrid search (vector + full text + structured SQL filters) in a single query. No need for a separate vector DB.

## 3. Query / Retrieval Agent

**Step 1 — Query Decomposition:** Agent (cheap LLM) analyzes the user's Swedish question. Extracts: implicit date filters, topic/category, decision type, entity references (roles, legal concepts, parishes), and the core semantic question. Outputs a structured query plan.

*Implementation:* `api/services/query_planner.py`. Calls `ai.decompose_query()` → maps `DecomposeResult` onto `DocumentFilter`: `DateFilter.start/end` → `date_from/date_to`; `categories[0]` → `category`; `entity_refs` → `entity_names`. Returns `QueryPlan(semantic_query, filter)`. The mapping lives in `api` — `shared` must not import from `ai`.

**Step 2 — Structured + Entity Pre-filter:** Narrows the candidate set using two paths: metadata filters (SQL WHERE on date, category, outcome) and entity-based filtering (join through `document_entities` to find documents involving specific entities). Also traverses `document_references` if the query implies precedent chains ("decisions that cite..." or follow-up questions about related rulings). This is the key trick — you're not doing semantic search across 1000 docs, you're searching across maybe 50-100 after filtering.

*Implementation:* `shared/repositories/search.py` — `search.find_candidate_documents(session, filter)` (a module function, not a class method). Empty filter fast path: if all filter fields are None/empty, the DB call is skipped entirely and `candidate_ids=None` (unfiltered) is used directly — no unnecessary full-table fetch. Non-empty filter with zero results falls back to `candidate_ids=None` (graceful degradation with a warning log). Reference traversal queries `document_references` in both directions: documents that cite the target case AND documents that the target case cites.

**Step 3 — Hybrid Retrieval:** On the filtered subset, run both vector similarity search (pgvector) and full-text search (Swedish tsvector) in parallel. Combine scores with reciprocal rank fusion (RRF).

*Implementation:* `api/services/retriever.py`. Queries use `asyncio.gather(vector_search, text_search)` both capped at `RETRIEVAL_SEARCH_LIMIT`. The user's question is embedded with `"query: "` prefix (e5 convention — symmetric with the `"passage: "` prefix used at index time by worker-embed). RRF fusion via `shared.search.rrf.rrf_fuse(k=60)` then takes `[:RETRIEVAL_TOP_K]`. Document metadata is hydrated concurrently via `asyncio.gather(*[get_by_id(did) for did in unique_doc_ids])`.

**Step 4 — Rerank:** Optional but cheap — a cross-encoder or even another LLM call to rerank the top-k results for relevance. At this scale it's fast.

*Implementation:* `_rerank()` in `api/services/retriever.py`. Gated behind `RETRIEVAL_RERANK_ENABLED` (default `False`) to satisfy NFR1 (<5s response). Uses `llm_core.generate_structured()` to return a ranked index list; any failure falls back to RRF order — rerank never breaks retrieval. The `llm_core` import is lazy (inside the function body) to avoid adding it to `api/pyproject.toml` as an explicit dependency.

**Step 5 — Synthesis:** Feed top chunks + metadata to LLM. Generate Swedish answer with citations (case numbers, dates). Return source references so frontend can link to PDFs.

*Implementation:* `api/services/answerer.py`. Streams tokens via `ai.synthesize_answer()` → yields `TokenEvent` per token, then a single `SourcesEvent` with deduplicated sources (one `SourceReference` per document, first-seen chunk in RRF order wins the excerpt, truncated to 200 chars), then `DoneEvent`. PDF URLs are generated via `storage.get_url("documents/{doc_id}/original.pdf")`, returning `None` on error. The event ordering `token* → sources → done` is guaranteed — sources are only emitted after synthesis completes.

**Session context:** Keep conversation history in memory (or lightweight session store) so the agent can handle follow-ups like "what about after 2021?" without the user re-explaining.

*Implementation:* `sessions` table in Postgres. Each `POST /api/chat` creates or loads a session by `session_id` (UUID). The `done` SSE event returns the `session_id`; subsequent requests send it back. Full turn history is stored in a JSONB column; `history_for_llm()` truncates to the last `SESSION_MAX_HISTORY_TURNS` turn-pairs before sending to the LLM. Stale or missing session IDs silently create a new session — no client error. The API layer (`api/services/session_service.py`) owns all session logic; the `session` repo module (`shared/repositories/session.py`, a module of functions taking `AsyncSession`) owns the DB access.

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
- Embedding model hosting: $0 at idle (scale-to-zero); ~$15-30/mo if upgraded to `min-instances: 1`
- **Total idle: ~$10-15/mo** (scale-to-zero) or **~$25-45/mo** (always-warm)

Scaling to 5000 docs: Cloud SQL stays the same, embedding cost scales linearly but is one-time, query costs unchanged.

## 7. Embedding Model

### Model Choice

**Model:** `intfloat/multilingual-e5-large` (1024 dimensions).

Chosen based on the [Scandinavian Embedding Benchmark (SEB)](https://github.com/KennethEnevoldsen/Scandinavian-Embedding-Benchmark) results for Swedish retrieval tasks. `e5-large` consistently outperforms `e5-base` and the Swedish-specific `KBLab/sentence-bert-swedish-cased` on retrieval benchmarks. Key alternatives considered:

| Model | Dims | Verdict |
|---|---|---|
| `intfloat/multilingual-e5-base` | 768 | Previous default. Weaker Swedish retrieval quality. |
| `intfloat/multilingual-e5-large` | 1024 | **Selected.** Best balance of Swedish quality, open-source, and sentence-transformers compatibility. |
| `BAAI/bge-m3` | 1024 | Top multilingual benchmark performer. Heavier, more complex (dense+sparse+ColBERT). Not needed at this scale. |
| `KBLab/sentence-bert-swedish-cased` | 768 | Swedish-specific (National Library of Sweden). Strong but less actively maintained; SEB results show e5-large edges it on retrieval. |
| Google `text-embedding-004` | 768 | Managed API, cheapest to run (<$1/mo). But proprietary — locks model choice to Google, no local dev parity. |

### Hosting Strategy

The embedding model is needed in two places: **ingestion** (worker-embed, batch) and **query time** (API server, latency-sensitive). Both use the same model via the `EmbeddingProvider` abstraction.

`e5-large` is ~2.2 GB. Running it in-process on a scale-to-zero Cloud Run service causes 30-60s cold starts on the query path — unacceptable for live user queries.

**Evaluated hosting options:**

| Option | Monthly cost | Cold start | Model control | Notes |
|---|---|---|---|---|
| Cloud Run `min-instances: 1` | ~$15-30 | None | Full | Simplest. API server always warm with model loaded. No external dependency. Spends most of the NFR2 idle budget. |
| HuggingFace Inference Endpoints | ~$5-15 | ~30-60s from zero | Full | Scale-to-zero available. Cheaper but adds external dependency and cold start. Good fallback option. |
| Vertex AI Embedding API | <$1 | None | Google models only | Cheapest. But locked to Google's model, no local dev parity, loses benchmark-validated quality. |

> **Open question — `min-instances` is not settled.** This section previously marked
> `min-instances: 1` as selected while [EMBEDDING_HOSTING.md](../design/EMBEDDING_HOSTING.md#decision)
> marked `min-instances: 0` as selected for launch. Both cannot hold, and the choice is a
> direct NFR1/NFR2 tradeoff: `0` protects the <$30/mo idle budget but makes the first query
> after scale-to-zero take 30-60s against a <5s target; `1` meets NFR1 but consumes
> $15-30/mo of that budget before Cloud SQL is counted. **EMBEDDING_HOSTING.md is the
> authoritative doc for this decision** — resolve it there, not here. Deferred to Story 12
> (GCP Deployment), where the real idle cost becomes measurable.
| Vertex AI custom endpoint (GPU) | ~$800 | None | Full | Massive overkill at this scale. |

**Decision: Cloud Run with `min-instances: 0`** (scale-to-zero) on the API service initially. Cold starts (~30-60s for model load) are accepted at launch given low query volume. Upgrade to `min-instances: 1` (~$15-30/mo) when usage justifies always-on cost. The ingestion worker (worker-embed) always scales to zero since batch latency is not user-facing.

*Local development:* `sentence-transformers` loads the model in-process. Same as production — no API stub needed.

### Token Counting (Chunking)

The chunker (`worker-chunk`) uses **tiktoken `cl100k_base`** to measure chunk sizes in tokens. This is a token-counting algorithm, not a model — it determines where to split text, not how to embed it. `cl100k_base` is OpenAI's GPT-4 tokenizer and does not match the e5 tokenizer (WordPiece). For Swedish text, `cl100k_base` tends to undercount tokens relative to the e5 tokenizer. The chunk budget (~500 tokens) includes headroom for this divergence — chunks will be somewhat smaller than 512 tokens in e5 terms, which keeps them within the model's max sequence length.

## 8. Key Architectural Decisions

- **Rule-based metadata extraction first** — legal docs follow consistent templates, LLM is fallback not default
- **Contextual chunking over naive chunking** — document summary prepended to every chunk before embedding
- **Hybrid search (vector + BM25)** over pure vector — legal text benefits heavily from keyword matching
- **Agent-driven filtering over user-driven** — the LLM extracts structure from natural language
- **Single Postgres over separate vector DB** — simplicity at this scale, hybrid search in one query
- **Graph-in-Postgres over Neo4j** — entity relationships and cross-references as relational tables. SQL joins replace graph traversal. 80% of GraphRAG value at zero additional infrastructure cost
- **Queue-based pipeline over monolithic script** — resumability, observability, future scalability
- **Interface abstraction for all infra dependencies** — local dev parity via config swap
