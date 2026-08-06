---
type: Concept
title: Generated API types
description: How src/api/schema.d.ts is generated from the FastAPI app's OpenAPI schema, and why a backend contract change surfaces as a TypeScript error rather than a runtime surprise.
tags: [frontend, typescript, openapi, codegen]
timestamp: 2026-08-05T00:00:00Z
---

# Generated API types

The frontend's TypeScript types for the [retrieval API](/api/index.md) are
generated, never hand written. `npm run gen:types` runs
`frontend/scripts/gen-types.mjs`, which imports the FastAPI app
(`uv run python -c "from api.main import app; ...; app.openapi()"`) rather
than calling a running server, and pipes the resulting OpenAPI schema through
`openapi-typescript` into `src/api/schema.d.ts`.

`src/api/{client,queries,types}.ts` build on top of that generated file: typed
`fetch` wrappers, TanStack Query hooks, and the DTO aliases the rest of the
app imports.

## Why importing the app, not calling it

Building the schema this way needs no database connection and no API keys —
just the `api` package importable under `uv`. It runs the same way in CI and
on a laptop with nothing started, and it makes a backend contract change show
up as a TypeScript compile error in the frontend rather than something
discovered at request time.

## Committed, and regeneration is a done-criterion

`src/api/schema.d.ts` is committed to the repo, not built as a Vite step.
Running `npm run gen:types` twice with no backend change in between is
expected to be a no-op — that idempotency is a verified part of what "done"
means for a backend change that touches the API surface.
