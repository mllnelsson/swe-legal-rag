---
type: Reference
title: Cost Estimate (Idle / Low Usage)
description: The idle and low-usage monthly cost breakdown across Cloud SQL, Cloud Run, Pub/Sub, GCS, and usage-based LLM/embedding calls.
tags: [cost, budget, gcp]
timestamp: 2026-07-24T00:00:00Z
---

# Cost Estimate (Idle / Low Usage)

- **Cloud SQL** (db-f1-micro): ~$7–10/mo
- **Cloud Run**: ~$0 at idle (scale to zero)
- **Pub/Sub**: pennies at this volume
- **GCS**: pennies for ~1000 PDFs
- **LLM API** (query time): Berget.ai per-task model pricing (Mistral Small/Medium, GLM
  5.2) — a handful of queries/day plus per-document ingestion calls is <$5/mo at this
  scale; Gemini remains an alternative if `LLM_PROVIDER=gemini` (see
  [LLM pricing](/reference/llm-pricing.md)).
- **Embedding hosting**: Berget-hosted `intfloat/multilingual-e5-large` (~€0.03/M tokens)
  — effectively $0 at this scale, no self-hosting, no `min-instances` decision (see
  [embedding hosting](/decisions/embedding-hosting.md)).

**Total idle: ~$7–15/mo** (Cloud SQL + Cloud Run + Pub/Sub + GCS; LLM/embedding cost is
usage-based, not idle).

Scaling to 5000 docs: Cloud SQL stays the same, embedding cost scales linearly but is
one-time, query costs unchanged. This is the target behind [NFR2](/prd.md).
