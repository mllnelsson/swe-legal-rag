# Documentation Update Log

## 2026-07-30

* **Update**: [llm-core](/packages/llm-core.md) — the trace lifecycle is now one `traced_call()` context manager instead of seven hand-driven functions. It owns success, failure and hand-off; callers only fold in the payload via `trace_response`, `trace_chunk` or `trace_outcome`. `start_trace`, `finish_trace`, `trace_failure`, `trace_result` and `trace_stream_completed` are gone from the public API.
* **Update**: [ai](/packages/ai.md) — `BergetEmbeddingProvider` opens its trace with the same `traced_call()` rather than driving the lifecycle by hand, and seeds model/provider on entry so a failed call is still attributed.
* **Update**: [shared](/packages/shared.md) — `StorageBackend` is a five-method blob store again. `add_json`/`iter_json` and the local `flock` machinery are gone: the trace recorder batches records and writes whole JSONL objects with `store()`, so an object store never has to append and the two backends no longer diverge. `iter_json` had no production caller.
* **Update**: [LLM Observability](/observability.md) — one uniform storage layout across backends, `{prefix}/{date}/{timestamp}-{rand}.jsonl` per flushed batch, with the batching triggers, the widened loss window, and why `flush()` asks the writer rather than merely waiting.
* **Update**: [LLM pricing](/reference/llm-pricing.md) — cost leaves the codebase entirely. Records no longer carry `estimated_cost_usd`, and there is no rate table, no `estimate_cost_usd()` and no costing CLI: a record carries the served `model` and the provider's `usage`, which is the complete raw material, so pricing is an analysis step performed against this reference. The page is now dated reference data rather than a spec binding a module, and states the rules (prefix match longest-first, case-insensitive, unpriced ≠ zero, `usage: null` ≠ zero, failed calls still bill) for whoever applies them.
* **Update**: [live testing](/playbooks/live-testing.md) and [local dev](/playbooks/local-dev.md) — trace paths are directory globs, cost verification runs the script, and the two batch env vars are listed.
* **Update**: [llm-core](/packages/llm-core.md) — `generate_structured` is generic in `response_model` (`[T: BaseModel] -> T`) rather than returning a bare `BaseModel`. Removes three `type: ignore[return-value]` in `ai/services.py` and an `assert isinstance` in the API reranker.

## 2026-07-27

* **Creation**: Established [LLM Observability](/observability.md) — every LLM and hosted-embedding call is captured to file storage with its full prompt, response, tokens and cost, correlated by `interaction_id` so one chat question can be costed as a sum over one key.
* **Update**: [LLM pricing](/reference/llm-pricing.md) no longer describes a Postgres `llm_traces` table — records are JSON in file storage, `estimated_cost_usd` is a string or null, and the queries are `jq`. Adds the explicit statement that no Berget rate is published in this repo, so default-configuration records carry tokens and a null cost.
* **Update**: [shared](/packages/shared.md) — `StorageBackend` gains `add_json`/`iter_json` append-style JSON streams, with the deliberate local-`.jsonl` vs GCS-object-per-record divergence and the `flock` requirement documented.
* **Update**: [llm-core](/packages/llm-core.md) — `Usage` type, per-provider token/model mapping, `LLM_STREAM_USAGE`, and `_tracing.py`: the package carries the trace hook but never a writer.
* **Update**: [ai](/packages/ai.md) — `_observability.py` and `_pricing.py`, `install_file_tracing()`, `PromptTemplate.name`, and why Berget embeddings are traced while local ones are not.
* **Update**: [architecture](/architecture.md) — the trace stream sits alongside PDFs in object storage, deliberately not in Postgres.
* **Update**: [live testing](/playbooks/live-testing.md) gains a "Verifying LLM Traces" section, including how to cost a single question; [local dev](/playbooks/local-dev.md) lists the five new env vars.

## 2026-07-26

* **Update**: [parse worker](/pipeline/parse.md) now repairs words split by a line-break hyphen — pypdfium2 emits U+FFFE there, which Postgres tokenized as two fragments, hiding the containing chunk from a search for the term. Line breaks themselves are deliberately left alone.
* **Creation**: Documented the anatomy of a decision PDF and the anchors the pipeline segments it with in [decision document structure](/reference/document-structure.md) — header, holding, trailer, `Bilaga X` appendices, and the two identifier spaces (ärendenummer vs beslutsnummer).
* **Creation**: Recorded [appendices are labelled, not dropped](/decisions/appendix-segmentation.md) — appended lower-instance decisions stay searchable but carry a `section` marker, and modelling the prior instance as structured data is explicitly deferred.
* **Creation**: Recorded [body-first retrieval over one vector index](/decisions/body-first-retrieval.md) — one HNSW index with a `section` predicate rather than two, a hard filter rather than a ranking penalty, and the partial index deferred behind measurement.
* **Update**: [chunks](/data-model/chunks.md) gains `section` and `appendix_label`; [documents](/data-model/documents.md) gains `decision_number`; both new [indexes](/data-model/indexes.md) listed (migration `004`).
* **Update**: [extract worker](/pipeline/extract.md) — references now come from the body only and in two identifier spaces, and relevance follows the holding instead of the latter 60% of the document, a heuristic appendices inverted.
* **Update**: [metadata worker](/pipeline/metadata.md) — field extractors take `DocumentSegments`, `decision_number` is extracted, and the LLM fallback is handed the body rather than `raw_text`.
* **Update**: [chunk worker](/pipeline/chunk.md) — body and each appendix are chunked separately and labelled, the trailer is not chunked, and the summary is derived from the body only.
* **Update**: [retrieval agent](/retrieval/agent.md) gains section scoping with a widen-on-empty fallback; the [chat endpoint](/api/chat-endpoint.md) `sources` payload gains `section` and `appendix_label`.
* **Update**: [shared package](/packages/shared.md) documents the new `segmentation.py` module and the `ChunkSection` vocabulary; [parse worker](/pipeline/parse.md) notes why `raw_text` deliberately keeps appendices.

## 2026-07-24

* **Creation**: Migrated the documentation set to an OKF v0.1 knowledge bundle — one concept per file, YAML frontmatter with a `type`, `/`-absolute cross-links, and per-directory `index.md` files. The former `specs/` and `design/` folders were replaced by topical sections (`pipeline/`, `retrieval/`, `data-model/`, `packages/`, `api/`, `frontend/`, `decisions/`, `playbooks/`, `reference/`).
* **Creation**: Split the monolithic backend and architecture specs into per-worker [pipeline](/pipeline/overview.md) Service concepts, per-package [Package](/packages/overview.md) concepts, per-table [Table](/data-model/documents.md) concepts, and a [Repository](/data-model/repositories.md) concept for the function-based data layer.
* **Deprecation**: Removed the superseded `min-instances 0 vs 1` self-hosting narration from the [embedding hosting](/decisions/embedding-hosting.md) decision. The tension — a direct NFR1 (<5s query) vs NFR2 (<$30/mo idle) tradeoff for a cold in-process `e5-large` load — is moot under the Berget-hosted default, since neither the API server nor `worker-embed` loads the model. It is preserved here in case the project ever reverts to self-hosting.
* **Deprecation**: Fixed stale LLM config in the [live testing](/playbooks/live-testing.md) playbook. Its env block previously set `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.0-flash` (a model shut down 2026-06-01), and `EMBEDDING_PROVIDER=local`, contradicting the Berget default in [local dev](/playbooks/local-dev.md); it now matches the Berget provider and per-task model scheme.
* **Update**: Consolidated the mandatory crawl tag-filter rationale into a single [decision](/decisions/tag-filter.md) (previously duplicated across the crawl source and backend specs), and the `ai` package into a single [concept](/packages/ai.md) (previously documented twice in the backend spec).
