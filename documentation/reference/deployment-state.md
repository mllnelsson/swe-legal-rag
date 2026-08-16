---
type: Reference
title: Deployment and Data State
description: What is actually deployed (nothing) versus what is actually ingested (a real local corpus) — and which classes of change are therefore free, which now carry a real cost, and which never depended on either.
tags: [state, deployment, data, migrations, scope]
timestamp: 2026-08-16T00:00:00Z
---

# Deployment and Data State

**Review this before the first deploy or before recreating a table.** It is a
statement of fact about a moment, and every conclusion below depends on that fact
still holding. "Nothing is deployed" and "nothing is ingested" used to be the same
fact; they no longer are, and this page is written to keep them separate.

## What exists

| | Status |
|---|---|
| Deployed environments | **None.** No Cloud Run service, no Cloud SQL instance, no GCS bucket, no Pub/Sub topic in use. [The GCP layout](/reference/gcp-layout.md) is a target, not a description |
| Running configuration | Local only: `STORAGE_BACKEND=local`, `QUEUE_BACKEND=sync` |
| Ingested corpus | **Real.** 184 documents, 1610 chunks (all embedded), 446 entities, locally crawled — not throwaway hand-testing rows, and not reproducible by re-running the pipeline: the source is what the crawl API served on the day it ran, not a fixed corpus the crawler can fetch again |
| API consumers | None. Nothing outside this repository calls `/api/chat` or reads the SSE stream |

The one standing assumption is the local database: Postgres at `DATABASE_URL` has
`alembic upgrade head` applied, and `overklagan_test` exists for integration tests. See
[local dev](/playbooks/local-dev.md) for how it got there.

## What follows from nothing being deployed

- **A breaking config or environment change needs no deprecation window**, no alias, no
  back-compat shim. Removing `LLM_PROVIDER=berget` as an accepted value was such a
  change and was correct to make outright. This depends on there being no deployed
  consumer to break, not on the corpus being empty — it still holds.
- **The API and SSE contracts need no versioning.** See the
  [chat endpoint](/api/chat-endpoint.md). Nothing outside this repository calls it, and
  its only client is [agent mode](/frontend/overview.md) in this repository — which
  ships in the same commit as any change to it. Same reasoning: this is about consumers,
  and there are none.

## What no longer follows from an empty corpus, because the corpus is not empty

- **A schema change is no longer free to recreate.** The ingested corpus is locally
  crawled data that re-running the pipeline does not reproduce, so a migration that
  drops and rebuilds a table now destroys real, non-reconstructible data. Alter in
  place, or export first; "drop and rebuild is as correct as alter, and usually
  clearer" no longer holds.
- **Changing the embedding model, dimension or either prefix now costs a real
  re-embed of 1610 chunks**, not zero rows. [Embedding
  dimension](/decisions/embedding-dimension.md) warns that such a change invalidates
  every stored embedding; that warning is live rather than inert. See [re-embedding
  after an embedding-config
  change](/playbooks/live-testing.md#re-embedding-after-an-embedding-config-change)
  for the procedure.

## What does not follow

- The Alembic history is still the schema's source of truth. Recreating a table means
  writing a migration that recreates it, not editing an old one or reaching for
  `create_all`.
- `llm_config.yaml` is checked in and shared. Nothing about the deployment or data
  state is a reason to hard-code a value that belongs in it.
- None of this licenses skipping tests, linting or type-checking. Those guard the code,
  not the data.

## When this goes stale

The moment something is actually deployed — a Cloud Run service, a Cloud SQL instance
serving traffic, an external caller of `/api/chat`. When that happens, the "What
follows from nothing being deployed" conclusions above have to be re-earned, the same
way the ingestion-side conclusions already had to be once the corpus stopped being
empty.
