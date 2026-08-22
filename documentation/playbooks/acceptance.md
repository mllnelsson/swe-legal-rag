---
type: Playbook
title: Acceptance Walkthrough
description: Turns the PRD's requirements into checks a human performs against the real system — a live agent turn on a real BERGET_API_KEY, against the real ingested corpus — as distinct from the scripted, model-free walkthrough in live testing.
tags: [acceptance, verification, prd, playbook]
timestamp: 2026-08-22T00:00:00Z
---

# Acceptance Walkthrough

**No human has run this walkthrough yet.** [The PRD's acceptance
criteria](/prd.md#acceptance-criteria) record that gap plainly rather than
leaving it unstated; this page is what closes it, once someone runs it.

## This is the real system, not the scripted one

[Live testing](/playbooks/live-testing.md) has a surface-by-surface UI
walkthrough, but its "walking the whole frontend on one server" section runs
under `CHAT_SCRIPT` — canned SSE events, no model call, fabricated sources and
case numbers, `pdf_url`s that 404 on purpose. It is the right tool for
checking layout and wiring. It settles none of the requirements below,
because none of them are true of a fixture.

This playbook is the other one: a real agent turn, on a real `BERGET_API_KEY`
(`CHAT_SCRIPT=off`, the default), against the real ingested corpus — **184
documents, 1610 chunks, 446 entities**, per [deployment
state](/reference/deployment-state.md). Nothing here is deployed, so "the real
system" means the local API and frontend from [live
testing](/playbooks/live-testing.md#running-the-api-server), pointed at the
local database that already holds that corpus.

## NFR1a — deterministic search responds in under 5 seconds

Time one call to `POST /api/search` from the frontend or with `curl -w
'%{time_total}\n'`.

**Embeddings are `local`** (`embedding.provider: local` in `llm_config.yaml`
— see [the ai package](/packages/ai.md)), so the *first* search after the API
starts pays the cost of loading `sentence-transformers` into the process; that
call can miss the 5s budget on model-load alone. A second call, once the
model is resident, is the one the budget is actually about — time that one,
not the first.

## NFR1b — an agent turn completes in under a minute, first token well before

Send one message to `/agent` (or `POST /api/chat` directly) and time it:
wall-clock to the first `event: token`, and wall-clock to `event: done`. [The
endpoint's own latency table](/api/chat-endpoint.md#latency) estimates first
token at ~18s and the whole turn well under the one-minute
[NFR1b](/prd.md) ceiling.

The turn's cost is not a guess: read the `X-Interaction-Id` response header
(the UI renders it on every finished turn as "Referens") and open the
directory it names:

```bash
ID=<X-Interaction-Id>
ls data/llm-traces/$(date -u +%F)/$ID/
```

One file per billed call — tool-loop iterations under `agents.chat`, the
reading and SQL sub-agents if the turn used them, `ai.synthesize_answer` for
the streamed answer. See [what did this question
cost](/observability.md#what-did-this-question-cost) for the full recipe.

## S4/S5 — implicit filters are extracted and applied

Ask a question that only implies a filter rather than naming one as a filter
— a category or a year mentioned in prose, not typed into a filter control.
Watch for `event: tool_call` / `event: tool_result` pairs carrying `label:
"search.filtered"` — see [the progress label
table](/api/chat-endpoint.md#the-api-emits-keys-the-client-owns-the-words).

**A `tool_result` carrying `status: "refused"` is a correct outcome, not a
failure.** It means the agent declined to filter on a guessed
`category`/`decision_outcome`/`entity_names` value until [`list_vocabulary`
grounded it](/retrieval/chat-agent.md#grounding-why-a-filter-can-be-refused) —
the label on that result matches the `search.filtered`/`search.broad` label its
call reported, and `status` alone says it was declined. The same turn should
then repair itself and either search grounded or fall back to broad search,
visible as a later `tool_result`.

## S6/S7 — a cited answer, and a reachable PDF

Check the finished answer for an inline `[c…]` citation marker and a specific
case number (`Ärendenummer`) it cites, then check `event: sources` for the
entry whose `handle` matches the marker and confirm its `pdf_url` resolves:

```bash
curl -sI "http://localhost:8000$PDF_URL" | grep -i content-type
# expect: content-type: application/pdf
```

See [the sources event](/api/chat-endpoint.md#event-sources) and [the PDF
endpoint](/api/document-pdf.md).

## S8 — a conversational follow-up needing no retrieval

Send a greeting ("hej") or, after a real answer, "förklara det enklare".
Expect the turn to end with **no `tool_call`/`tool_result` frames at all** —
the model calls no tool and writes the reply itself (see [the two ways a turn
can end](/retrieval/chat-agent.md#two-ways-a-turn-can-end)) — rather than any
`search.*` step, with `sources: []` — a real empty list, not a search that
found nothing.

## S1/S2 — an idempotent, checkpointed pipeline; extracted metadata

Re-run a pipeline step against an already-`completed` task
(`scripts/run_step.py <step> <doc_id>`, or a full `run_pipeline.py` pass over
an already-ingested corpus) and confirm no duplicate row appears:

```sql
SELECT document_id, step, count(*) FROM tasks GROUP BY 1, 2 HAVING count(*) > 1;
-- expect 0 rows: uq_tasks_document_id_step holds one row per (document, step)
```

See [`tasks`](/data-model/tasks.md) and [worker
patterns](/pipeline/worker-patterns.md). For S2, spot-check a few documents'
extracted `case_number`, `decision_date`, `decision_outcome` and `category`
against the source PDF.

## Carried over: the LLM client's retry behaviour, still unproven live

**The retry fix has never been exercised against the real `api.berget.ai`
host.** It is proved today only by unit tests and a loopback test server —
0 retries with the fix in place, 3 without it, over 4 messages. This item is
carried over from a root-level runbook that has since been deleted; this
playbook is its only remaining home, so it stays here rather than being lost.

The first real metadata pass against the corpus is the test: run it and watch
the output for

```
openai._base_client: Retrying request
```

None should appear. Any occurrence means the fix is not doing what the unit
tests say it does against the real host, and is worth a closer look before
trusting the rest of this walkthrough's timings.

## See also

* [Live Testing Guide](/playbooks/live-testing.md) — the scripted, model-free
  counterpart: UI layout and wiring, no `BERGET_API_KEY` needed, fabricated
  answers and sources.
* [Deployment and Data State](/reference/deployment-state.md) — what the
  corpus actually holds right now, and what "nothing is deployed" does and
  does not imply for this walkthrough.
* [Product Requirements](/prd.md) — the requirements this playbook checks.
