# Documentation Update Log

## 2026-07-26

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
