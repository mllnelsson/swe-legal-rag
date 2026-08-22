---
type: Concept
title: Generated API types
description: How src/api/schema.d.ts is generated from the FastAPI app's OpenAPI schema, and why a backend contract change surfaces as a TypeScript error rather than a runtime surprise.
tags: [frontend, typescript, openapi, codegen]
timestamp: 2026-08-22T00:00:00Z
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

## The one exception: the chat stream

[`POST /api/chat`](/api/chat-endpoint.md) returns a `StreamingResponse`, so
FastAPI publishes its request body and **nothing about the frames that come
back**. There is nothing for the generator to read, and no amount of
regeneration will produce these types.

`src/api/chat-events.ts` is therefore written by hand against the endpoint
contract, which is its authority. Two consequences follow, and both are handled
rather than tolerated:

* A contract change there is not a compile error. `src/features/agent/progress-labels.test.ts`
  reads `packages/agents/src/agents/chat/_dtos.py` as raw text and asserts the
  client has Swedish words for every `ProgressLabel` the API can emit — so an
  added label fails the build instead of reaching a reader as `decision.audit`.
  A *removed* label is caught from the other side: `progress-text.ts` types its
  two tables as `Record<ProgressLabel, string>`, so the words for a label that
  no longer exists are an excess property rather than dead code nobody notices.
  Fields are covered the same way — `makeSource` in `src/test/factories.ts`
  returns a `SourceReference`, so a field added to the contract fails to
  compile until the factory carries it.
* An unrecognised event name is skipped by the parser rather than thrown on,
  because the contract states that new event types may be added.

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
