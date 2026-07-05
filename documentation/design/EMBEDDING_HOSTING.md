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

## Decision

**Option 1 (Cloud Run `min-instances: 0`)** selected for launch. Rationale:

1. **Simplicity** — no additional services, same code path everywhere.
2. **Zero idle cost** — matches the project's scale-to-zero philosophy at launch.
3. **Clear upgrade path** — flip `min-instances` to `1` when cold starts become a problem (~$15-30/mo).
4. **Fallback path** — if a different approach is needed, Option 2 (HF Endpoints) is a straightforward migration via the existing `EmbeddingProvider` abstraction.

## Re-evaluation Triggers

Revisit this decision if:
- Query volume increases enough to require multiple always-on instances (cost scales linearly).
- The model is upgraded to something larger that doesn't fit in Cloud Run's memory limits (8 GB max).
- Budget constraints require eliminating the always-on cost entirely.
