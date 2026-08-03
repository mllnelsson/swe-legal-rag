# Retrieval

* [Query / Retrieval Agent](agent.md) - The five-step query agent — decompose, pre-filter, hybrid retrieve (RRF), optional rerank, synthesize — plus session context. Documents the deprecated chat path; see deterministic search for the non-agent alternative.
* [Deterministic Search](deterministic-search.md) - The LLM-free hybrid search path behind POST /api/search — filter narrowing with no fallback, parallel vector/text arms fused by RRF, appendix widening, and document-level ranking that never fetches metadata for documents it will not return.
* [Query Expansion](query-expansion.md) - Opt-in, additive query expansion for the search API — ai.expand_query proposes alternate phrasings that add rankings to the same RRF fusion rather than replacing the original query, keeping search deterministic and replayable.
