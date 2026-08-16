---
type: API Endpoint
title: Health Endpoint (GET /healthz)
description: The GET /healthz liveness check — always {"status": "ok"} when the process is up, with no dependency probe behind it.
resource: GET /healthz
tags: [api, health, deploy]
timestamp: 2026-08-16T00:00:00Z
---

# Health Endpoint (`GET /healthz`)

Defined inline in `create_app` (`packages/api/src/api/main.py`), not in
`api/routes/` alongside the rest of the surface — it is infrastructure for the
process, not a client-facing feature.

## Response

```json
{"status": "ok"}
```

Always this, with HTTP 200, whenever the process is accepting requests. There is
no database check, no storage check, no LLM-role check behind it — a `200` says
the FastAPI app is up, nothing more.

## Why this exists

It is the deploy-time liveness check: a Cloud Run health probe (or any
orchestrator) hits this to decide whether the process should keep receiving
traffic. Composition-root failures that *would* be worth checking — a missing
[`semantic_model.yaml`](/reference/semantic-model.md) entry, a malformed
[`llm_config.yaml`](/reference/llm-config.md) — are already fatal at startup
(see [the semantic-model startup check](/reference/semantic-model.md)), which is
what keeps this endpoint simple: by the time it can answer at all, those checks
have already passed.

Implemented directly in `api/main.py`, served through the [api
package](/packages/api.md). Nothing is deployed yet — see [deployment
state](/reference/deployment-state.md) — so this endpoint has no live caller
today.
