---
type: Reference
title: Cost Estimate (Idle / Low Usage)
description: The idle and low-usage monthly cost breakdown across Cloud SQL, Cloud Run, Pub/Sub, GCS, and usage-based LLM/embedding calls.
tags: [cost, budget, gcp]
timestamp: 2026-08-27T00:00:00Z
---

# Cost Estimate (Idle / Low Usage)

- **Cloud SQL** (db-f1-micro): ~$7–10/mo
- **Cloud Run**: ~$0 at idle (scale to zero)
- **Pub/Sub**: pennies at this volume
- **GCS**: pennies for ~1000 PDFs
- **LLM API** (query time): Berget.ai per-task model pricing (Mistral Small, GLM 5.2,
  gpt-oss-120b, Gemma) — a handful of queries/day plus per-document ingestion calls is
  <$5/mo at this scale; Gemini remains an alternative if `LLM_PROVIDER=gemini` (see
  [LLM pricing](/reference/llm-pricing.md)).
- **Embedding**: the checked-in `llm_config.yaml` ships `embedding.provider: local` —
  in-process `sentence-transformers`, no API call, no per-token cost at all, not just a
  small one. Berget-hosted `intfloat/multilingual-e5-large` (~€0.03/M tokens) is the
  alternative if `embedding.provider` is pointed at `berget`, and would itself be
  effectively $0 at this scale — no self-hosting, no `min-instances` decision — but it
  is not what a deploy of the shipped config actually spends. See [embedding
  hosting](/decisions/embedding-hosting.md).

**Total idle: ~$7–15/mo** (Cloud SQL + Cloud Run + Pub/Sub + GCS; LLM cost is
usage-based, not idle; embedding cost is zero on the shipped local config).

Scaling to 5000 docs: Cloud SQL stays the same, query costs unchanged. Embedding cost
stays zero on the shipped local provider — the one-time cost of embedding a larger
corpus is machine time on whichever host runs `worker-embed`, not a metered API bill —
and would only scale linearly (and one-time) under the Berget alternative above. This
is the target behind [NFR2](/prd.md).
