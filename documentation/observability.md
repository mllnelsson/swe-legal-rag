---
type: Concept
title: LLM Observability
description: How every LLM and embedding call is captured to a local file, one file per call, correlated by directory — the record schema, the correlation keys, and the wiring every process must do.
tags: [observability, cost, tracing, llm]
timestamp: 2026-08-28T00:00:00Z
---

# LLM Observability

Every call to a language model or a hosted embedding endpoint is written to a local
JSON file holding the full prompt, the full response, token counts, and latency. This
is independent of the [`StorageBackend`](/packages/shared.md) that holds the PDFs —
traces never went through it, and there is no GCS trace path: this project's cloud
deployment is shelved in favour of a local stack, so a local file is the only backend
that exists or needs to.

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
- **Structured application logging.** Traces are not a log; see [Application
  Logging](/logging.md) for the split. A log line records that something
  happened — a request came in, a route ran, a step finished — with any text it
  carries limited to a 120-character preview, while a trace record carries the
  full call: the whole prompt, the whole response, the token usage. Both are
  correlated by the same `interaction_id`, so a request's log line and the
  trace records the turn it started produced are found by the same key.
- **Tool definitions.** A trace records which tools were *called* and with what
  arguments, never which tools the model was *offered* — a change to a tool's
  description or parameter schema leaves no trace of the change itself, only of
  how the model then behaved.
- **The last iteration's own tool results, when nothing calls again.** A
  `tool_loop` record's `messages` carries the *previous* iteration's tool call
  and result as history, so the final call's result is only ever written into a
  record that never gets made. Benign for chat: the loop ordinarily ends on the
  terminal `answer` tool, whose arguments are captured directly in
  `response_tool_calls`, and `answer` executes no further tool. A run that
  instead ends by raising `MaxIterationsError` loses the record of whatever its
  last tool call actually returned.

## Record schema

`schema_version` is `1`. It is bumped only when a field changes meaning or
disappears — adding a field does not break a reader and does not bump it.

```json
{
  "schema_version": 1,
  "id": "3f9a1c2d4e5b6789a0b1c2d3e4f56789",
  "started_at": "2026-07-27T10:15:33.123456Z",
  "latency_ms": 812,
  "operation": "tool_loop",
  "provider": "berget",
  "model": "zai-org/GLM-5.2",
  "success": true,
  "error": null,
  "messages": [
    {"role": "system", "content": "…", "tool_calls": [],
     "tool_call_id": null, "tool_name": null}
  ],
  "response_text": "",
  "response_tool_calls": [{"id": "…", "name": "search_decisions",
                           "arguments": {"query": "…"}}],
  "usage": {"input_tokens": 1234, "output_tokens": 88, "total_tokens": 1322},
  "context": {"source": "agents.chat", "prompt": "CHAT_ORCHESTRATION",
              "interaction_id": "…", "agent_run_id": "…", "session_id": "…",
              "tool_loop_iteration": 2}
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
| `usage` | Provider-reported token counts. With `model`, this is the raw material that cost is derived from. |
| `context` | The caller's correlation values, passed through verbatim. |

**There is no cost field, and no rate table in this repo.** `model` and `usage` are
the complete raw material; applying a price to them is an analysis question. See
[Costing a trace](#costing-a-trace).

### Reading the nulls

A reader that treats these as zero will silently under-report.

| Value | Means |
|---|---|
| `usage: null` | The provider reported no token counts. **Not zero.** |
| `usage.output_tokens: null` | That counter was absent. Always so for embeddings. |
| `response_text: null` | Nothing was produced. `""` means it succeeded and produced empty text. |
| `model: null` | Neither the response nor the config named one, so the call cannot be priced. |

## Costing a trace

The pipeline records what a call *used*; it never prices it. A record carries the
served `model` and the provider's `usage`, and cost is a pure function of those two —
so pricing is done when the traces are analyzed, with whatever tool the analysis uses.

That is why there is no cost field, no rate table and no costing CLI in this repo.
Computing it at write time would freeze a rate that may be wrong or, as today, missing
entirely: the Berget-hosted models this project runs by default have no published rate
here, so every record would carry a null that could never be filled in. Applied on
read, obtaining a rate later prices **every trace already written**.

Rates and the rules for applying them are in
[LLM pricing](/reference/llm-pricing.md) — including that unpriced is not zero, and
that `usage: null` means "not reported".

```bash
# tokens by model for one day, the input to any cost calculation
cat data/llm-traces/2026-07-30/*/*.json \
  | jq -s 'group_by(.model) | map({model: .[0].model, calls: length,
           input: (map(.usage.input_tokens // 0) | add),
           output: (map(.usage.output_tokens // 0) | add)})'
```

### A successful record whose response will not parse

`generate_structured` records **before** validating the JSON. The call was made
and billed regardless of whether the schema matched, so a violation is a
caller-side failure, not a provider one. It shows up as `success: true` with a
`response_text` that will not parse — which is exactly the artefact needed to
fix the prompt.

## Storage layout

One file per billed call, one directory per unit of work — the directory *is* the
correlation index, so no reader script or `StorageBackend.list()` has to reconstruct
it:

```
{LOCAL_STORAGE_PATH}/{LLM_TRACE_KEY_PREFIX}/{YYYY-MM-DD}/{interaction_id}/{HHMMSS.ffffff}-{source}-{id8}.json
```

A real chat turn (from a scripted-provider smoke test — no live model run has
produced traces in this repo):

```
2026-08-14/3f9a1c2d-.../125510.465743-agents.chat-bf46bfd6.json
2026-08-14/3f9a1c2d-.../125510.467835-agents.chat.read-75dc0f72.json
2026-08-14/3f9a1c2d-.../125510.470813-ai.synthesize_answer-a32d3d47.json
```

- **The date** rolls a day's traces into one directory, so "what did today cost" is
  still a single top-level prefix.
- **The interaction directory** is what makes "what did this request cost" a sum over
  one folder rather than a scan filtered by `context.interaction_id` — `ls` shows the
  shape of a turn at a glance. See [correlation](#correlation--the-wiring-invariant)
  for who opens it.
- **`agents.chat.read`'s record carries `operation: "generate_structured"`.** The
  [reader](/retrieval/chat-agent.md#reading-a-decision-is-a-sub-agent) answers via a
  JSON schema (`ReadingSelection`) rather than free text, so its record parses and
  reads the same way `ai.expand_query`'s or `ai.extract_metadata`'s does.
- **The filename** sorts into call order, since time-of-day comes first. `{id8}` is
  the record's own `id` truncated to 8 characters — timestamps alone would be enough
  while calls run sequentially, but this keeps filenames unique if tool calls ever run
  in parallel.
- **`_unscoped`** stands in for `{interaction_id}` when a record arrives with no
  interaction id in context. This makes a gap in the wiring invariant visible on disk
  rather than leaving it a rule in a document — a growing `_unscoped` directory is a
  bug reporting itself.

Path components are built from the (client-suppliable) interaction id and the
caller-set `source`, so both are whitelisted to `[A-Za-z0-9._-]` before becoming a
path segment — a hostile id cannot escape the trace root.

**This is why a local dev reloader must not watch `data/`.** A trace file lands
under `data/llm-traces/` on every LLM/embedding call; a `uvicorn --reload` run from
the repo root would watch that directory too and reload the server on its own
traffic. The documented dev command scopes the reloader with `--reload-dir
packages` — see [local dev](/playbooks/local-dev.md#typical-dev-workflow) and
[live testing](/playbooks/live-testing.md#running-the-api-server).

### Writes are synchronous

Each record is written whole: serialized, written under a `.tmp` name, then moved
into place with `os.replace`. A reader never sees a partial file, and two writers
never contend — different records always resolve to different paths, so there is
nothing to lock.

**This puts a file write on the event loop, ahead of the next LLM call.** On local
disk that is tens of microseconds per call — on the order of 2ms across a whole chat
turn, against the one-minute NFR1b budget — worth stating because it is a deliberate
trade, not an oversight. It would be the wrong trade over a network filesystem or an
object store, where the same write could stall for whole seconds; that is the
condition under which buffering onto a background writer should come back, not
before.

Prompts are never truncated, so a full backfill's worth of traces is still large — a
per-call, per-file layout does not change that, only where the bytes land.

## Correlation — the wiring invariant

**Every process that makes LLM calls must call `install_file_tracing()` once at
startup, and must set a `trace_context` at each unit-of-work boundary.** Without
the context a record still lands, but nothing ties it to the work that caused
it, and cost questions become unanswerable.

`install_file_tracing()` is idempotent: a call after one has already succeeded
returns the recorder already installed rather than building another. This is what
lets [`scripts/run_pipeline.py`](/packages/overview.md) compose several workers'
`subscribe()` functions into one process — each calls `install_file_tracing()`
independently, and only the first actually builds a `FileTraceRecorder`. It takes no
storage backend argument: traces are local files, resolved from `LOCAL_STORAGE_PATH`
directly, not through `shared.create_storage_backend`.

| Key | Set by |
|---|---|
| `interaction_id` | `interaction_scope()`, defined in `agent_kit.tracing` and re-exported as `ai.interaction_scope()` (`packages/ai/src/ai/_tracing_scope.py`) — an explicit id wins; failing that, one already in the trace context is **inherited**; failing that, one is **minted**. Opened around the whole request by `api/routes/chat.py` and `api/routes/sql.py` (the id resolved from the `X-Interaction-Id` request header — see below) and by `api/routes/search.py` (source `api.search`, no header, always mints); opened again by `agents.sql.run_sql_agent` itself, and — for chat — by `agent_kit.run_agent`, which `agents.chat.run_chat_agent` configures with `source="agents.chat"` rather than opening the scope itself; either way this is what lets `query_corpus` join the turn that called it instead of starting one of its own; and opened by every non-API entry point too — `ai.worker_trace_scope(source)` (one per queue message), `scripts/run_step.py` (one per step dispatch) and `scripts/run_agent.py` (one per case), all of which mint since none has anything to inherit from. See [below](#every-unit-of-work-opens-an-interaction) |
| `agent_run_id` | `agent_run_scope()`, same module — **always mints**, never inherits. Opened once per sub-agent invocation: by `agent_kit.run_agent` for the whole chat turn, by `run_sql_agent` for itself, and by each `read_decision_text` reading. A turn may make several `query_corpus` calls and read up to `chat_agent_max_documents_read` decisions, and those otherwise share every key they carry; this is what keeps them apart |
| `session_id` | The API, inside the SSE generator in `api/routes/chat.py` |
| `document_id`, `task_id` | Each worker, via the `MessageScope` `ai.worker_trace_scope(name)` supplies to `shared.worker.subscribe_step`, entered around `asyncio.run` inside its `handle_message` |
| `document_id`, `task_id` | `scripts/run_step.py`, around the step dispatch in `_run_step` |
| `run_id`, `case` | `scripts/run_agent.py`, around each input in `run_cases` — the join back from a batch run's JSONL record to the trace(s) it produced |
| `source` | The innermost code that knows what the call is |
| `prompt` | `ai/services.py`, from the template's name |

### Every unit of work opens an interaction

The [storage layout](#storage-layout) needs a directory name for every record, so
`ai.worker_trace_scope(source)`, `scripts/run_step.py` and `scripts/run_agent.py` each
open an `interaction_scope` around their unit of work — one per queue message, one per
step dispatch, one per case — exactly like the API opens one around a chat turn. Before
this, those three set only `document_id`/`task_id` or `run_id`/`case`.

Those keys **remain** as ordinary context fields alongside the minted `interaction_id`,
rather than folding into the directory name — "what did ingesting document X cost" is
still answered by grepping records for `context.document_id`, not by a path shortcut,
because one document spans several worker messages, each minting its own interaction
and its own directory.

`source` says **what the call is**, not who asked for it — *who* is
`interaction_id` or `document_id`. Values: `ai.decompose_query`,
`ai.expand_query`, `ai.extract_metadata`, `ai.extract_entities`,
`ai.summarize_document`, `ai.synthesize_answer`,
`ai.embed`, `agents.sql`,
`agents.chat.plan`, `agents.chat`, `agents.chat.read`, `api.chat`, `api.search`, `worker-chunk`,
`worker-embed`, `worker-extract`, `worker-metadata`, `scripts.run_step`,
`scripts.run_agent`. Contexts nest and merge; on a key collision the innermost
wins — which is exactly why `api.chat`/`api.search` and the `worker-*`/
`scripts.*` names, all of them outer attributions, never actually reach a
record: the `ai.*`/`agents.*` source set by the call itself always overrides
them. `source` still needs to name them, because that is what "the innermost
wins" means in practice — the outer value is the one a nested call replaces.

`agents.chat.plan` is **exactly one record per turn** — the plan step is a
single call, on `LLMRole.CHAT`, that either replies directly or hands the
executor a plan by calling `begin_research`. `agents.chat` then appears **once
per executor tool-loop iteration**, on `LLMRole.ORCHESTRATE`, because each is
its own billed call — a five-step run produces five records under that
source, plus one `ai.synthesize_answer` for the streamed answer, plus
`agents.sql` and `agents.chat.read` for whichever sub-agents the executor
reached for. A turn that needed no retrieval is **one** `agents.chat.plan`
record and nothing else: the plan step calls no tool and writes the reply
itself, so no executor loop and no synthesis call ever run. That shape is
itself diagnostic — a turn whose executor loop runs five iterations for a
question that should have been a direct reply means the plan step chose
research when it should have replied. All of them carry
the same `interaction_id`: `run_chat_agent` and `run_sql_agent` both open an
`interaction_scope`, which **inherits** the id the API already put in context
rather than minting a second one. A run started outside the API — from
[`scripts/run_agent.py`](/playbooks/live-testing.md) — has no id to inherit, so
`interaction_scope` mints one there instead; either way the run is correlated.

### The client-supplied interaction id

`POST /api/chat` and `POST /api/sql` both accept a request header
`X-Interaction-Id` and always return one, resolved by
`api.correlation.resolve_interaction_id()`. Honoured only when it parses as a
UUID — anything else is silently ignored and an id is minted instead, the same
way an unrecognized `session_id` silently starts a fresh session rather than
erroring. The value lands in the `context` of every trace record the request
produces and becomes the key those records are searched by, so arbitrary client
text would be both an injection surface and a collision risk. A supplied id is
canonicalised with `str(uuid.UUID(...))`, so one id has one stored spelling
regardless of case or brace form.

The response header always carries the id actually in use, which is what lets a
client that reports a bad answer be pointed straight at the trace records that
produced it — a header survives a turn that ends in `event: error`, where a
`done` event (which also carries no id today) never arrives.

`ai.expand_query` is the only source that appears on the otherwise LLM-free
[deterministic search](/retrieval/deterministic-search.md) path, and only when a
caller sets `expand: true`. Its absence from a search's trace is therefore
meaningful: it says the result was reproducible without a model.

`run_agent.py`'s `run_id`/`case`, unlike its `source`, are never overridden by
anything further in: they are this script's own keys, and they survive onto
every trace record a case produces regardless of how many calls the task
inside it makes.

**The manual runner used to be a hole in this invariant.**
[`scripts/run_step.py`](/playbooks/live-testing.md) never called
`install_file_tracing()`, so every `metadata`, `extract`, `chunk` and `embed` run it
performed made real, billed calls that were never recorded — and because tracing failing
open is by design, nothing complained. It now installs tracing in `_dispatch` and sets
the context in `_run_step`, like the workers do. If a process makes model calls and is
not in the table above, it is a hole of the same kind.

### Two placements that are load-bearing

**In the chat route, resolving the id and entering the context are two
separate steps, in that order.** `resolve_interaction_id()` runs in the
handler body, before the `StreamingResponse` is built, because the response
headers — including `X-Interaction-Id` — are sent before Starlette starts
draining the generator; an id resolved inside the generator could never reach
them. The `trace_context` itself is still entered *inside* the generator,
because Starlette drives that generator *after* `chat_endpoint` has returned —
a context entered around the handler body would have exited before the first
token. Entered inside, it spans every iteration of the agent's tool loop, both
sub-agents, the embedding and the streaming synthesis alike, all inheriting the
id resolved a step earlier. `POST /api/sql` has no such split: it is not
streamed, so the route resolves the id, sets the response header, and opens the
scope around the single call to `run_sql_agent` in one place.

**In the workers, the context wraps `asyncio.run`, not the coroutine.**
`asyncio.Runner` copies the current context when it builds the loop, so an outer
set propagates in. Setting it after the run would do nothing. `shared.worker.subscribe_step`
enters the `scope` it was given exactly there, around its own internal `asyncio.run` —
`shared` cannot supply the context itself since it must not depend on `llm-core`, so each
worker passes `ai.worker_trace_scope(name)` in; the two workers with no LLM calls
(download, parse) pass no `scope` at all.

## Recorder lifecycle

Each record is written inline, synchronously, before the call it describes returns
control to its caller — see [Writes are synchronous](#writes-are-synchronous) for the
trade that makes.

- **Never raises.** `TraceRecorder.record` must not raise — a stream records from a
  `finally` that may be unwinding under `GeneratorExit`. A record that fails to
  serialize or write is logged and dropped rather than costing the call it describes.
- **No loss window worth naming.** There is no queue and no batch sitting open — a
  record either finished writing or it did not start, so a hard kill loses at most the
  one record in flight, not a window of seconds.
- **Install never fails.** A trace root that cannot be created leaves no recorder at
  all, which llm-core treats as tracing off. Observability must never stop a worker or
  the API from starting.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `LLM_TRACE_ENABLED` | `true` | Off means no recorder and no files. |
| `LLM_TRACE_KEY_PREFIX` | `llm-traces` | Directory name under `LOCAL_STORAGE_PATH` traces are written under. |
| `LLM_STREAM_USAGE` | `true` | Ask the provider for token usage on streams. Switchable because a host that rejects the parameter fails the whole call, and streaming is the user-facing chat path. |

With the repo's default `LOCAL_STORAGE_PATH=./data`, traces land under
`data/llm-traces/`, alongside `data/documents/` — the two keyspaces sharing that root.
Only the PDF keyspace goes through [`StorageBackend`](/packages/shared.md) now; traces
are written directly with `Path`/`os.replace`, never through `store()`.

## What did this question cost

Find the interaction id in the API log (`Chat interaction <uuid> for session
…`) or read it straight off the `X-Interaction-Id` response header — both name
the same value — then read every file under its directory:

```bash
ls data/llm-traces/$(date -u +%F)/<uuid>/
cat data/llm-traces/$(date -u +%F)/<uuid>/*.json \
  | jq -r '[.context.source, .model, .usage.input_tokens,
            .usage.output_tokens] | @tsv'
```

Expect one `agents.chat.plan` row for the plan step, one row per executor
tool-loop iteration under `agents.chat`, one `ai.embed` per search, one
`ai.synthesize_answer` — the last two absent when the plan step replied
directly — and, depending on which tools the executor reached for,
`agents.sql` (itself one row per SQL-loop iteration) and `agents.chat.read`.
Summing the token columns and applying the rates from
[LLM pricing](/reference/llm-pricing.md) is what the question cost.

A chat question is therefore materially more expensive than the single
question-and-answer pair the old pipeline made, and the trace stream is where
that shows up. See [the conversational agent](/retrieval/chat-agent.md) for the
settings that bound it.

**Per-document ingestion cost has no directory shortcut**, because `document_id` is a
context field, not a path segment — one document spans several worker messages, each
minting its own interaction and directory. Grep for it across a day's files instead,
and drop the date to widen it further:

```bash
grep -l "$doc_id" data/llm-traces/$(date -u +%F)/*/*.json \
  | xargs cat | jq -r '[.context.source, .model, .usage.total_tokens] | @tsv'
```

> **On the default configuration the answer is in tokens, not currency.** No
> Berget rate is published in this repo, and guessing one would be worse than
> reporting nothing. Tokens are recorded either way, so a rate obtained later
> prices these same records — see [LLM pricing](/reference/llm-pricing.md).

## Where the code lives

| Concern | Location |
|---|---|
| Hook: record type, recorder Protocol, `trace_context`, `traced_call` | `llm-core`, `_tracing.py` |
| Instrumentation of the four entry points | `llm-core`, `_service.py` |
| Token/model mapping per provider | `llm-core`, `providers/` |
| Blob `store`/`retrieve` — no JSON, no append, PDFs only | `shared`, `storage/` |
| Storage layout, synchronous writes, serialization, `FileTraceRecorder` | `agent-kit`, `tracing/_recorder.py` |
| `interaction_scope`/`agent_run_scope` — the correlation keys | `agent-kit`, `tracing/_scopes.py` |
| Trace root: `install_file_tracing()` supplying `StorageSettings().local_storage_path`, and the re-exports every existing `ai.*`/`agents.*` call site imports | `ai`, `_observability.py` / `_tracing_scope.py` |
| Rates and how to apply them | [LLM pricing](/reference/llm-pricing.md) — reference data, no code |

llm-core carries the hook but never a writer, which is what lets it stay free of
any dependency on the rest of the project; `agent-kit` supplies the writer and the
correlation scopes but takes the trace root as an argument rather than deciding
where traces live, which is what lets `ai` root them under this project's
`LOCAL_STORAGE_PATH` with no change to the path a reader already expects. See
[llm-core](/packages/llm-core.md), [agent-kit](/packages/agent-kit.md) and
[ai](/packages/ai.md).
