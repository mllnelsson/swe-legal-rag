# Documentation Update Log

## 2026-08-16
* **Update**: [Deterministic search](/retrieval/deterministic-search.md) runs its hybrid arms sequentially, not through `asyncio.gather`. They share the request's `AsyncSession`, which permits one operation at a time, so every live `/api/search` call was raising `InvalidRequestError` and returning 500 — a fault no unit test could see, because mocked repositories never suspend.
* **Update**: The [frontend](/frontend/overview.md) is written for a non-technical reader: retrieval-arm names are gone from result cards ([honesty rule 4](/frontend/honesty-rules.md)), the SQL evidence block leads with its rows rather than its `SELECT` (rule 14), agent mode opens with three example questions, and anything that navigates is a link rather than a button that navigates.
* **Update**: [Small screens](/frontend/overview.md#small-screens) — three shared layout classes and one media query stack the two-column pages below 900px, with the rail ordered after the content so results precede filters. A designed-for-mobile layout stays out of scope.
* **Update**: [live testing](/playbooks/live-testing.md) gains a surface-by-surface walkthrough for reviewing the UI on one scripted server.
* **Update**: [chat endpoint](/api/chat-endpoint.md) and [live testing](/playbooks/live-testing.md) — `CHAT_SCRIPT` replays a canned event stream in place of the agent, so [agent mode](/frontend/overview.md) can be looked at without a model call or a minute of waiting. Everything but the events stays real: the SSE framing, the session row, the persisted turn, the rail. The fixtures are built from the `agents.chat` DTOs so they cannot drift from the contract, the answers state that they are fabricated, and every scripted request logs at WARNING.

## 2026-08-15
* **Creation**: Established the [sessions endpoints](/api/sessions.md) — listing, reopening and deleting past conversations. The [sessions table](/data-model/sessions.md) held everything a list needed and nothing could read it. Summaries are projected in SQL so a rail never pulls a transcript, titles are the opening question verbatim rather than model-written, and sessions whose turn never completed are filtered out — a row exists before the agent runs, so every failure left one behind.
* **Update**: [Agent mode](/frontend/overview.md) gains a conversation rail and the `/agent/:sessionId` route. A conversation is now a URL rather than a `useRef`, so it survives a reload. The conversation list is the one query in the app that is not cached forever — asking a question changes it.
* **Creation**: [Honesty rule 21](/frontend/honesty-rules.md) — a reopened conversation shows what was said, not what it rested on. A restored turn renders no source list at all: the empty-source statement rule 19 requires would claim the answer cited nothing, rather than that the citations were not kept.
* **Update**: [sessions](/data-model/sessions.md) is no longer "optional" or a candidate for Redis — reopening a conversation from last week needs the row to outlive the process. The [api package](/packages/api.md) notes that `/api/sessions` is its first mutating endpoint.
* **Creation**: Agent mode in the [frontend](/frontend/overview.md) — the first client for [`POST /api/chat`](/api/chat-endpoint.md), at `/agent`, reached from a Sök/Agent toggle on the home page. Deterministic search is unchanged and keeps its own surface. `EventSource` is not usable (the question travels in a request body), so the client is fetch plus an SSE parser over the response body.
* **Creation**: Added [honesty rules](/frontend/honesty-rules.md) 13–20, covering an answer a language model wrote rather than a search result: what a source may be presented as, that a count is never shown without the query behind it, that `error` is terminal, that a `refused` step is not a failure, and that an aborted turn says the agent will not remember it.
* **Update**: The [conversational agent](/retrieval/chat-agent.md) gains a second terminal tool, `reply_from_context`, and the [chat endpoint](/api/chat-endpoint.md) a matching `answer.direct` label. A greeting, a thank-you or "förklara det enklare" previously either spent ~18 seconds searching for nothing or fell through the evidence gate to "Jag hittade inget i besluten" — [PRD S8](/prd.md) was not actually met.
* **Update**: [chat endpoint](/api/chat-endpoint.md) — `search.refused` is now emitted rather than merely declared. A declined filter reported `search.filtered` with `status: "refused"`, naming a search that never ran. The route's fallback error message is Swedish like the agent's, and SSE frames are no longer `\uXXXX`-escaped.
* **Update**: [LLM Observability](/observability.md) — `ai.reply_from_context` joins the source vocabulary. A turn needing no retrieval is two records; a greeting costing five iterations means the orchestrator is searching when it should be replying.
* **Update**: [generated API types](/frontend/generated-types.md) — the chat event types are hand-written and stated as the one exception, because a `StreamingResponse` publishes nothing about its frames to OpenAPI. A test reads the backend's `ProgressLabel` enum as text so an added label fails the build rather than reaching a user as a raw key.

## 2026-08-14
* **Update**: [LLM Observability](/observability.md) — the trace writer is one synchronous file per billed call under `{date}/{interaction_id}/`, replacing a queue, a daemon thread, batching, a flush protocol and drop accounting. Every justification for that machinery was object-storage-specific, and GCS is off; the directory now *is* the correlation index, so costing a request is a sum over one folder.
* **Update**: [architecture](/architecture.md) and [shared package](/packages/shared.md) — traces no longer go through `StorageBackend`, which now serves PDFs alone. `install_file_tracing()` takes no storage backend.
* **Update**: [LLM Observability](/observability.md) — every unit of work opens an `interaction_scope`, including the pipeline workers and both scripts, since the layout needs a directory per unit of work. A record arriving without one lands in `_unscoped/`, making a wiring gap visible on disk.
* **Update**: [sessions](/data-model/sessions.md) and the [repository layer](/data-model/repositories.md) — a turn is appended by Postgres in one `history || :entries::jsonb` statement. The previous read-modify-write lost a turn whenever two arrived at once; a row lock would instead have been held for the whole streamed turn.
* **Update**: [local dev](/playbooks/local-dev.md) and [live testing](/playbooks/live-testing.md) — four `LLM_TRACE_*` env vars removed, and the trace inspection commands are per-directory over `.json` rather than per-day over batched `.jsonl`.

## 2026-08-13
* **Creation**: Established the [conversational agent](/retrieval/chat-agent.md) — a tool loop over the deterministic retrieval tool set, with a terminal `answer` tool that doubles as the reranking and two sub-agents for reading and counting.
* **Update**: Rewrote the [chat endpoint](/api/chat-endpoint.md) contract and un-deprecated it — progress events carrying a closed `label` key vocabulary the client maps its own words onto, and a mandatory `sql` event.
* **Deprecation**: Removed the five-step chat pipeline (`query_planner`, `retriever`, `answerer`) and `RetrievalSettings` from the [api package](/packages/api.md); `chat_toolset.py` replaces them as the agent's view of the retrieval services.
* **Update**: Added `terminal_tools` to `tool_loop` in [llm-core](/packages/llm-core.md), so a run ends deliberately rather than when the model happens to stop calling tools.
* **Update**: Added the `read` role to [LLM configuration](/reference/llm-config.md) for the document-reading sub-agent, and a `chat` task to the [LLM task runner](/playbooks/live-testing.md).
* **Update**: Split [NFR1](/prd.md) in two — NFR1a keeps the 5-second budget for deterministic search, NFR1b gives an agent turn a one-minute ceiling.
* **Update**: [LLM Observability](/observability.md) — `agent_run_id` is opened by every sub-agent invocation, including each individual reading. A reading previously inherited the orchestrator's, leaving two `read_decision` calls in one turn identical in every correlation key.
* **Update**: [LLM Observability](/observability.md) — one `interaction_id` now spans a whole chat turn. Three call sites each minted one unconditionally and the innermost won, so the API's id reached no record and the SQL sub-agent's iterations sat under an id of their own; per-question cost was undercounted by exactly that sub-agent's spend. `ai.interaction_scope()` inherits an enclosing id and mints only without one, and `ai.agent_run_scope()` adds an `agent_run_id` per agent invocation.
* **Update**: [chat endpoint](/api/chat-endpoint.md) and [SQL agent endpoint](/api/sql-agent.md) accept and return an `X-Interaction-Id` header, honoured only when it parses as a UUID; [api package](/packages/api.md) gains `api/correlation.py` and the CORS `expose_headers` a browser needs to read it back.
* **Update**: [sessions](/data-model/sessions.md) — a turn now stores the `interaction_id` that produced it, and `history_for_llm` projects entries to `{role, content}` so no bookkeeping field reaches a prompt. The documented `timestamp` field never existed in the code.
* **Update**: Corrected stale claims in [live testing](/playbooks/live-testing.md) (source `api.retriever.rerank` does not exist) and [LLM pricing](/reference/llm-pricing.md) (the unpriced-model table omitted the `read` and `sql` roles and listed the embedding model as Berget-hosted when it defaults to local).

## 2026-08-09

* **Update**: [LLM Observability](/observability.md), [local dev](/playbooks/local-dev.md),
  [live testing](/playbooks/live-testing.md), [LLM pricing](/reference/llm-pricing.md) and
  [shared package](/packages/shared.md) — `LOCAL_STORAGE_PATH`'s default moves from
  `./storage` (never matching `.env.example`, and outside `.gitignore`) to `./data`,
  matching the shipped `.env.example` and `docker-compose.yml`. PDFs move from
  `data/pdfs/documents/` to `data/documents/`, and traces from `data/pdfs/llm-traces/` to
  `data/llm-traces/` — two keyspaces directly under the storage root rather than nested
  under a leftover `pdfs/` directory from when a PDF was the only thing stored.
  Observability's apology for traces landing "alongside the PDF tree" is removed as
  obsolete rather than reworded. `shared.md` now states explicitly that
  `LOCAL_STORAGE_PATH` is the root every key hangs off, not a PDF directory. Local dev
  carries the one-line migration for an existing `data/pdfs/` layout
  (`mv data/pdfs/* data/ && rmdir data/pdfs`); an `.env` still setting the old path keeps
  working unchanged since the env var always wins over the default.

* **Update**: [Live Testing Guide](/playbooks/live-testing.md) — documents
  `scripts/run_agent.py`, the LLM-side counterpart to `scripts/run_step.py`: batches an
  AI task (`sql` or `summarize`) over a file of inputs, one per line, recording every
  result — including failures — as a JSONL line, with `ok` and `answered` kept
  deliberately distinct and an `LLM_PROVIDER=none` recipe for smoke-testing the harness
  with no key.
* **Update**: [LLM Observability](/observability.md) — the correlation-key table and the
  outer-attribution list now cover `scripts/run_agent.py`'s `run_id`/`case` context,
  which is the join from a batch run's JSONL record back to the trace(s) it produced.
* **Update**: [SQL Agent Endpoint](/api/sql-agent.md), [agents package](/packages/agents.md)
  — both point at `scripts/run_agent.py` as the way to run `run_sql_agent` over many
  questions without booting the API.
* **Creation**: [semantic_model.yaml reference](/reference/semantic-model.md) — the SQL
  agent's semantic model moved out of hand-written Python dicts and frozensets in
  `agents/sql/_schema.py` into a checked-in, ORM-validated YAML file: file format (the
  bare-string/mapping column shorthand, the `free_text`/`selectable` flags, the worked
  `examples` block), the two-way check against `shared.models.Base.metadata`, the
  `_NEVER_EXPOSED` floor, and the "how to add a column" walkthrough.
* **Update**: [agents package](/packages/agents.md) — new `sql/_semantic_model.py`
  loader module, `sql/_schema.py`'s changed role (a pure renderer, no longer a source of
  prose), the three new `SemanticModel*` errors replacing `SchemaNotesIncompleteError`,
  and the `document` parameter threaded through the guard/tools/agent functions.
* **Update**: [SQL Agent Endpoint](/api/sql-agent.md) — the `TEXT_TO_SQL` prompt now
  carries a worked-examples block alongside the schema, and the agent's knowledge of the
  corpus is sourced from `semantic_model.yaml` rather than hand-typed prose.
* **Update**: [forced grounding decision](/decisions/sql-agent.md) — records why the
  semantic model's ORM-agreement check moved from a unit-test assertion to a fatal API
  startup check, and the `find_predicate_columns` fix that scans predicate segments
  instead of "everything after the first WHERE" so a `JOIN ... ON` no longer forces
  grounding on a column a query only groups by.
* **Update**: [local dev environment](/playbooks/local-dev.md) — run
  `uv run python scripts/check_semantic_model.py` after any migration touching a table
  the SQL agent exposes.

## 2026-08-08

* **Creation**: [agents package](/packages/agents.md), [SQL Agent Endpoint (POST
  /api/sql)](/api/sql-agent.md), [forced grounding decision](/decisions/sql-agent.md) — a
  new text-to-SQL agent converts a Swedish free-text question to a read-only SQL query via
  an LLM tool loop and returns the query and its rows, never an interpreted answer. A
  predicate over a free-text column (`documents.decision_outcome`, `documents.category`,
  `entities.name`) is refused by the tool executor until its values have actually been
  read with `list_column_values`, so a mid-tier model (Mistral Medium) cannot silently
  miscount against near-duplicate or compound values. Read-only Postgres transaction plus
  a static SQL guard; no dedicated database role.
* **Update**: [architecture overview](/architecture.md) — the SQL agent is now the third
  way to query the corpus, alongside deterministic search and the deprecated chat agent.
* **Update**: [backend packages overview](/packages/overview.md) — repo tree and
  dependency graph gain `agents` (depends on `shared` + `ai` + `llm-core`; depended on by
  `api`).
* **Update**: [ai package](/packages/ai.md) — the new `TEXT_TO_SQL` prompt template
  (rendered directly by `agents.run_sql_agent`, not through an `ai/services.py` function)
  and the new `LLMRole.SQL` role, on `mistralai/Mistral-Medium-3.5-128B`.
* **Update**: [llm_config.yaml reference](/reference/llm-config.md) — the new `sql:` role
  entry and its `LLM_MODEL_SQL` override variable.
* **Update**: [per-task LLM model selection](/decisions/llm-model-selection.md) — now four
  roles, not three; added the `sql` row.
* **Update**: [testing strategy](/testing.md) — added the `agents` package's integration
  suite (real read-only sandbox, not just the static guard) to the per-module examples.
* **Update**: [crawl worker](/pipeline/crawl.md), [crawl source](/reference/crawl-source.md),
  [documents](/data-model/documents.md), [data model design notes](/data-model/design-notes.md),
  [indexes](/data-model/indexes.md), [repository layer](/data-model/repositories.md) — crawl
  now de-duplicates on the new `documents.source_decision_number` column, the beslutsnummer
  parsed from the listing headline, because `source_url` and the CMS document id both name
  the *listing entry* rather than the decision and let the listing's own duplicate
  publication of 21/2021, under two document ids, through twice.
* **Update**: [live testing](/playbooks/live-testing.md) — `scripts/run_pipeline.py` now
  re-queues `pending` tasks *before* crawling rather than after; on the sync backend a task
  crawl had just created was still `pending` and indistinguishable from one genuinely
  stranded, so resuming afterwards published every newly discovered document's first task
  twice.
* **Update**: [extract worker](/pipeline/extract.md), [decision document
  structure](/reference/document-structure.md) — cross-reference extraction now matches an
  anchor word followed by a whole citation list, rather than only the first item after it,
  and recognises the year-first beslutsnummer spelling (`beslut 2022/15`) the registry's own
  listing headlines use, via new `shared.segmentation.normalize_cited_decision_number`.
  Identifiers extracted rise from 54 to 116 over the 185-document corpus, with none
  previously found lost.
* **Update**: [llm-core](/packages/llm-core.md), [worker architecture
  patterns](/pipeline/worker-patterns.md), [ai package](/packages/ai.md), [testing
  strategy](/testing.md) — an `OpenAiCompatibleProvider`/`OpenAiCompatibleEmbeddingProvider`
  client is now looked up per call, keyed to the event loop that pooled its connections,
  rather than built once at construction; a client built once was producing 219 retries
  against 221 calls on the 2020-2026 ingest, since a worker's `asyncio.run()`-per-message
  pattern handed the second message a connection whose loop had closed.
  `shared.worker.subscribe_step` gained an injected `teardown` parameter, released by the
  four LLM-calling workers via `ai.close_llm_clients`. Unit tests mock the new
  `llm_core._clients.get_async_openai` accessor rather than a `provider._client` attribute,
  which no longer exists.
* **Update**: [embedding model hosting](/decisions/embedding-hosting.md),
  [local dev](/playbooks/local-dev.md) — corrected drift against the code: the shipped
  `llm_config.yaml` defaults `embedding.provider` to `local`, not `berget`; the
  implementation is `OpenAiCompatibleEmbeddingProvider`
  (`openai_compatible_embeddings.py`), not the earlier `BergetEmbeddingProvider`; and
  `EMBEDDING_PROVIDER=berget`, which both files gave as the default, was never a valid
  value — that variable takes an `EmbeddingBackend` kind, as the
  [env-var registry](/reference/llm-config.md#env-var-registry) already said. The
  decision's rationale for preferring Berget once it is configured is unchanged.
* **Update**: [search result honesty rules](/frontend/honesty-rules.md) — twelfth
  rule: with [query expansion](/retrieval/query-expansion.md) on, the phrasings the
  summary shows are partly a model's rather than the reader's own question, and the
  three outcomes (variants searched, none proposed, expansion unavailable) are
  distinguished rather than collapsed.

## 2026-08-07

* **Update**: [decision document structure](/reference/document-structure.md) —
  `_CASE_NUMBER_RE` now accepts `/` alongside `-`/`–` as the ärendenummer separator
  (the registry wrote `ÖN 2021/2` throughout 2020–2021), and the raw/canonical
  distinction is spelled out so this does not read as contradicting the
  beslutsnummer/ärendenummer disjointness the reference-resolution machinery relies
  on. `_HOLDING_RE` now also matches "Överklagandenämndens beslut" as a bare heading
  on its own line, documented as a new "Holding anchor" section.
* **Update**: [structural fields are parsed, not inferred](/decisions/structural-fields-are-parsed.md) —
  records that `case_number` does reach the LLM fallback when the rule-based pass
  finds nothing, and that its answer is now filtered by
  [`canonicalize_identifiers`](/pipeline/metadata.md#identifier-validation) before
  being accepted, since an unfiltered answer is exactly the "plausible wrong value"
  this decision is written against.
* **Update**: [metadata worker](/pipeline/metadata.md) — new "Identifier validation"
  section documents `canonicalize_identifiers`: an LLM answer for `case_number` or
  `decision_number` is only accepted if it is built from the nämnd's own optional
  markers plus a number, and a rejection is logged as a WARNING naming the discarded
  value.
* **Update**: [extract worker](/pipeline/extract.md) — regulation citations: a
  numeric section range of at most 6 provisions is now expanded into one entity per
  section, a longer range stays whole, and a range or bare chapter subsumed by
  another citation on the same document is dropped. Parish/diocese/pastorat
  matching now takes a bounded run of capitalised words only and strips leading
  role/sentence-opener words, cutting distinct parish entities from 122 to 43 on the
  live corpus; `pastorat` is now a recognised head noun. Persistence now deletes a
  document's stale `document_entities` rows via
  `document_entity.delete_missing_for_document`, so re-extraction replaces a
  document's entity set instead of only adding to it.
* **Update**: [`document_entities`](/data-model/document-entities.md) and the
  [repository layer](/data-model/repositories.md) — record
  `delete_missing_for_document`, and that `document.get_by_case_number` /
  `get_by_decision_number` now tolerate a second matching row (ordering by
  `decision_date`, earliest first) instead of raising, since neither identifier is
  unique in the corpus.
* **Update**: [frontend](/frontend/overview.md) and [query
  expansion](/retrieval/query-expansion.md) — query expansion is now reachable from
  the UI, a checkbox above the filter rail carried in the URL as `?utoka=1`. Removes
  the now-false claim in "Out of scope" that `expand: true` is never sent from the
  frontend.

## 2026-08-06

* **Update**: [local dev](/playbooks/local-dev.md) — `.claude/hooks/db-sandbox.sh
  refresh` now requires `--yes` and refuses without it (exit 64, nothing touched).
  One cluster serves every worktree, so the sandbox it drops is shared with every
  other session and agent on this checkout, and the script cannot tell whose work is
  in it; the confirmation makes that a deliberate choice rather than a side effect.
  `ensure` is unchanged and still needs no confirmation, since it only creates a
  missing sandbox and never drops one — which also means a stale sandbox is the
  expected state rather than a fault. Recorded in `CLAUDE.md` as well.
* **Update**: [deterministic search](/retrieval/deterministic-search.md) and
  [`POST /api/search`](/api/search.md) — the vector arm now applies a cosine-similarity
  floor (`search_min_vector_similarity`, default 0.78, calibrated against the ingested
  corpus), and every chunk carries `vector_similarity`/`text_score` alongside its ranks.
  Without the floor a nearest-neighbour scan answered every query, so an empty result was
  unreachable except through an excluding filter, and the fused RRF `score` — 0.01639 at
  rank 1 for any query whatsoever — could not tell a caller otherwise. Rules 3, 4 and 11
  of the [honesty rules](/frontend/honesty-rules.md) follow from the new response shape.
* **Update**: [frontend](/frontend/overview.md) — clarified that chat is a deferred
  phase rather than a rejected one. The [PRD](/prd.md) still specifies a chat
  interface (S3), a synthesized answer citing case numbers (S6) and conversational
  follow-ups (S8); that work follows once the search functionality is settled, so the
  PRD is deliberately left unamended and this frontend is an interim deliverable
  against it. The previous wording listed chat under "out of scope" alongside auth and
  the marketing site, which read as a decision against it.

## 2026-08-05

* **Update**: [frontend](/frontend/overview.md) rewritten in full — the V1 chat UI it
  described was never built; a React SPA at `frontend/` was built instead, calling only
  the deterministic retrieval API ([search](/api/search.md), [filters](/api/filters.md),
  [documents](/api/documents.md), [document detail](/api/document-detail.md),
  [concepts](/api/concepts.md), [keywords](/api/keywords.md)) and never
  [`POST /api/chat`](/api/chat-endpoint.md) — no SSE, no session, no browser-side LLM call.
  Stack is the reverse of what was planned: Vite + React 19 + TypeScript +
  `react-router` + TanStack Query, plain CSS against the design system's tokens, no
  Tailwind and no shadcn/ui. Records the seven routes, the Swedish-named URL-encoded
  search state, the vendored fonts/icons (no third-party request leaves the page), and
  the known retrieval-side limitation that a nonsense query still scores a confident top
  hit since the vector arm has no similarity floor.
* **Creation**: [Search result honesty rules](/frontend/honesty-rules.md) — the ten
  tested constraints the frontend enforces on what it claims about a search result,
  each one backed by what the corpus or the search API's response shape does not
  support: appendix text is not the nämnd's words, `score` is never shown, `total` is a
  candidate pool not a corpus count, declared vs. inferred entities are styled apart,
  unresolved citations render as text not links, and five more.
* **Creation**: [Generated API types](/frontend/generated-types.md) — `src/api/schema.d.ts`
  is generated by importing the FastAPI app and running `app.openapi()` through
  `openapi-typescript`, needing no database, no API keys and no running server; the
  output is committed, and regenerating it with no backend change is a verified no-op.
* **Update**: [Architecture Overview](/architecture.md) — the frontend line no longer
  claims a streaming chat UI over the chat endpoint; it is a search UI over the
  deterministic retrieval API only.
* **Update**: [chat endpoint](/api/chat-endpoint.md) — no longer describes itself as
  the frontend's wire contract; the frontend never opens this stream. The deprecated
  status and the rest of the contract are unchanged.
* **Update**: [deployment state](/reference/deployment-state.md) — corrected the claim
  that the frontend is the chat endpoint's "only client": the frontend does not call it
  at all, so the endpoint currently has no client in this repository either.
## 2026-08-05

* **Update**: [worker patterns](/pipeline/worker-patterns.md), [shared](/packages/shared.md), [repositories](/data-model/repositories.md) and [live testing](/playbooks/live-testing.md) — `run_pipeline_step` now logs every step's start, duration and outcome, so a pipeline run reports all seven stages rather than only the three that happened to log something of their own (crawl's summary, download's httpx line, embed's chunk count). Parse, metadata and extract gained per-step detail lines; `SyncQueueBroker.drain` reports queue depth and a drained summary; `scripts/run_pipeline.py` closes with a `tasks` count by step and status via the new `task.count_by_step_and_status`. New `shared.logging_config.configure_logging()` replaces seven import-time `basicConfig` calls — importing six workers before configuring meant the composing script's format was discarded and a run logged without timestamps.
* **Update**: [shared](/packages/shared.md), [worker patterns](/pipeline/worker-patterns.md), [live testing](/playbooks/live-testing.md), [local dev](/playbooks/local-dev.md) and [packages overview](/packages/overview.md) — the sync queue backend no longer calls a handler from `publish`; it queues, and `SyncQueueSubscriber.start()` pumps. Inline dispatch could not work: every publish happens inside the publishing step's event loop and every handler opens one of its own, so the first hand-off died with `RuntimeError: asyncio.run() cannot be called from a running event loop`. It was also wrong on its own terms — `run_pipeline_step` publishes *before* marking its task completed, so the whole downstream pipeline ran inside the publishing step's `try` block and a failure in embed rolled back and failed the download task that had already succeeded.
* **Update**: [shared](/packages/shared.md) and [worker patterns](/pipeline/worker-patterns.md) — the async engine is now keyed on the running event loop, with a new `dispose_async_engine()`. An asyncpg connection belongs to the loop that opened it, so the module-level engine handed the second `asyncio.run()` a connection whose loop had closed: `got Future attached to a different loop`. Workers dispose per message, `worker_crawl.__main__` after its own run; the API server keeps one engine and a normal pool, unchanged.
* **Update**: [crawl worker](/pipeline/crawl.md) and [live testing](/playbooks/live-testing.md) — `scripts/run_pipeline.py` now re-drives every `pending` task before pumping (`--no-resume` opts out). Crawl publishes only for documents it has just discovered, so a document stranded by an earlier failure is invisible to it: already in `documents`, therefore skipped, and its pending task is a message nobody sends. This is the gap that left 25 crawled 2026 documents with `download` still `pending` and no way to reach them short of `run_step.py` per document.

## 2026-08-04

* **Update**: [live testing](/playbooks/live-testing.md) and [local dev](/playbooks/local-dev.md) — both still told a reader to run the full sync-queue pipeline as `python -m worker_crawl`, which subscribes nothing and dies on its first publish with `QueueHandlerError: No handler registered for topic: 'download'`. The [2026-07-27 entry](#2026-07-27) below records this same correction landing in live testing once already; it did not survive in the "Option A: Full pipeline" block, and local dev was never covered at all. Both now name `scripts/run_pipeline.py` and state the failure mode explicitly, so the next reader who meets that traceback recognises it rather than re-diagnosing it. Bare crawl remains documented as a single-step, real-queue-backend run.

* **Creation**: [Structural fields are parsed, not inferred](/decisions/structural-fields-are-parsed.md) — records the answer to a question that will be asked again ("should we turn on LLM fallback for the regexes?"): no. Measured against all 25 real corpus documents, every parser failure was a deterministic one-line regex defect, not genuine corpus irregularity; fixing the regexes moved every measured metric to or near 100%. A regex already right on the corpus must not be replaced by a model whose failure mode — a plausible wrong value — is worse than the regex's own failure mode of `None`, since a wrong `case_number` silently misfiles a document and corrupts the reference graph. Records where LLM fallback stays correct instead: open-vocabulary entities, prose-shaped `decision_outcome`/`category`, and generative summaries — and that this round of fixes makes that fallback fire *less*, since its entity-density check sizes its threshold off `body` alone but counted entities across body and appendices together, and appendix entities were going unfound (not the appendix text itself being absent from `body`, which the check never included) on 22 of 25 corpus documents. Cross-linked from the [architectural register](/decisions/architectural-register.md), [document structure](/reference/document-structure.md), [testing](/testing.md), [extract worker](/pipeline/extract.md) and [appendix segmentation](/decisions/appendix-segmentation.md).
* **Update**: [decision document structure](/reference/document-structure.md) — two severe defects, both invisible until measured against the real corpus. `BILAGA A` (upper case, 22 of 25 decisions) was never matched by the old `Bilaga`-only label regex, so those documents' appendix start fell back to end-of-text and the trailer swallowed the appended lower-instance decision whole — 98 983 of 230 550 corpus characters, 43%, absent from the index entirely rather than mis-attributed. Fixed: the label word is matched case-insensitively, the emitted `Appendix.label` is a canonical `Bilaga <id>` never echoed from the source spelling, and the trailer-start anchor now takes the *earliest* matching label rather than the first pattern tried, since the corpus does not fix the trailer's field order. Also documents the new `TrailerField`/`parse_trailer_fields` (order-independent trailer reading), the full-stop keyword separator (the old `,`/`;`-only separator had never split anything — 12 of 25 decisions stored a merged keyword), zero-padded ärendenummer and the `N-YYYY` beslutsnummer spelling, the `source_headline` corroborating source and its trailer-wins precedence, and the new `SegmentationGap` drift signal.
* **Update**: [appendix segmentation](/decisions/appendix-segmentation.md) — records the consequence of the label-casing defect above (43% of the corpus silently unindexed) and corrects the "revisit when both hold" condition 1: segmentation had *run* over the corpus, but the `Bilaga` layout it was verified against was the minority spelling — "has run" and "is known to hold" were not the same claim, and that gap is what let the defect stand undetected.
* **Update**: [metadata worker](/pipeline/metadata.md) — `extract_decision_number`/`extract_category` now take `source_headline` and fall back to it only when the trailer/body have nothing (decision number) or the header line is missing (category); `extract_metadata_rule_based`'s signature changed to `(text, source_headline=None)`. New `_log_template_drift`, called once per document at this step only (extract and chunk re-segment the same text), logs `SegmentationGap`s, a missing-decision-number-everywhere warning, and a trailer/headline disagreement warning — verified silent across all 25 corpus documents.
* **Update**: [extract worker](/pipeline/extract.md) — the kyrkoordningen regulation patterns required the statute's name before the lagrum; the corpus writes it after in 213 of 215 citations, so `EntityType.REGULATION` was an entirely empty vocabulary (0 rows, 0/25 documents). Rewritten to match both orders, both names, ranges written either way, an optional sub-clause, `KO N:M`, the spelled-out form, and chapter-only citations, normalising every match to one canonical `N kap. M § kyrkoordningen` — now 104 rows across 59 names in 24/25 documents (the 25th cites no lagrum). Also notes that `_is_result_complete` sizes its threshold off `body` alone but counts entities across body and appendices together, so while appendix entities were going unfound the check judged results incomplete more often than the extraction warranted — this round of fixes makes the LLM fallback fire less, not just the regulation vocabulary grow.
* **Update**: [chunk worker](/pipeline/chunk.md) — appendix chunking was effectively unreachable for 22/25 corpus documents until the label anchor was fixed; a re-chunk is expected to move `chunks.section = 'appendix'` from a small minority to nearly all documents (appendix characters available to chunk: 9 693 → 106 305 across the corpus).
* **Update**: [documents](/data-model/documents.md) — `case_number` is now zero-padded to `YYYY-NNNN`; `source_headline` documented as a corroborating source for `decision_number`/`category` (trailer/PDF wins) that is never stored split.
* **Update**: [testing](/testing.md) — a parser regression suite must pin the *observed* corpus spelling variants, not an idealised one; both the appendix-label and kyrkoordningen defects above were invisible to their own tests because the fixtures used the minority spelling for the exact thing that turned out broken.
* **Update**: [architectural register](/decisions/architectural-register.md) — one new entry: structural fields stay rules-only, LLM fallback is for open-vocabulary and prose-shaped fields.

## 2026-08-03

* **Update**: [local dev](/playbooks/local-dev.md) — records the coding agent's sandbox database. `overklagan` holds locally crawled data that re-running the pipeline does not reproduce, and an agent deleted rows from it; it is now read-only to agents. `.claude/hooks/db-sandbox.sh` takes a `createdb -T` copy as `overklagan_coding_agent` at session start, `.claude/settings.json` redirects `DATABASE_URL`/`PGDATABASE` there (pinning `TEST_DATABASE_URL`, which the `_test` suffix rule would otherwise derive as `overklagan_coding_agent_test`), and `.claude/hooks/db-guard.sh` refuses any Bash command that would write anywhere else. The guard resolves the connection target before judging the statement, since `psql` takes its database from `-d`, a positional, a URI, a conninfo, `PGDATABASE`, `PGSERVICE` or `$USER` and most of those never name it on the command line; anything unresolvable counts as protected. Grants were not an option — both local login roles are superusers and bypass permission checks.
* **Creation**: [Keywords Endpoint](/api/keywords.md) and [Keyword Documents Endpoint](/api/keyword-documents.md) — the nämnd's own `Sökord` subject classification, previously parsed off the trailer only as a positional anchor and then discarded, is now a first-class [entity](/data-model/entities.md) (`EntityType.KEYWORD`): discovered automatically, linked to documents, browsable, traversable and filterable. No new table and no migration — `entities.type` is a `StrEnum`-backed `VARCHAR`, so a fifth vocabulary member costs nothing (see the [architectural register](/decisions/architectural-register.md)). The new `shared.segmentation.parse_keywords` reads the value; the [extract worker](/pipeline/extract.md) persists it deterministically in every `EXTRACT_STRATEGY` mode alike, always `primary`, dropping any `keyword`-typed entity a strategy tries to emit itself. [`/api/documents/{id}`](/api/document-detail.md) surfaces it as a `keywords` bucket kept apart from `concepts`, since a keyword is *declared* by the decision where the other four entity types are *inferred* from its prose. **This closes the "Sökord is not a facet" known gap** recorded further down this date, differently from how that entry scoped it: as entities, not a column plus migration.
* **Update**: [filters](/api/filters.md) gains a `keywords` facet, and [`/api/documents`](/api/documents.md) / [`POST /api/search`](/api/search.md) gain a `keyword` filter — matching exactly against the published vocabulary, unlike the substring `ilike` `entity_name` uses, since these values are a controlled vocabulary a caller was handed rather than a guess.
* **Update**: [deterministic search](/retrieval/deterministic-search.md) — the LLM-free endpoint count is ten, not eight; `keyword_service.py` follows the same `(AsyncSession, typed pydantic) -> typed pydantic` signature discipline as the other three services, so a future MCP tool wrapper covers it for free.
* **Update**: [extract worker](/pipeline/extract.md), [document structure](/reference/document-structure.md), [chunk worker](/pipeline/chunk.md) and [appendix segmentation](/decisions/appendix-segmentation.md) — corrected the standing claim that `Sökord` was "already structured on documents." It wasn't: nothing held the value. It now is, as entities rather than a column.
* **Update**: [architectural register](/decisions/architectural-register.md) — records the general rule this follows: a new *kind of thing extraction finds* extends `entities` with a vocabulary member rather than getting a dedicated table, unless it needs columns the existing shape cannot express.

* **Deprecation**: [chat endpoint](/api/chat-endpoint.md) is now deprecated but retained — `POST /api/chat` renders `deprecated: true` in the OpenAPI schema, and the four services behind it ([api package](/packages/api.md): `query_planner`, `retriever`, `answerer`, `session_service`) each carry a marker comment. Nothing behavioural changed. This is an ownership signal, not a compatibility window — [nothing is deployed](/reference/deployment-state.md) — recording that the `api` package's purpose is a deterministic retrieval tool set and chat is the one remaining LLM-driven, stateful, streaming surface, expected to move to a future `agent` package. Records the clean extraction set: the four services, `RetrievalSettings`/`SessionSettings`, `ai.decompose_query`/`ai.synthesize`, and the [sessions](/data-model/sessions.md) table — `ai.expand_query` stays behind, since it belongs to [deterministic search](/retrieval/deterministic-search.md). Also updated: [retrieval agent](/retrieval/chat-agent.md) (cross-links deterministic search as the non-agent alternative) and [frontend](/frontend/overview.md) (V1 chat UI keeps consuming the deprecated endpoint unchanged; the retrieval API is the forward path).

* **Update**: [embedding window](/decisions/embedding-window.md), [llm_config.yaml](/reference/llm-config.md) and [local dev](/playbooks/local-dev.md) — new `EMBEDDING_WINDOW_OVERRIDE` escape hatch: set it and no tokenizer is loaded at all, the window being taken on trust and chunk sizes estimated at 2.0 characters per token. Added because the tokenizer requirement was new to worker-chunk and a machine with no hub access and no warm cache could not start at all (verified: `LocalEntryNotFoundError` without it, clean start with it). Environment-only and absent from `embedding:` on purpose — one machine opting out is not the file declaring a second source of truth. The constant is the *densest* Swedish text measured, not the average, so the estimate can only run high: chunks come out roughly half size (12 vs 6 on the traced decisions, worst passage 257/512 vs 475/512) rather than overrunning the window.

* **Creation**: Documented the [retrieval API](/api/index.md) — eight deterministic REST endpoints that reach the corpus without an LLM, shaped as a tool set rather than a UI backend: [search](/api/search.md), [filters](/api/filters.md), [documents](/api/documents.md), [document detail](/api/document-detail.md), [chunks](/api/document-chunks.md), [pdf](/api/document-pdf.md), [concepts](/api/concepts.md) and [concept documents](/api/concept-documents.md). Until now retrieval was reachable only through the SSE [chat endpoint](/api/chat-endpoint.md); there was no way to search, list a decision, walk its citations or read its PDF without going through a model.
* **Creation**: [deterministic search](/retrieval/deterministic-search.md) — the algorithm behind `POST /api/search`, recorded alongside the existing [retrieval agent](/retrieval/chat-agent.md) rather than replacing it. The two differ deliberately on empty filters: the agent widens to an unfiltered search because an answer from a wider net beats no answer, while search returns empty, because answering "nothing older than 2024" with 2019 decisions is a lie. Also records document-grouped ranking (max fused chunk score, tiebroken on matched-chunk count then `document_id`, so metadata is fetched only for the returned page), shallow-by-design paging, and the `diagnostics` block that makes fusion auditable.
* **Creation**: [query expansion](/retrieval/query-expansion.md) — the opt-in, default-off `ai.expand_query`. Four constraints are load-bearing and recorded as such: variants are *additive* rankings into the same `rrf_fuse` with the original always in the pool (so expansion cannot lose a hit); the expander returns strings and never filters (there is no good rule for arbitrating against an explicit client filter); the lexical arm is expanded and the vector arm is not by default; and `queries` vs `expand` keeps the core deterministic, since `effective_queries` is echoed and replays exactly. Records why [`plan_query`/`decompose_query`](/packages/ai.md) were **not** reused — they take conversation history and emit filters, making them a chat planner, not an expander.
* **Update**: [api package](/packages/api.md) — three new routers, three new services, `dependencies.py` (one `get_db` seam shared by every router), generic `Page[T]` pagination, `SearchSettings`, and the transport-agnostic service signature that lets an MCP or WebSocket adapter sit over the same functions. Notes that the package still has no `errors.py` on purpose, and that `llm-core` is now a declared dependency rather than one resolving transitively through `ai`.
* **Update**: [ai package](/packages/ai.md) — `expand_query()` and the `QUERY_EXPANSION` prompt, including why the variant cap lives in the user template (`render()` does not format the system prompt).
* **Update**: [shared package](/packages/shared.md) — `search/filters.py` (`is_empty_filter`, derived from the model so a new filter field cannot go unconsidered), `search/rrf.py` gains `rrf_fuse_scored` and takes arbitrarily many rankings, and `storage/keys.py` makes `documents/{id}/original.pdf` a named contract instead of a literal duplicated across three packages.
* **Update**: [repositories](/data-model/repositories.md) — paged metadata browse, facet aggregation, and the joined graph reads that resolve an edge to the thing on its other end. Records that `_protocols.py` was deliberately **not** extended: it declares what *workers* call, and these are API-only functions imported as modules.
* **Update**: [document entities](/data-model/document-entities.md) — `relevance` is queried for the first time; [document references](/data-model/document-references.md) — both citation directions resolve in one call rather than N+1.
* **Update**: [observability](/observability.md) — new `ai.expand_query` trace source, and the note that its *absence* from a search's trace is meaningful.
* **Update**: [frontend](/frontend/overview.md) — "no manual filters in V1" is now explicitly a frontend scope decision, not a backend limitation; the filter, browse and traversal surface its V2 backlog describes already exists.
* **Known gap, closed later the same day**: recorded in [filters](/api/filters.md) — `Sökord`, the decisions' own subject keywords and the best facet the API could offer, was parsed off the trailer and discarded. Scoped here as pipeline work — a column plus a re-parse — left out of the retrieval API's initial scope rather than deferred for cost. Closed differently from how it was scoped: see the keyword-entity entries at the top of this date.

## 2026-08-02

* **Creation**: [embedding sequence window is observed, not declared](/decisions/embedding-window.md) — bug fix record. Contextual passages were measuring as high as 520 e5 tokens against the model's 512-token window, silently truncated by `sentence-transformers` at embed time. Root causes: the chunk budget was measured in tiktoken `cl100k_base` (~1.37× e5 on Swedish, the opposite of the "undercounts" claim this page used to make) rather than e5's own tokenizer, and the prepended document summary was unbounded. Fix: `ai.create_embedding_ruler()`/`ai.verify_embedding_window()` observe the window from the tokenizer at startup rather than declaring it, `worker_chunk.budget` derives a 349-token chunk budget (34-token overlap, 150-token summary reserve) from it, and `truncate_summary()` enforces the reserve on sentence boundaries.
* **Update**: [embedding model choice](/decisions/embedding-model.md) — the "Token counting for chunking" section was factually inverted (claimed tiktoken undercounts Swedish relative to e5); rewritten to record the measured 1.37× direction and point at the new embedding-window decision. Frontmatter `description` no longer advertises tiktoken; the [decisions index](/decisions/index.md) entry updated to match.
* **Update**: [chunk worker](/pipeline/chunk.md) — new `budget.py`/`errors.py` modules, `split_into_chunks`/`split_document_into_chunks` are keyword-only with no defaults and counted by the embedding model's own tokenizer, `truncate_summary()` enforces the summary reserve on sentence boundaries, two new startup-triggered WARNINGs (summary truncated; chunk over budget), and the `__main__` startup invariant that derives and logs the 512→349/34/150 budget before subscribing.
* **Update**: [embed worker](/pipeline/embed.md) — `process_embedding` gains required `count_tokens`/`max_input_tokens`; an over-long input is warned about and embedded anyway, untruncated, never raised — one degraded chunk beats failing the terminal step and having the message redelivered forever. `__main__` now also calls `ai.verify_embedding_window()` alongside `verify_embedding_dimension()`. Also corrected a stale claim that the default embedding provider is Berget-hosted; `embedding.provider` is config, not a hard-coded default, and currently reads `local` in `llm_config.yaml`.
* **Update**: [data model design notes](/data-model/design-notes.md) — the chunk-sizing rationale named ~500 tokens for retrieval-granularity reasons only; now records the 349-token budget as a derived, hard ceiling against the embedding model's window, per the embedding-window decision.
* **Update**: [llm_config.yaml](/reference/llm-config.md) — documents the `summarize` role's new `max_tokens: 256` (a coarse stop on runaway generation; the enforced ceiling is worker-chunk's `truncate_summary()`, since a provider-side cut lands mid-word) and why `embedding:` carries no sequence-window key.
* **Update**: [ai](/packages/ai.md) — new `tokenization.py` module: `EmbeddingRuler`, `create_embedding_ruler()`, `verify_embedding_window()`, `SPECIAL_TOKEN_COUNT`, `EmbeddingWindowError`. `transformers` is now a direct dependency of the package, same rationale as the existing `numpy` entry.
* **Update**: [Testing Strategy](/testing.md) — a third way to keep a heavyweight optional dependency out of the unit suite, alongside mocking an owned seam or stubbing `sys.modules`: hand the consumer a value carrying the callable (`EmbeddingRuler`), so a fake is a lambda and there is nothing to patch.
* **Update**: [Local Development Environment](/playbooks/local-dev.md) — worker-chunk now needs the e5 tokenizer files (HuggingFace hub access or a warm cache) to start, which it did not before; the container path has no cache mount or bake-in step yet.
* **Update**: [architectural register](/decisions/architectural-register.md) — cross-links the new [embedding sequence window](/decisions/embedding-window.md) decision alongside the other embedding records.
* **Update**: [appendix segmentation](/decisions/appendix-segmentation.md) — the deferred "modelling the prior instance" section now names the candidate shape (one `documents` row per appendix, related to its decision), the three `documents`/`tasks` assumptions it breaks, and two conditions for revisiting: anchors verified corpus-wide, and a real query the current model cannot answer. Parked deliberately rather than rejected — `chunks.section` answers today's questions, and aggregate questions about the instance below are what would justify the table.
* **Creation**: [deployment state](/reference/deployment-state.md) — nothing is deployed and no corpus is ingested, so schema recreation, embedding-model changes and breaking config changes are all free right now. Recorded because the alternative is re-deriving it every time, or defaulting to caution and planning migrations for data that does not exist. Carries its own invalidation condition.
* **Update**: [llm-core](/packages/llm-core.md), [ai](/packages/ai.md), [llm_config.yaml](/reference/llm-config.md), [extract worker](/pipeline/extract.md) and [live testing](/playbooks/live-testing.md) — new `ProviderKind.NONE` / `NullProvider`: a provider that constructs without credentials and raises `LLMDisabledError` on use. Every worker builds its provider in `subscribe()`, so a run of the non-LLM steps previously still needed a key for the steps that were never going to execute. `LLM_PROVIDER=none` disables every role, `kind: none` under `providers:` disables one; `api_key_env` became optional for that kind alone. worker-extract's fallback mode degrades to its regex half at startup and its `llm` mode refuses; chunk is where a no-LLM run stops.
* **Update**: [architectural register](/decisions/architectural-register.md) — records why "no model here" is a provider kind rather than an `LLM_ENABLED` flag: one exhaustive dispatch instead of two switches, and per-role granularity a process-wide flag could not express.
* **Update**: [live testing](/playbooks/live-testing.md) — **correction.** The per-step dependency list said `scripts/run_step.py`'s `metadata` step calls the configured LLM provider. It never has: the script injects `no_llm_extractor`, so only the rule-based pass runs there, unlike the worker.

* **Update**: [llm-core](/packages/llm-core.md) — `ProviderKind` moved here from `ai` and `LLMConfig.provider` is typed as it, so `create_provider` has no fallback case: pydantic rejects an unknown provider when the config is built, and adding a kind without a case is a type error. Removed the `"berget"` legacy value, the per-vendor `berget_api_key`/`gemini_api_key` fields, and `BERGET_BASE_URL`. Providers now require `api_key` and `base_url` and raise the new `MissingCredentialError` without them — a defaulted base URL sends traffic to the wrong host silently.
* **Update**: [ai](/packages/ai.md) — `EmbeddingBackend` takes its `OPENAI_COMPATIBLE` value from `ProviderKind` so the two cannot drift, and lost its `BERGET` member. A host whose kind has no embeddings client is refused by `resolve_embedding_config` with the new `UnsupportedEmbeddingBackendError`, naming the offending YAML key. `BergetEmbeddingProvider` is now `OpenAiCompatibleEmbeddingProvider` — it was host-named but took no host-specific behaviour.
* **Update**: [llm_config.yaml](/reference/llm-config.md) — **the role registry is now closed.** `create_llm_provider` takes an `LLMRole`, and the three zero-argument wrappers and three `ROLE_*` constants are gone; only the wrappers had ever had call sites. Adding a role needs both an enum member and a `roles:` entry, which contradicts the "no Python change required" claim recorded here on 2026-08-01.
* **Update**: [worker patterns](/pipeline/worker-patterns.md) — new `shared.worker` module splits worker startup into `subscribe_step` (register, return) and `serve` (signal handlers, block). `scripts/run_pipeline.py` composes six workers by calling only the first half, so the `signal.SIG_DFL` reset it used to need is deleted rather than preserved.
* **Update**: [LLM Observability](/observability.md) — the worker half of the wiring invariant now runs through `ai.worker_trace_scope`, injected into `subscribe_step` as a `MessageScope`. `shared` must not depend on llm-core and the context must be entered outside `asyncio.run`, which rules out wrapping the handler. worker-download and worker-parse pass no scope; they make no LLM calls.
* **Update**: [extract worker](/pipeline/extract.md) — `process_extraction` takes an injected `strategy`. It used to call the factory inside the step body, constructing an LLM provider per document while every other worker built one at startup. The strategies are plain callables rather than three classes behind a one-method Protocol, `worker_extract/models.py` is deleted in favour of `ai.dtos` (it duplicated it field for field), and `EXTRACT_STRATEGY` moved onto `ExtractSettings` — an unrecognised value is now fatal instead of silently selecting the default.
* **Update**: [embed worker](/pipeline/embed.md) and [embedding dimension](/decisions/embedding-dimension.md) — `process_embedding` takes `expected_dimension`, the width `verify_embedding_dimension` observed, instead of reading a process-wide constant nothing tied to the provider in use.
* **Update**: [architectural register](/decisions/architectural-register.md) — records the closed-enum/arbitrary-name split governing both provider kinds and roles, and the refusal to default a host or carry per-vendor credential fields.

## 2026-08-01

* **Creation**: [llm_config.yaml](/reference/llm-config.md) — the file format, the four-level precedence rules against environment variables, and the full env-var registry. Declared the single source of truth for LLM and embedding configuration, so the near-duplicate `.env` blocks in [local dev](/playbooks/local-dev.md) and [live testing](/playbooks/live-testing.md) could be cut down to links; those two had already drifted apart once.
* **Creation**: [per-task LLM model and provider selection](/decisions/llm-model-selection.md) — the LLM side had no decision record while embeddings had three. Why each task gets its own model, why a role may now name its own *provider* (previously inexpressible, since `LLM_PROVIDER` is process-wide), why Berget for all three by default, and why `LLM_MODEL` is deliberately ignored by role resolution.
* **Update**: [ai](/packages/ai.md) — new `llm_config.py` module: discovery, validation and role/embedding resolution. `LLMRoleConfig` and its three `LLM_MODEL_*` fields are gone; `create_llm_provider(role)` serves an **open** role registry, so declaring `rerank:` in the YAML is enough to use it. A missing or malformed file is fatal by design — silent fallback to built-in defaults is how the documented configuration and the running one drift apart.
* **Update**: [llm-core](/packages/llm-core.md) — `create_provider` dispatches on the provider *kind* (`openai_compatible`, with `berget` kept as an alias), and the new host-agnostic `api_key` field carries a key the caller resolved itself. The long-standing claim that "a second OpenAI-compatible host needs a config value, not a new provider class" is now literally true: it is a `providers:` entry.
* **Update**: [embedding dimension](/decisions/embedding-dimension.md) — the "known hazard, nothing cross-checks them" is now an enforced startup invariant. `verify_embedding_dimension` compares three of the four declarations against each other; the migration's DDL stays outside the check, so recreating the column remains manual.
* **Update**: [embed worker](/pipeline/embed.md) and [retrieval agent](/retrieval/chat-agent.md) — **bug fix.** The retriever prefixed queries with `"query: "` and its comment asserted chunks were embedded with `"passage: "`. Nothing applied it. e5 is asymmetric, and prefixing one side only is worse than prefixing neither. Both prefixes now come from `embedding.query_prefix`/`passage_prefix`, and `process_embedding` takes a required `passage_prefix` with no default — a forgotten default is what caused this.
* **Update**: [live testing](/playbooks/live-testing.md) — a re-embed procedure, required after any change to the embedding model or either prefix. Stale vectors do not fail; retrieval keeps working, silently and badly.
* **Update**: [LLM Observability](/observability.md) — `scripts/run_step.py` joins the wiring invariant with `source=scripts.run_step`. It never called `install_file_tracing()`, so every manual metadata/extract/chunk/embed run made real, billed calls that were never recorded — and since tracing fails open by design, nothing complained.
* **Update**: [architectural register](/decisions/architectural-register.md) — model assignment is a declarative file rather than environment variables.
* **Update**: [local dev](/playbooks/local-dev.md) — the AI env block is secrets plus `EMBEDDING_DIMENSION`; the interface-mapping table points at `llm_config.yaml` for provider selection.
* **Update**: [testing](/testing.md) — integration tests run against their own `overklagan_test` database, resolved from `TEST_DATABASE_URL` or derived from `DATABASE_URL`, and collection aborts rather than truncating if the two name the same database. Schema comes from `alembic upgrade head` via an `-x db_url=` override, not `create_all`. The `integration` marker is applied by directory rather than by hand, and a bare `uv run pytest` is unit-only so an agent cannot reach a database by accident.
* **Update**: [worker patterns](/pipeline/worker-patterns.md) — the integration fixtures live once in `shared.testing.fixtures` as a pytest plugin; a package's conftest declares only its `next_topic`. Rerunning a step re-drives the existing task row, because `tasks` holds one row per (document, step).
* **Update**: [repositories](/data-model/repositories.md) — integration tests inject the repo modules unchanged, the same way production does. `bind_repo` is gone; there is one call convention with `session` first.
* **Update**: [local dev](/playbooks/local-dev.md) — creating `overklagan_test` is part of first-time setup on both platforms, `docker/init.sql` creates it on a fresh volume, and the fixtures migrate it themselves.
* **Update**: [live testing](/playbooks/live-testing.md) — the command table matches [testing](/testing.md), and troubleshooting covers a missing test database and the same-database guard.

## 2026-07-31

* **Update**: [LLM Observability](/observability.md) — `install_file_tracing()` is idempotent: a call after one has already succeeded returns the recorder already installed. [`scripts/run_pipeline.py`](/playbooks/local-dev.md) composes six worker `main()`s into one process and four of them install tracing, which would otherwise leave a stray writer thread and `atexit` hook behind for every recorder the next call displaced.
* **Update**: [architectural register](/decisions/architectural-register.md) — the "no LLM proxy container" entry no longer rests on `flock`-per-append, which is gone. Many processes share one key prefix because the recorder writes each batch as its own uniquely-named object; there is nothing to append to and nothing to lock.

## 2026-07-30

* **Update**: [llm-core](/packages/llm-core.md) — the trace lifecycle is now one `traced_call()` context manager instead of seven hand-driven functions. It owns success, failure and hand-off; callers only fold in the payload via `trace_response`, `trace_chunk` or `trace_outcome`. `start_trace`, `finish_trace`, `trace_failure`, `trace_result` and `trace_stream_completed` are gone from the public API.
* **Update**: [ai](/packages/ai.md) — `BergetEmbeddingProvider` opens its trace with the same `traced_call()` rather than driving the lifecycle by hand, and seeds model/provider on entry so a failed call is still attributed.
* **Update**: [shared](/packages/shared.md) — `StorageBackend` is a five-method blob store again. `add_json`/`iter_json` and the local `flock` machinery are gone: the trace recorder batches records and writes whole JSONL objects with `store()`, so an object store never has to append and the two backends no longer diverge. `iter_json` had no production caller.
* **Update**: [LLM Observability](/observability.md) — one uniform storage layout across backends, `{prefix}/{date}/{timestamp}-{rand}.jsonl` per flushed batch, with the batching triggers, the widened loss window, and why `flush()` asks the writer rather than merely waiting.
* **Update**: [LLM pricing](/reference/llm-pricing.md) — cost leaves the codebase entirely. Records no longer carry `estimated_cost_usd`, and there is no rate table, no `estimate_cost_usd()` and no costing CLI: a record carries the served `model` and the provider's `usage`, which is the complete raw material, so pricing is an analysis step performed against this reference. The page is now dated reference data rather than a spec binding a module, and states the rules (prefix match longest-first, case-insensitive, unpriced ≠ zero, `usage: null` ≠ zero, failed calls still bill) for whoever applies them.
* **Update**: [live testing](/playbooks/live-testing.md) and [local dev](/playbooks/local-dev.md) — trace paths are directory globs, cost verification runs the script, and the two batch env vars are listed.
* **Update**: [llm-core](/packages/llm-core.md) — `generate_structured` is generic in `response_model` (`[T: BaseModel] -> T`) rather than returning a bare `BaseModel`. Removes three `type: ignore[return-value]` in `ai/services.py` and an `assert isinstance` in the API reranker.

## 2026-07-29

* **Update**: [chunks](/data-model/chunks.md) — `embedding` is documented as nullable, which is what the rest of the stack always assumed: `ChunkCreate.embedding` defaults to `None`, `ChunkRead` types it optional, and vector search filters `WHERE embedding IS NOT NULL`. Migration `005` drops the `NOT NULL` that migration 001 imposed, which had made the chunk worker's own insert impossible.
* **Update**: [local dev](/playbooks/local-dev.md) — getting Postgres is now documented per platform: Compose on Linux, native Homebrew `postgresql@17` + pgvector 0.8.5 on macOS. Covers the keg-only `PATH`, the `createuser -s postgres` step that keeps one `DATABASE_URL` working on both, and why `docker/init.sql` is belt-and-braces rather than load-bearing. "Running in Containers" is now scoped as a choice about application code, independent of where Postgres runs.
* **Update**: [architectural register](/decisions/architectural-register.md) records two decisions — **no LLM proxy container** (the `sync` broker, not trace storage, is what keeps the workers in one process) and **platform-dependent local Postgres behind one `DATABASE_URL`**.
* **Update**: [live testing](/playbooks/live-testing.md), [testing](/testing.md), [worker patterns](/pipeline/worker-patterns.md), [GCP layout](/reference/gcp-layout.md) and [packages overview](/packages/overview.md) — integration tests need *a* Postgres on `DATABASE_URL`, not a Docker one; troubleshooting gains the keg-only `PATH` and missing-`postgres`-role cases.

## 2026-07-27

* **Update**: [local dev](/playbooks/local-dev.md) gains a "Running in Containers" section — one image, a one-shot `pipeline` service and an `api` service behind the `app` compose profile, the two env vars the containers override, and why the topology is one pipeline container rather than seven. The "application code runs on the host" claim is now a default rather than a constraint.
* **Update**: [live testing](/playbooks/live-testing.md) and [packages overview](/packages/overview.md) — the full-pipeline run is `scripts/run_pipeline.py`, not `python -m worker_crawl`, which subscribes nothing and fails on its first publish.
* **Creation**: Established [LLM Observability](/observability.md) — every LLM and hosted-embedding call is captured to file storage with its full prompt, response, tokens and cost, correlated by `interaction_id` so one chat question can be costed as a sum over one key.
* **Update**: [LLM pricing](/reference/llm-pricing.md) no longer describes a Postgres `llm_traces` table — records are JSON in file storage, `estimated_cost_usd` is a string or null, and the queries are `jq`. Adds the explicit statement that no Berget rate is published in this repo, so default-configuration records carry tokens and a null cost.
* **Update**: [shared](/packages/shared.md) — `StorageBackend` gains `add_json`/`iter_json` append-style JSON streams, with the deliberate local-`.jsonl` vs GCS-object-per-record divergence and the `flock` requirement documented.
* **Update**: [llm-core](/packages/llm-core.md) — `Usage` type, per-provider token/model mapping, `LLM_STREAM_USAGE`, and `_tracing.py`: the package carries the trace hook but never a writer.
* **Update**: [ai](/packages/ai.md) — `_observability.py` and `_pricing.py`, `install_file_tracing()`, `PromptTemplate.name`, and why Berget embeddings are traced while local ones are not.
* **Update**: [architecture](/architecture.md) — the trace stream sits alongside PDFs in object storage, deliberately not in Postgres.
* **Update**: [live testing](/playbooks/live-testing.md) gains a "Verifying LLM Traces" section, including how to cost a single question; [local dev](/playbooks/local-dev.md) lists the five new env vars.

## 2026-07-26

* **Update**: [parse worker](/pipeline/parse.md) now repairs words split by a line-break hyphen — pypdfium2 emits U+FFFE there, which Postgres tokenized as two fragments, hiding the containing chunk from a search for the term. Line breaks themselves are deliberately left alone.
* **Creation**: Documented the anatomy of a decision PDF and the anchors the pipeline segments it with in [decision document structure](/reference/document-structure.md) — header, holding, trailer, `Bilaga X` appendices, and the two identifier spaces (ärendenummer vs beslutsnummer).
* **Creation**: Recorded [appendices are labelled, not dropped](/decisions/appendix-segmentation.md) — appended lower-instance decisions stay searchable but carry a `section` marker, and modelling the prior instance as structured data is explicitly deferred.
* **Creation**: Recorded [body-first retrieval over one vector index](/decisions/body-first-retrieval.md) — one HNSW index with a `section` predicate rather than two, a hard filter rather than a ranking penalty, and the partial index deferred behind measurement.
* **Update**: [chunks](/data-model/chunks.md) gains `section` and `appendix_label`; [documents](/data-model/documents.md) gains `decision_number`; both new [indexes](/data-model/indexes.md) listed (migration `004`).
* **Update**: [extract worker](/pipeline/extract.md) — references now come from the body only and in two identifier spaces, and relevance follows the holding instead of the latter 60% of the document, a heuristic appendices inverted.
* **Update**: [metadata worker](/pipeline/metadata.md) — field extractors take `DocumentSegments`, `decision_number` is extracted, and the LLM fallback is handed the body rather than `raw_text`.
* **Update**: [chunk worker](/pipeline/chunk.md) — body and each appendix are chunked separately and labelled, the trailer is not chunked, and the summary is derived from the body only.
* **Update**: [retrieval agent](/retrieval/chat-agent.md) gains section scoping with a widen-on-empty fallback; the [chat endpoint](/api/chat-endpoint.md) `sources` payload gains `section` and `appendix_label`.
* **Update**: [shared package](/packages/shared.md) documents the new `segmentation.py` module and the `ChunkSection` vocabulary; [parse worker](/pipeline/parse.md) notes why `raw_text` deliberately keeps appendices.

## 2026-07-24

* **Creation**: Migrated the documentation set to an OKF v0.1 knowledge bundle — one concept per file, YAML frontmatter with a `type`, `/`-absolute cross-links, and per-directory `index.md` files. The former `specs/` and `design/` folders were replaced by topical sections (`pipeline/`, `retrieval/`, `data-model/`, `packages/`, `api/`, `frontend/`, `decisions/`, `playbooks/`, `reference/`).
* **Creation**: Split the monolithic backend and architecture specs into per-worker [pipeline](/pipeline/overview.md) Service concepts, per-package [Package](/packages/overview.md) concepts, per-table [Table](/data-model/documents.md) concepts, and a [Repository](/data-model/repositories.md) concept for the function-based data layer.
* **Deprecation**: Removed the superseded `min-instances 0 vs 1` self-hosting narration from the [embedding hosting](/decisions/embedding-hosting.md) decision. The tension — a direct NFR1 (<5s query) vs NFR2 (<$30/mo idle) tradeoff for a cold in-process `e5-large` load — is moot under the Berget-hosted default, since neither the API server nor `worker-embed` loads the model. It is preserved here in case the project ever reverts to self-hosting.
* **Deprecation**: Fixed stale LLM config in the [live testing](/playbooks/live-testing.md) playbook. Its env block previously set `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.0-flash` (a model shut down 2026-06-01), and `EMBEDDING_PROVIDER=local`, contradicting the Berget default in [local dev](/playbooks/local-dev.md); it now matches the Berget provider and per-task model scheme.
* **Update**: Consolidated the mandatory crawl tag-filter rationale into a single [decision](/decisions/tag-filter.md) (previously duplicated across the crawl source and backend specs), and the `ai` package into a single [concept](/packages/ai.md) (previously documented twice in the backend spec).
