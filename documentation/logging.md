---
type: Concept
title: Application Logging
description: What every process in this repo writes to stdout — the one LOG_LEVEL knob, the shared format, the API's per-request envelope and its route metadata, and the previews-not-payloads rule that keeps prompts out of the log.
tags: [logging, observability, api, operations]
timestamp: 2026-09-01T00:00:00Z
---

# Application Logging

Logs record **flow**: what arrived, what ran, how long it took, what it produced.
[Traces](/observability.md) record **payload**: the exact prompt a model saw and the
exact text it returned. The two are correlated by one `interaction_id` and are
deliberately not the same stream — a log with prompts in it is unreadable, and a trace
stream with request timings in it is unsearchable.

## `LOG_LEVEL`

One environment variable, honoured by every entry point in the repo.

| Value | Meaning |
|---|---|
| `DEBUG` | Every step inside a request: search arms, agent tool calls, session lookups, startup stages. |
| `INFO` | Default. One line in and one line out per request, plus what each unit of work did. |
| `WARNING` | Only things that are wrong or surprising. |
| `ERROR`, `CRITICAL` | Failures only. |

Case-insensitive. **Anything else refuses to start**, with a `ValueError` naming the
value and listing what is accepted. That matches `ChatScript` in
[`api/config.py`](/packages/api.md) and is the same stance the whole
`shared.logging_config` module exists to enforce: a logging configuration that is
silently ignored is the failure this code was written to prevent, and quietly serving
INFO to someone who asked for DEBUG is that failure wearing a different hat.

### Where it is read from

`resolve_log_level()` checks `os.environ` first, then reads `.env` **directly** with
`dotenv_values`. The second lookup is not redundant and must not be removed:

> Every entry point calls `configure_logging()` *before* `load_dotenv()`, and in six of
> the seven workers `load_dotenv()` is not in `main()` at all — it is inside
> `subscribe()`. Reading only `os.environ` would make a `.env` `LOG_LEVEL` work under
> Docker Compose, which injects `env_file` into the real process environment, and
> silently do nothing under `uv run`. That asymmetry is worse than either behaviour on
> its own.

`dotenv_values` is read-only and puts nothing into `os.environ`, so no other variable's
resolution order moves. See [`shared.logging_config`](/packages/shared.md).

## The format

```
HH:MM:SS LEVEL   logger.name: message
HH:MM:SS LEVEL   logger.name [interaction]: message     # DEBUG only
```

Structured detail is appended as `key=value` pairs rather than rendered as JSON: this is
a single-user tool read in a terminal, and there is no log aggregator to feed. Values
containing whitespace are quoted, so a field never splits into two.

`shared.logging_config.configure_logging()` installs it with `force=True`, from `main()`
rather than at import — `scripts/run_pipeline.py` imports six workers before running a
line of its own, and `basicConfig` is a no-op once the root logger has a handler. The API
is the exception: `uvicorn api.main:app` makes the *import* of `api.main` the entry
point, so `configure_api_logging()` runs at module scope there. Nothing else imports
`api.main`, so there is no second entry point to fight with.

### The interaction column

At `DEBUG`, every record carries the first eight characters of the request's
`interaction_id`, or `-` outside a request. It is what separates two concurrent chat
turns whose per-step lines interleave. At `INFO` the id appears in full on the `→` entry
line and nowhere else — once per request is enough, and the full value is what a trace
directory is named after.

The id is put on the record by a `logging.Filter` reading the **trace** context
(`agent_kit.llm.current_trace_context()`), not a ContextVar of its own. The API's access
middleware opens `ai.interaction_scope` around the whole request, so records from
`agents` and `ai` — which know nothing about the API — are correlated too.

### uvicorn

`configure_api_logging()` clears uvicorn's own handlers and sets `propagate=True`, so
`Started server process` arrives in the same shape as every application line. It then
raises `uvicorn.access` to `WARNING`: the `api.access` envelope below logs the same
request with strictly more detail, and keeping both means every request logs three lines,
two of which say the same thing in two formats.

Noisy third-party loggers (`httpx`, `openai`, `transformers`, `sentence_transformers`,
…) are damped one step — `WARNING` when the root is `INFO`, `INFO` when the root is
`DEBUG`. "Let me see each step" means this system's steps.

## The API request envelope

`api.access_log.AccessLogMiddleware` is to a request what
[`run_pipeline_step`](/pipeline/worker-patterns.md) is to a pipeline step: the envelope
owns entry, exit, duration and outcome, so a route that logs nothing of its own is still
visible.

| Where | Level | Line |
|---|---|---|
| request arrives | INFO | `→ <method> <path> interaction=<uuid>` |
| response complete | INFO | `← <method> <path> <status> in <duration><fields>` |
| client left mid-stream | INFO | `← … <status> in <duration><fields> aborted` |
| exception escaped the app | ERROR | `✗ <method> <path> failed after <duration>` with traceback, then the exit line |
| `/healthz` | DEBUG | both lines, demoted — a liveness probe every few seconds would bury everything else |

**Exactly one `←` for every `→`.** The exit line comes from a `finally`, so it survives
an exception, a client disconnect and an abandoned SSE stream alike.

Duration is milliseconds below a second and seconds above: a browse endpoint answers in
single-digit milliseconds and a chat turn takes twenty seconds, and one fixed precision
cannot read well for both.

### Why it is raw ASGI

`BaseHTTPMiddleware` hands back control as soon as the response *starts*. On
`POST /api/chat` its exit line would report time to first byte — a fraction of a
twenty-second turn — and would carry none of the metadata the route accumulated while
streaming. A raw ASGI middleware wraps `send` and sees the terminating
`http.response.body` with `more_body` false, which for an SSE stream is the real end of
the answer.

`packages/api/tests/unit/test_chat_route.py::TestChatLogging` guards this: the exit line
must be the last record of the turn, not the first.

### Route metadata

A route contributes to its own exit line by calling `note(request, **fields)`, and
otherwise logs only what is specific to its work — **never a duplicate
started/finished pair**, the same rule
[worker patterns](/pipeline/worker-patterns.md#progress-logging) states for workers. The
fields ride on `request.scope["state"]`, which is one dict shared with the middleware, so
a route can still add to them from inside a streaming generator.

| Endpoint | Fields on the exit line |
|---|---|
| `POST /api/search` | `q`, `hits`, `total`, `queries`, `expanded`, `filtered`, `widened`, `top_sim` |
| `GET /api/filters` | `categories`, `outcomes`, `keywords`, `entity_types`, `documents` |
| `POST /api/chat` | `session`, `tools`, `sql`, `sources`, `answer_chars`, `scripted`, `persisted` |
| `POST /api/sql` | `answered`, `rows`, `truncated`, `iterations`, `attempts` |
| `GET /api/documents` | `count`, `total`, `limit`, `offset`, `filtered` |
| `GET /api/documents/{id}` | `doc`, `found` |
| `GET /api/documents/{id}/chunks` | `doc`, `chunks`, `section` |
| `GET /api/documents/{id}/pdf` | `doc`, `bytes` |
| `GET /api/concepts` | `count`, `total`, `limit`, `offset`, `type`, `q` |
| `GET /api/concepts/{id}/documents` | `entity`, `count`, `total`, `relevance` |
| `GET /api/keywords` | `count`, `total`, `limit`, `offset`, `q` |
| `GET /api/keywords/{id}/documents` | `keyword`, `count`, `total` |
| `GET /api/sessions` | `count`, `total`, `limit`, `offset` |
| `GET /api/sessions/{id}` | `session`, `turns` |
| `DELETE /api/sessions/{id}` | `session`, `removed` |

`answer_chars` and not `tokens`: no token count reaches the chat route — the agent emits
none, and the billed totals live in the [trace records](/observability.md). A field named
`tokens` derived from character counts would read as a bill and be wrong.

### The chat turn's own lines

The route adds what the envelope cannot know:

| Level | Line |
|---|---|
| INFO | `chat started session=<id> msg_chars=<n> history=<n>` |
| WARNING | `chat is SCRIPTED (<name>) — no model was called` (see `CHAT_SCRIPT` in [chat endpoint](/api/chat-endpoint.md)) |
| WARNING | `chat failed in <n>s after <n> tools — <message>` — an `error` event, which is terminal |
| ERROR | `chat crashed in <n>s after <n> tools, session <id>` with traceback |

There is no `chat completed` line. The exit line is the turn's summary.

## What DEBUG adds

| Module | Lines |
|---|---|
| `api.main` | Each lifespan stage, with the embedding provider's load time — the ~9 s (or ~90 s cold) that otherwise presents as a hang; see [local dev](/playbooks/local-dev.md) |
| `api.access` | The query string |
| `api.routes.chat` | The question preview, one line per non-token agent event, time to first token, source count |
| `api.services.search_service` | Query and resolved variants, candidate narrowing, per-arm hit counts, fusion in/out |
| `api.services.chat_toolset` | One line per agent tool call, including the SQL agent's generated query (previewed) |
| `api.services.session_service` | Session created/resumed/unknown, the history window handed to the model |
| `api.services.{document,concept,keyword}_service` | Result counts per query |

### Previews, not payloads

Every piece of free text on its way to a log line goes through
`api.access_log.preview()`, which collapses whitespace and truncates at **120
characters**. Prompts, tool results, chunk text and answer bodies are **never** logged at
any level. They are already captured whole by the [trace files](/observability.md), and
duplicating them into stdout would make DEBUG unreadable and leak a corpus into a
terminal scrollback.

## Where the code lives

| Concern | Module |
|---|---|
| Level resolution, format, root handler | `packages/shared/src/shared/logging_config.py` |
| API process setup, uvicorn adoption, interaction filter | `packages/api/src/api/logging_setup.py` |
| Request envelope, `note()`, `preview()` | `packages/api/src/api/access_log.py` |
| Interaction id resolution | `packages/api/src/api/correlation.py` |
| Pipeline step envelope | `packages/shared/src/shared/pipeline.py` |
