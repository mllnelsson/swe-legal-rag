---
type: Reference
title: Deployment and Data State
description: What is actually deployed and ingested right now — nothing — and which classes of change are therefore free rather than breaking.
tags: [state, deployment, data, migrations, scope]
timestamp: 2026-08-02T00:00:00Z
---

# Deployment and Data State

**Review this before the first deploy or the first full crawl.** It is a statement of
fact about a moment, and every conclusion below depends on that fact still holding.

## What exists

| | Status |
|---|---|
| Deployed environments | **None.** No Cloud Run service, no Cloud SQL instance, no GCS bucket, no Pub/Sub topic in use. [The GCP layout](/reference/gcp-layout.md) is a target, not a description |
| Running configuration | Local only: `STORAGE_BACKEND=local`, `QUEUE_BACKEND=sync` |
| Ingested corpus | **None.** No documents parsed, chunked or embedded beyond throwaway hand-testing rows. There are no stored vectors and no production data |
| API consumers | None. Nothing outside this repository calls `/api/chat` or reads the SSE stream |

The one standing assumption is the local database: Postgres at `DATABASE_URL` has
`alembic upgrade head` applied, and `overklagan_test` exists for integration tests. See
[local dev](/playbooks/local-dev.md) for how it got there.

## What follows

These are the conclusions the state above licenses. They exist because the alternative
— re-deriving them each time, or defaulting to caution — has repeatedly turned routine
changes into imagined migrations.

- **A schema change may recreate rather than migrate in place.** There is no data to
  preserve. A migration that drops and rebuilds a table is as correct as one that
  alters it, and usually clearer.
- **Changing the embedding model, dimension or either prefix costs nothing.**
  [Embedding dimension](/decisions/embedding-dimension.md) and
  [live testing](/playbooks/live-testing.md) both warn that such a change invalidates
  every stored embedding and requires a full re-embed. Both are correct in general and
  inert today: the re-embed is a re-embed of zero rows.
- **A breaking config or environment change needs no deprecation window**, no alias, no
  back-compat shim. Removing `LLM_PROVIDER=berget` as an accepted value was such a
  change and was correct to make outright.
- **The API and SSE contracts need no versioning.** See the
  [chat endpoint](/api/chat-endpoint.md); the only client is the
  [frontend](/frontend/overview.md) in this repository.

## What does not follow

- The Alembic history is still the schema's source of truth. Recreating a table means
  writing a migration that recreates it, not editing an old one or reaching for
  `create_all`.
- `llm_config.yaml` is checked in and shared. "Nothing is deployed" is not a reason to
  hard-code a value that belongs in it.
- None of this licenses skipping tests, linting or type-checking. Those guard the code,
  not the data.

## When this goes stale

The moment either of two things happens: something is deployed, or a full crawl is run
and kept. Check the second with:

```sql
SELECT count(*) FROM documents;
```

A non-trivial count means the corpus claim above no longer holds, and every
"costs nothing" conclusion that depends on it has to be re-earned.
