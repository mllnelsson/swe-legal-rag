# Embedding Model Hosting Options

This document captures the evaluated hosting options for the embedding model (`intfloat/multilingual-e5-large`, 1024 dimensions). The model is needed at both **ingestion time** (worker-embed, batch) and **query time** (API server, latency-sensitive). Both paths must use the same model — mismatched models produce incompatible vector spaces.

For model choice rationale, see [ARCHITECTURE.md §7](../specs/ARCHITECTURE.md).

## Constraints

- **Model size:** ~2.2 GB on disk, ~1-1.5 GB RAM at inference.
- **Query-time latency:** Users expect sub-second responses. Cold starts of 30-60s are unacceptable on the query path.
- **Ingestion latency:** Batch processing — cold starts are acceptable.
- **Scale:** ~1000 documents, low query volume (handful of queries/day).
- **Budget:** Minimise standing cost; the system is lightly used.

## Options

### Option 1: Cloud Run with `min-instances: 1` (Selected)

Run the embedding model in-process on the API server's Cloud Run service. Start with `min-instances: 0` (scale-to-zero) and upgrade to `min-instances: 1` when query volume justifies always-on cost.

| Aspect | `min-instances: 0` (launch) | `min-instances: 1` (upgrade) |
|---|---|---|
| **Monthly cost** | ~$0 at idle | ~$15-30 (2 GB instance, always-on) |
| **Cold start** | ~30-60s (model download + load) | None |
| **Model control** | Full | Full |
| **External dependency** | None | None |
| **Local dev parity** | Identical | Identical |

**Pros:**
- Simplest architecture. No additional services, no API calls, no network latency for embeddings.
- Same code path in dev and production.
- Scale-to-zero keeps launch costs at ~$0.

**Cons:**
- Cold start of 30-60s on first query after idle (acceptable at launch with low traffic).
- Each Cloud Run instance carries the full model in memory. If auto-scaling adds instances, each one loads the model independently.
- Container image is large (~3 GB with model weights baked in) or requires model download at startup.

**Upgrade trigger:** When cold starts become a user experience problem (regular users hitting 30-60s waits), set `min-instances: 1`.

**Cloud Run configuration:**
```yaml
min-instances: 0        # Scale-to-zero at launch; upgrade to 1 when needed
memory: 2Gi             # e5-large needs ~1.5 GB + headroom
cpu: 2                  # CPU inference is fast enough for single queries
concurrency: 80         # Default; embedding is fast per-request
startup-cpu-boost: true # Faster model loading on cold scale-up
```

---

### Option 2: HuggingFace Inference Endpoints

Deploy `intfloat/multilingual-e5-large` as a dedicated HuggingFace Inference Endpoint with scale-to-zero.

| Aspect | Detail |
|---|---|
| **Monthly cost** | ~$5-15 (CPU instance at ~$0.06/hr, billed per minute, $0 when idle) |
| **Cold start** | ~30-60s when scaling from zero (model download + load) |
| **Model control** | Full — deploy any HuggingFace model |
| **External dependency** | HuggingFace infrastructure |
| **Local dev parity** | Different code path — local uses `sentence-transformers`, production calls HTTP API |

**Pros:**
- Cheapest option that keeps model control.
- Scale-to-zero means no cost during idle periods.
- Managed infrastructure — no container image to maintain.

**Cons:**
- Cold start on first query after idle period. Can be mitigated with a keep-alive ping, but that negates the cost savings.
- Adds a network hop and external dependency on the query path.
- Requires a `RemoteEmbeddingProvider` implementation in the `ai` package (the `EmbeddingProvider` protocol supports this, but the provider doesn't exist yet).

**Implementation notes:**
- Add `providers/remote_embeddings.py` implementing `EmbeddingProvider` via HTTP POST to the HF endpoint URL.
- Set `EMBEDDING_PROVIDER=remote` and `EMBEDDING_ENDPOINT_URL=<hf-endpoint>` in production.
- Local dev continues using `EMBEDDING_PROVIDER=local`.

---

### Option 3: Vertex AI Embedding API (Google's model)

Use Google's managed `text-embedding-004` via the Vertex AI API instead of self-hosting e5-large.

| Aspect | Detail |
|---|---|
| **Monthly cost** | <$1 ($0.02 per 1M tokens) |
| **Cold start** | None — managed API, always available |
| **Model control** | None — locked to Google's embedding model |
| **External dependency** | Google Cloud Vertex AI |
| **Local dev parity** | None — no local equivalent without API key |

**Pros:**
- Virtually free at this scale.
- No infrastructure to manage, no cold starts, no memory concerns.
- Already within the GCP ecosystem.

**Cons:**
- Locked to Google's model (`text-embedding-004`, 768 dims). Cannot use the benchmark-validated `e5-large`.
- No local dev parity — requires API key and network access even for development.
- Model quality for Swedish legal text is unvalidated against the Scandinavian Embedding Benchmark.
- Different vector dimension (768 vs 1024) would require schema changes if switching back later.

---

### Option 4: Vertex AI Custom Endpoint (GPU)

Deploy `e5-large` as a custom prediction endpoint on Vertex AI with dedicated GPU.

| Aspect | Detail |
|---|---|
| **Monthly cost** | ~$800 (L4 GPU, 24/7) |
| **Cold start** | None — dedicated hardware |
| **Model control** | Full |
| **External dependency** | Google Cloud Vertex AI |
| **Local dev parity** | Different code path |

**Not selected.** Overkill for 1000 documents and low query volume. The cost is 25-50x higher than alternatives for no meaningful benefit at this scale.

---

### Option 5: Berget.ai Hosted e5-large (Selected)

Call the identical `intfloat/multilingual-e5-large` model hosted by [Berget.ai](https://docs.berget.ai), a GDPR-compliant, EU-hosted, OpenAI-API-compatible inference provider, instead of self-hosting it anywhere.

| Aspect | Detail |
|---|---|
| **Monthly cost** | ~€0.03 per million tokens — effectively $0 at this project's scale (~1000-5000 documents, handful of queries/day) |
| **Cold start** | None from this project's perspective — Berget's serverless inference handles its own scaling, not ours |
| **Model control** | Same model (`intfloat/multilingual-e5-large`, 1024 dims) — no dimension change, no migration |
| **External dependency** | Berget.ai inference API |
| **Local dev parity** | Different code path (HTTP call vs in-process `sentence-transformers`) — same as Option 2, but the model itself doesn't need to be downloaded or loaded locally either |

**Pros:**
- No self-hosting at all: no Cloud Run cold-start tradeoff, no `min-instances` decision, no in-process model load (~2.2 GB) on either the API server or `worker-embed`.
- Same model, same dimension as today — purely a hosting/transport change, zero data migration.
- Cheapest option that keeps model control and EU data residency (relevant for Swedish legal documents).
- Reuses the same Berget account/API key already needed for the LLM provider (see [BACKEND_DESIGN.md](BACKEND_DESIGN.md)) — no separate infrastructure to provision.

**Cons:**
- Adds a network hop on the query path (same tradeoff as Option 2), though Berget's serverless inference is designed for this and the project's NFR1 (<5s) budget comfortably covers one embedding call plus retrieval.
- External dependency on Berget's uptime, in addition to whatever LLM provider is configured.

**Implementation:** `packages/ai/src/ai/providers/berget_embeddings.py` — `BergetEmbeddingProvider` implements `EmbeddingProvider` via `openai.AsyncOpenAI.embeddings.create()` (Berget's inference API is a drop-in OpenAI API). Selected via `EMBEDDING_PROVIDER=berget` (the new default), reusing `BERGET_API_KEY`.

---

## Decision

**Option 5 (Berget.ai hosted e5-large)** is now the default (`EMBEDDING_PROVIDER=berget`). Rationale:

1. **Resolves the `min-instances` tension below entirely** — there is no self-hosted model to warm up or scale, so the NFR1 (<5s query)/NFR2 (<$30/mo idle) tradeoff that motivated Option 1 vs upgrading `min-instances` no longer applies to embeddings.
2. **Same model, zero migration** — `intfloat/multilingual-e5-large` at 1024 dims, unchanged from the self-hosted default; `shared.config.EMBEDDING_DIMENSION` and the `chunks.embedding` column are untouched.
3. **Near-zero cost** — €0.03/M tokens is negligible at this project's scale, cheaper than any self-hosted always-on option.
4. **Fallback path preserved** — `EMBEDDING_PROVIDER=local` (the previous default, `sentence-transformers` in-process) remains fully implemented for offline development and tests that shouldn't depend on network access or a Berget API key.

**Superseded: `min-instances` 0 vs 1.** The open question below (originally about self-hosting `e5-large` on the API's Cloud Run service) is **moot for the default deployment** now that embeddings are hosted by Berget rather than self-hosted. It's preserved here for historical context and in case a future re-evaluation trigger (see below) reverts to self-hosting.
>
> **Unresolved (self-hosted case only): `min-instances` 0 vs 1.** ARCHITECTURE.md previously asserted
> `min-instances: 1` was selected while this document asserted `0`. This doc is
> authoritative; the value was treated as **open until Story 12 (GCP Deployment)**,
> where measured idle cost could settle it. The tension is structural, not editorial:
>
> | Setting | NFR1 (<5s query) | NFR2 (<$30/mo idle) |
> |---|---|---|
> | `min-instances: 0` | ❌ 30-60s on first query from cold | ✅ zero idle cost |
> | `min-instances: 1` | ✅ always warm | ⚠️ $15-30/mo, most of the budget |
>
> Note that e5-base would **not** have resolved this — at ~1.1 GB it roughly halves the
> cold start, which is still far outside a 5s target. Any in-process model needs a warm
> path to satisfy NFR1. This entire tension applies only if the project ever moves back
> to self-hosting; it does not apply to the current Berget-hosted default.

## Considered: consolidating embedding onto the API service

**Moot under the current Berget-hosted default** — this was a concern about two
processes each holding ~2.2 GB of `e5-large` weights in-process. With `EMBEDDING_PROVIDER=berget`,
neither the API server nor `worker-embed` loads the model at all; both just make an HTTP
call. Preserved below for the self-hosted (`EMBEDDING_PROVIDER=local`) case only.

Embedding currently runs in **two** processes: the API server loads it at query time
(`api/main.py` → `create_embedding_provider()`, used by `retriever.py`) and `worker-embed`
loads its own copy for batch ingestion. With e5-large that is ~2.2 GB of weights resident
in each.

A proposed alternative is to make the API the single host for the model and have
`worker-embed` call it rather than loading its own instance.

| | Argument |
|---|---|
| **For** | One model instance instead of two; the API is already warm if `min-instances: 1`, so ingestion reuses warmth it is already paying for; worker containers get small and cheap to start. |
| **Against** | Couples batch ingestion to the API's availability and request path; a bulk backfill would drive heavy sustained load through a latency-sensitive service; needs batching/timeout handling that the in-process call does not; loses the "same code path everywhere" property that motivated Option 1. |

**Not decided** (and no longer relevant unless the project reverts to self-hosting).
Recorded here so the option is not rediscovered from scratch. The
`EmbeddingProvider` Protocol is the seam that makes this a swap rather than a rewrite —
an HTTP-backed provider would satisfy the same interface, exactly as Option 2 (HF
Endpoints) and Option 5 (Berget, the current default) do.

## Re-evaluation Triggers

Revisit this decision if:
- Query volume increases enough to require multiple always-on instances (cost scales linearly).
- The model is upgraded to something larger that doesn't fit in Cloud Run's memory limits (8 GB max).
- Budget constraints require eliminating the always-on cost entirely.
- Ingestion backfills become frequent enough that loading the model twice is a material cost.
