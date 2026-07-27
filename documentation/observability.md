---
type: Concept
title: LLM Observability
description: How every LLM and embedding call is captured to file storage — the record schema, the correlation keys, and the wiring every process must do.
tags: [observability, cost, tracing, llm]
timestamp: 2026-07-27T00:00:00Z
---

# LLM Observability

Every call to a language model or a hosted embedding endpoint is written to file
storage as a JSON record holding the full prompt, the full response, token
counts, latency, and a cost estimate. Records go to the same
[`StorageBackend`](/packages/shared.md) that holds the PDFs, so local
development and GCP behave identically.

Two questions drive the design:

- **What did the model actually see and say?** Answered by storing prompts and
  responses whole, never truncated.
- **How much did this question cost?** Answered by correlation: every call made
  while serving one chat request carries the same `interaction_id`, so the
  answer is a sum over one key.

## What is captured

| Call | Operation | Traced |
|---|---|---|
| `generate` | `generate` | Yes |
| `generate_structured` | `generate_structured` | Yes |
| `generate_stream` | `generate_stream` | Yes, including abandoned streams |
| `tool_loop` | `tool_loop` | Yes, one record per iteration |
| Berget embeddings | `embed` | Yes |
| Local sentence-transformers embeddings | — | No |

One record is emitted per **billed API call**. A tool loop that takes three
turns produces three records, because that is three charges. A stream produces
its record when the stream ends, whether it completed or the consumer walked
away.

### Deliberately not captured

- **The texts passed to the embedding endpoint.** They are chunk text already
  durable in Postgres and reachable from `document_id`; copying the corpus into
  the trace stream would multiply its size for no new information. Only
  `texts_count` and `input_chars` are kept.
- **Local embeddings.** No API call, no token accounting, and a contribution of
  exactly zero to what a question cost.
- **Structured application logging.** Out of scope; traces are not a log.

## Record schema

`schema_version` is `1`. It is bumped only when a field changes meaning or
disappears — adding a field does not break a reader and does not bump it.

```json
{
  "schema_version": 1,
  "id": "3f9a1c2d4e5b6789a0b1c2d3e4f56789",
  "started_at": "2026-07-27T10:15:33.123456Z",
  "latency_ms": 812,
  "operation": "generate_structured",
  "provider": "berget",
  "model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
  "success": true,
  "error": null,
  "messages": [
    {"role": "system", "content": "…", "tool_calls": [],
     "tool_call_id": null, "tool_name": null}
  ],
  "response_text": "{\"filters\": …}",
  "response_tool_calls": [],
  "usage": {"input_tokens": 1234, "output_tokens": 88, "total_tokens": 1322},
  "estimated_cost_usd": "0.00031250",
  "context": {"source": "ai.decompose_query", "prompt": "QUERY_DECOMPOSITION",
              "interaction_id": "…", "session_id": "…"}
}
```

| Field | Meaning |
|---|---|
| `id` | Unique per record. Not a correlation key — see `context`. |
| `started_at` | RFC 3339 UTC, microseconds, always `Z`. The only timestamp; the end is `started_at + latency_ms`. |
| `operation` | One of the operations in the table above. |
| `model` | The model the provider **says it served**, not the one configured. |
| `error` | `null` when `success`, otherwise `{"type", "message"}`. |
| `messages` | The full prompt, every field of every message, never truncated. |
| `estimated_cost_usd` | A **string** or `null`, never a float. |
| `context` | The caller's correlation values, passed through verbatim. |

### Reading the nulls

A reader that treats these as zero will silently under-report.

| Value | Means |
|---|---|
| `usage: null` | The provider reported no token counts. **Not zero.** |
| `usage.output_tokens: null` | That counter was absent. Always so for embeddings. |
| `estimated_cost_usd: null` | Unpriced model or missing usage. **Never `0` as a stand-in** — `"0.00000000"` means genuinely free. |
| `response_text: null` | Nothing was produced. `""` means it succeeded and produced empty text. |
| `model: null` | Neither the response nor the config named one; implies a null cost. |

Cost is a string because floats do not round-trip a `Decimal` and drift when
thousands are summed. Reparse with `Decimal(record["estimated_cost_usd"])`.

### A successful record whose response will not parse

`generate_structured` records **before** validating the JSON. The call was made
and billed regardless of whether the schema matched, so a violation is a
caller-side failure, not a provider one. It shows up as `success: true` with a
`response_text` that will not parse — which is exactly the artefact needed to
fix the prompt.

## Storage layout

Streams roll over daily, keyed `{LLM_TRACE_KEY_PREFIX}/{YYYY-MM-DD}` in UTC.
The two backends lay a stream out differently because object stores cannot
append, and the difference is hidden behind `add_json`/`iter_json`:

| Backend | Layout |
|---|---|
| Local | One file per day: `{LOCAL_STORAGE_PATH}/llm-traces/2026-07-27.jsonl`, one record per line |
| GCS | One object per record: `gs://{bucket}/llm-traces/2026-07-27/20260727T101533123456Z-3f9a1c2d.json` |

**Records within a stream are unordered.** Key order approximates write order on
GCS and completion order locally, and neither is a total order. Anything that
cares sorts on `started_at`, not on the key.

Local appends take an exclusive `flock`. `O_APPEND` is atomic only below
`PIPE_BUF` (4096 bytes) and a record carrying a full decision runs to tens of
kilobytes, so concurrent workers would otherwise interleave partial lines.

Prompts are never truncated, so the streams are large: a full backfill of ~1073
documents at roughly three calls each lands in the 100–300 MB range. The daily
rollover is what keeps any one file openable.

## Correlation — the wiring invariant

**Every process that makes LLM calls must call `install_file_tracing()` once at
startup, and must set a `trace_context` at each unit-of-work boundary.** Without
the context a record still lands, but nothing ties it to the work that caused
it, and cost questions become unanswerable.

| Key | Set by |
|---|---|
| `interaction_id`, `session_id` | The API, inside the SSE generator in `api/routes/chat.py` |
| `document_id`, `task_id` | Each worker, around `asyncio.run` in `handle_message` |
| `source` | The innermost code that knows what the call is |
| `prompt` | `ai/services.py`, from the template's name |

`source` says **what the call is**, not who asked for it — *who* is
`interaction_id` or `document_id`. Values: `ai.decompose_query`,
`ai.extract_metadata`, `ai.extract_entities`, `ai.summarize_document`,
`ai.synthesize_answer`, `ai.embed`, `api.retriever.rerank`. Contexts nest and
merge; on a key collision the innermost wins.

### Two placements that are load-bearing

**In the API, the context is entered inside the SSE generator, not around the
route handler.** Starlette drives that generator *after* `chat_endpoint` has
returned, so a context entered around the handler body would have exited before
the first token. Entered inside, it spans decomposition, embedding, reranking
and the streaming synthesis alike.

**In the workers, the context wraps `asyncio.run`, not the coroutine.**
`asyncio.Runner` copies the current context when it builds the loop, so an outer
set propagates in. Setting it after the run would do nothing.

## Recorder lifecycle

Records are handed to a bounded queue drained by one daemon thread. A trace
write must never sit in front of an LLM call — on the chat path a synchronous
object-store round-trip would surface directly as first-token latency.

Three consequences worth knowing:

- **A bounded loss window.** On `SIGKILL` or a hard crash, whatever is still
  queued is lost. Acceptable for cost telemetry, which is recomputable from
  tokens and cross-checkable against the provider's dashboard. `flush()` covers
  the cases that need certainty; an `atexit` hook flushes on clean shutdown.
- **A full queue drops rather than blocks.** Shedding records beats stalling an
  LLM call behind a slow writer. Drops are logged.
- **Install never fails.** A backend that cannot be built leaves no recorder at
  all, which llm-core treats as tracing off. Observability must never stop a
  worker or the API from starting.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `LLM_TRACE_ENABLED` | `true` | Off means no recorder, no thread, no files. |
| `LLM_TRACE_KEY_PREFIX` | `llm-traces` | Storage key prefix for the streams. |
| `LLM_TRACE_QUEUE_SIZE` | `1000` | Records buffered before dropping. |
| `LLM_TRACE_FLUSH_TIMEOUT` | `5.0` | Seconds `flush()` and shutdown will wait. |
| `LLM_STREAM_USAGE` | `true` | Ask the provider for token usage on streams. Switchable because a host that rejects the parameter fails the whole call, and streaming is the user-facing chat path. |

With `STORAGE_BACKEND=local` and the repo's `LOCAL_STORAGE_PATH=./data/pdfs`,
traces land under `data/pdfs/llm-traces/` alongside the PDF tree. Odd-looking,
but harmless: re-rooting the storage path would break PDF key resolution for
already-downloaded documents.

## What did this question cost

Find the interaction id in the API log (`Chat interaction <uuid> for session
…`), then sum its records:

```bash
jq -r --arg i "<uuid>" 'select(.context.interaction_id == $i)
  | [.context.source, .usage.input_tokens, .usage.output_tokens,
     .estimated_cost_usd] | @tsv' \
  data/pdfs/llm-traces/$(date -u +%F).jsonl
```

Expect at least four rows — `ai.decompose_query`, `ai.embed`,
`ai.synthesize_answer`, plus `api.retriever.rerank` when reranking is on.

The same shape answers the per-document ingestion question against
`.context.document_id`, and the budget question across a whole day:

```bash
jq -s 'map(.estimated_cost_usd | select(. != null) | tonumber) | add' \
  data/pdfs/llm-traces/$(date -u +%F).jsonl
```

> **Costs are null on the default configuration.** Only the two verified Gemini
> rates are seeded; the Berget-hosted models this project runs by default are
> unpriced, so their records carry tokens and a null cost. Sum the token columns
> until rates are added — see [LLM pricing](/reference/llm-pricing.md).

## Where the code lives

| Concern | Location |
|---|---|
| Hook: record type, recorder Protocol, `trace_context` | `llm-core`, `_tracing.py` |
| Instrumentation of the four entry points | `llm-core`, `_service.py` |
| Token/model mapping per provider | `llm-core`, `providers/` |
| Append-style JSON streams | `shared`, `storage/` |
| The file recorder and `install_file_tracing` | `ai`, `_observability.py` |
| Rate table and cost estimation | `ai`, `_pricing.py` |

llm-core carries the hook but never a writer, which is what lets it stay free of
any dependency on the rest of the project. See
[llm-core](/packages/llm-core.md) and [ai](/packages/ai.md).
