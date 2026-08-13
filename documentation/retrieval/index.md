# Retrieval

* [Conversational Agent](chat-agent.md) - The agent behind the chat endpoint — a GLM tool loop over the deterministic retrieval tool set, a terminal answer tool that doubles as the reranking, two Mistral sub-agents for reading and counting, and one streamed synthesis call.
* [Deterministic Search](deterministic-search.md) - The LLM-free hybrid search path behind POST /api/search — filter narrowing with no fallback, parallel vector/text arms under a similarity floor and fused by RRF, appendix widening, and document-level ranking that never fetches metadata for documents it will not return.
* [Query Expansion](query-expansion.md) - Opt-in, additive query expansion for the search API — ai.expand_query proposes alternate phrasings that add rankings to the same RRF fusion rather than replacing the original query, keeping search deterministic and replayable.
