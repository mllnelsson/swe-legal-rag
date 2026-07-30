---
type: Reference
title: GCP Layout and Local Replacements
description: The GCP service layout, and the thin-interface abstraction that makes every dependency a config swap between GCP and local dev.
tags: [gcp, infrastructure, local-dev, deployment]
timestamp: 2026-07-24T00:00:00Z
---

# GCP Layout and Local Replacements

## GCP services

- **Cloud Run** — API server, pipeline workers, frontend serving. All scale to zero.
- **Pub/Sub** — pipeline orchestration between steps.
- **Cloud SQL (Postgres + pgvector)** — a single small instance; the main standing cost.
- **GCS** — PDF storage.
- **Secret Manager** — API keys for LLM providers (`BERGET_API_KEY` for the default
  Berget.ai provider; `GEMINI_API_KEY` if `LLM_PROVIDER=gemini`).

## Local replacements

Every GCP service has a local equivalent, so swapping local ↔ GCP is a config change, not
a code change:

| GCP Service | Local Replacement | Notes |
|---|---|---|
| Cloud SQL (pgvector) | Postgres 17 + pgvector | Identical SQL interface; `ankane/pgvector` via Compose on Linux, native Homebrew on macOS |
| Pub/Sub | In-process queue or Redis Streams | A synchronous in-process queue works for dev; Redis to test async behavior |
| GCS | Local filesystem or MinIO | A local directory; MinIO for S3-compatible API parity |
| Cloud Run | Local Python process | Run the workers directly — no containerization during dev |
| Secret Manager | `.env` file | Standard dotenv pattern |

**Key principle:** each external dependency sits behind a thin interface (a storage
interface, a queue interface, a database connection-string swap), so switching between
local and GCP is a config change. These abstractions live in the
[shared package](/packages/shared.md); the day-to-day workflow is the
[local dev playbook](/playbooks/local-dev.md).
