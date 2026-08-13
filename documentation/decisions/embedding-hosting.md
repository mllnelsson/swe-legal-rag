---
type: Decision
title: Embedding model hosting
description: Where the e5-large embedding model is hosted — Berget.ai hosted inference rather than any self-hosted option, selected per environment via llm_config.yaml, which ships defaulting to the in-process local fallback.
tags: [embedding, hosting, berget, infrastructure]
timestamp: 2026-08-08T00:00:00Z
---

# Embedding model hosting

**Status:** Accepted — Berget.ai hosted `e5-large`, selected by setting
`embedding.provider: berget` in [`llm_config.yaml`](/reference/llm-config.md). The
config as shipped in this repo defaults `embedding.provider` to `local` instead — see
[Current default](#current-default) below; the decision to prefer Berget when a key is
available is unchanged.

The embedding model ([e5-large, 1024 dims](/decisions/embedding-model.md)) is needed at
both **ingestion time** ([worker-embed](/pipeline/embed.md), batch) and **query time**
([API server](/packages/api.md), latency-sensitive). Both paths must use the same model
— mismatched models produce incompatible vector spaces.

## Constraints

- **Model size:** ~2.2 GB on disk, ~1–1.5 GB RAM at inference.
- **Query-time latency:** sub-second responses expected; 30–60s cold starts are
  unacceptable on the query path.
- **Ingestion latency:** batch — cold starts are acceptable.
- **Scale:** ~1000 documents, low query volume (a handful of queries/day).
- **Budget:** minimise standing cost; the system is lightly used.

## Decision

Call the identical `intfloat/multilingual-e5-large` model hosted by
[Berget.ai](https://docs.berget.ai) — a GDPR-compliant, EU-hosted, OpenAI-API-compatible
inference provider — instead of self-hosting it anywhere. Rationale:

1. **No self-hosting at all** — no Cloud Run cold-start tradeoff, no `min-instances`
   decision, no in-process model load (~2.2 GB) on either the API server or
   `worker-embed`.
2. **Same model, zero migration** — 1024 dims, unchanged from the self-hosted default;
   `shared.config.EMBEDDING_DIMENSION` and the [chunks.embedding
   column](/data-model/chunks.md) are untouched (see [embedding
   dimension](/decisions/embedding-dimension.md)).
3. **Near-zero cost** — ~€0.03 per million tokens, negligible at this scale and cheaper
   than any self-hosted always-on option.
4. **EU data residency** — relevant for Swedish legal documents.
5. **Reuses the Berget account/API key** already needed for the LLM provider — no
   separate infrastructure to provision.

**Implementation:** `packages/ai/src/ai/providers/openai_compatible_embeddings.py` —
`OpenAiCompatibleEmbeddingProvider` implements `EmbeddingProvider` via
`openai.AsyncOpenAI.embeddings.create()` (Berget's inference API is a drop-in OpenAI
API). The class was generalised from an earlier `BergetEmbeddingProvider`/
`berget_embeddings.py` that took no Berget-specific behaviour — it works against any
OpenAI-compatible embeddings endpoint, Berget included, chosen by which `providers:`
entry `embedding.provider` names in `llm_config.yaml`. Reuses `BERGET_API_KEY` when
that entry is `berget`. See the [ai package](/packages/ai.md).

**Fallback preserved — and, as shipped, the default.**
`LocalEmbeddingProvider` (`sentence-transformers` in-process) remains fully implemented
for offline development and tests that must not depend on network access or a Berget
API key. Selected by `embedding.provider: local` in `llm_config.yaml`, or the
`EMBEDDING_PROVIDER` env var — which takes an `EmbeddingBackend` **kind**
(`openai_compatible` or `local`), not a `providers:` name, so `EMBEDDING_PROVIDER=berget`
is not a valid value. See the [env-var registry](/reference/llm-config.md#env-var-registry).

### Current default

The `llm_config.yaml` checked into this repo ships with `embedding.provider: local`,
not `berget` — this decision's preference for Berget applies once a `BERGET_API_KEY`
is configured and `embedding.provider` is pointed at that `providers:` entry, which is
an environment-specific choice rather than a code default. Nothing above the
[constraints](#constraints) changes: Berget remains the intended hosted path, `local`
remains the offline fallback, and this doc's job is only to describe which one the
shipped config selects.

## Trade-offs

- Adds a network hop on the query path, but the [NFR1a (<5s on search)](/prd.md) budget comfortably
  covers one embedding call plus retrieval.
- Adds an external dependency on Berget's uptime, in addition to the configured LLM
  provider.

## Options considered

| Option | Monthly cost | Cold start | Model control | Verdict |
|---|---|---|---|---|
| **Berget.ai hosted e5-large** | ~€0.03/M tokens | None (Berget scales) | Same model | **Selected** |
| Cloud Run in-process (`min-instances` 0→1) | ~$0 idle → $15–30 always-on | 30–60s cold / none warm | Full | Superseded |
| HuggingFace Inference Endpoints | ~$5–15 | 30–60s from zero | Full | Not selected |
| Vertex AI Embedding API (`text-embedding-004`) | <$1 | None | None (768 dims, locked) | Not selected — dimension change, unvalidated for Swedish legal text |
| Vertex AI Custom GPU Endpoint | ~$800 | None | Full | Not selected — 25–50× overkill at this scale |

**Superseded — self-hosting and the `min-instances` 0-vs-1 tension.** The earlier
question of whether to run `e5-large` in-process on Cloud Run at `min-instances: 0`
(cheap, cold) or `1` (warm, ~$15–30/mo) is **moot** under the Berget default — there is
no self-hosted model to warm up or scale. Likewise the "consolidate embedding onto the
API service" idea (avoiding two processes each holding ~2.2 GB of weights) no longer
applies, since neither process loads the model. This history is recorded in
[the log](/log.md); the `EmbeddingProvider` Protocol is the seam that would make a
revert a swap rather than a rewrite.

## Re-evaluation triggers

Revisit this decision if:

- Query volume grows enough to make a self-hosted always-on instance cheaper than
  per-token billing.
- The model is upgraded to something larger than Cloud Run's memory limits (8 GB max).
- Ingestion backfills become frequent enough that per-token cost outweighs a
  self-hosted batch path.
- Berget availability or data-residency terms change.
