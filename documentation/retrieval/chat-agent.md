---
type: Concept
title: Conversational Agent
description: The agent behind the chat endpoint — a GLM tool loop over the deterministic retrieval tool set, two terminal tools for the two kinds of message a conversation holds, two Mistral sub-agents for reading and counting, and one streamed writing call.
tags: [retrieval, agent, tool-loop, sse, synthesis]
timestamp: 2026-08-15T00:00:00Z
---

# Conversational Agent

The agent behind [`POST /api/chat`](/api/chat-endpoint.md), implemented in
`packages/agents/src/agents/chat/`. It answers a Swedish question by driving the
[deterministic retrieval tool set](/retrieval/deterministic-search.md) and two
sub-agents, then writing an answer from the evidence it selected.

It does not reimplement retrieval. Every tool is a wrapper over a service that
already exists and is tested on its own, which is why the agent can be exercised
against a fake toolset with no database at all.

## Shape

```
run_chat_agent(request, toolset)
  ├─ tool_loop(..., terminal_tools={"answer", "reply_from_context"})
  │                                                 GLM-5.2, blocking
  │    list_vocabulary()          → tool_call / tool_result
  │    search_decisions(...)      → tool_call / tool_result
  │    query_corpus(...)          → tool_call / sql / tool_result   [Mistral-M]
  │    read_decision(...)         → tool_call / tool_result         [Mistral-M]
  │    answer(chunk_ids, document_ids, notes)       ─┐ terminal,
  │    reply_from_context(notes)                    ─┘ loop returns
  │
  ├─ ai.synthesize_answer(evidence bundle)          GLM-5.2, streaming
  │    → token* → sources → done
  └─ ai.reply_from_context(conversation)            GLM-5.2, streaming
       → token* → sources(empty) → done
```

**Two phases, and the split is the point.** `LLMProvider.generate_stream` takes
no tools, so there is no streaming tool-call path to use — the loop gathers
evidence without streaming, and one final call writes the prose. Carrying the
evidence in a single synthesis prompt rather than in the loop is what keeps it
affordable: a passage placed in the loop is re-sent on every later iteration,
while one placed in the synthesis prompt is sent once.

The synthesis prompt is **fresh and compact** — the selected passages, the
reader's extracts, the SQL rows and the agent's notes — not the loop's own
history, which carries dead ends and verbose tool results.

## Models

| Job | Role | Model | Why |
|---|---|---|---|
| Orchestration + the answer | `chat` | GLM-5.2 | Plans, selects evidence, writes the user-facing Swedish |
| Reading one decision | `read` | Mistral-Medium-3.5-128B | Sees a whole document, so it wants context length |
| Counting | `sql` | Mistral-Medium-3.5-128B | The [SQL agent's](/api/sql-agent.md) own role, unchanged |

See [LLM configuration](/reference/llm-config.md).

## Tools

Ten callable services collapse to five, plus two terminal tools that call
nothing. `list_concepts`/`list_keywords` and their
document traversals are *filter values* —
`search_decisions(document_filter={"keywords": […]})` does the traversal.
Metadata browsing goes through `query_corpus`. `get_document_pdf` is useless to
a model.

| Tool | Wraps |
|---|---|
| `list_vocabulary(contains?)` | `search_service.get_filters` plus keyword/concept name search for the tail past the facet cap |
| `search_decisions(query, queries?, document_filter?, include_appendices?, limit?)` | `search_service.search_documents` |
| `read_decision(document_id, question, include_appendices?)` | `document_service.get_document_chunks` → the reading sub-agent |
| `inspect_decision(document_id)` | `document_service.get_document_detail` |
| `query_corpus(question)` | `agents.run_sql_agent` |
| `answer(chunk_ids, document_ids, notes)` | — terminal |
| `reply_from_context(notes)` | — terminal |

Search results carry `vector_similarity` and the search diagnostics, not just
the fused `score`. That is deliberate: RRF derives `score` from rank alone, so
the top hit scores the same whatever was asked, and only the similarity lets the
agent tell a close match from the nearest paragraph to a question the corpus
does not address. See [the similarity
floor](/retrieval/deterministic-search.md#the-similarity-floor).

### Handles, not UUIDs

Passages and decisions are addressed as `c1`, `d2`. A mid-tier model transcribes
a short handle reliably and a UUID unreliably, and an unknown handle is
*detectable*: it comes back as a refusal listing the valid ones, rather than
silently selecting nothing.

## Two ways a turn can end

A conversation holds two kinds of message, and collapsing them was a real
defect rather than a missing nicety. Before `reply_from_context` existed, every
turn entered the tool loop with "Search first" as its first instruction, so
"tack" either spent an embedding pass and ~18 seconds searching for nothing, or
called `answer` with no chunks and fell through the evidence gate to the canned
*"Jag hittade inget i besluten som besvarar frågan"* — a report on a search
nobody wanted. [PRD S8](/prd.md), conversational follow-ups, was not actually
met.

| Terminal tool | For | Written by |
|---|---|---|
| `answer(chunk_ids, document_ids, notes)` | A question the corpus answers | `ANSWER_SYNTHESIS`, from the selected evidence |
| `reply_from_context(notes)` | A greeting, a thank-you, a question about the previous answer | `CHAT_DIRECT_REPLY`, from the conversation alone |

Both stream, so the API forwards one shape either way. Both end with `sources`
— empty for a direct reply, and truthfully so.

**The direct-reply prompt's whole risk is the opposite of the synthesis
prompt's.** With no underlag in front of it, a model asked to be helpful will
invent the law, so `CHAT_DIRECT_REPLY` may build only on the conversation
history and the user's message: no case number, no date, no rule that is not
already in what has been said. Asked something the history does not cover, it
says the question needs looking up rather than guessing. The tool description
carries the same rule for the orchestrator — a legal question it has not
researched is a search, however small it sounds.

The check is ordered before the evidence gate, so the three empty-handed
endings stay distinct:

| State | What the user gets |
|---|---|
| `direct_reply` set | A conversational reply, streamed |
| No evidence, no direct reply | "Jag hittade inget i besluten…" — no model call |
| Loop exhausted | A terminal `ErrorEvent`, no `done` |

### The terminal `answer` tool is the reranking

`llm_core.tool_loop` normally returns when the model stops calling tools, which
makes termination incidental and the final assistant message throwaway prose.
Naming `answer` a [terminal tool](/packages/llm-core.md) makes the ending
deliberate and the handoff machine-readable — and the selection *is* the
reranking: the agent names which passages carry the answer as a tool call, not
as a separate LLM round-trip. The rerank step the previous chat pipeline had was
not carried over.

## Grounding: why a filter can be refused

`documents.category` and `documents.decision_outcome` hold free text —
`decision_outcome` is the verbatim closing sentence. A guessed value matches
nothing, and [deterministic search stops on an empty
filter](/retrieval/deterministic-search.md) rather than widening, so a guess
becomes a confident empty answer.

`search_decisions` therefore **refuses** a `document_filter` touching
`category`, `decision_outcome` or `entity_names` until `list_vocabulary` has
been called in the same run. This is the same precondition
[`run_sql`](/decisions/sql-agent.md) enforces, for the same reason: the prompt
asks for it too, but a prompt is a request and this is a guarantee.

The refusal is returned to the model **as a tool result, not an exception**, so
the next iteration repairs itself through the loop's ordinary path. A client
sees it as one `tool_result` with `status: "refused"`.

`keywords` is deliberately not on that list. It is the nämnd's own declared
`Sökord` classification, published verbatim by the facets, so filtering on one
uses a value the caller was handed rather than a guess.

## Reading a decision is a sub-agent

Measured against the corpus (184 documents), `documents.raw_text` averages
10,107 characters, median 7,183, p90 20,791 and **maximum 165,316**; 20
documents exceed 20,000.

Putting whole decisions in the orchestrator's context would make cost scale with
`documents × loop iterations × session turns`. Instead `read_decision` hands the
document, the user's question and the orchestrator's instructions to the `read`
role and returns only a focused extract. The orchestrator's context never holds
a decision, which is what makes the size of the worst document uninteresting and
why no character budget is needed.

**It reads chunks, never `raw_text`.** `raw_text` is the flattened PDF, with the
nämnd's ruling and the appealed decision concatenated and no marker between
them. Appendices average 5,888 characters and 168 of 184 documents have one, so
this is the common case, not an edge. The reader is given body text by default,
appendices only on request, and each appendix boundary marked in the text it
sees. Everything downstream — `chunks.section`, `appendix_label`, the [sources
event](/api/chat-endpoint.md#event-sources) — depends on that distinction
surviving.

## What the answer may assert

The synthesis prompt is given four sections, any of which may be empty:
passages, readings, tabular data, and the agent's notes. Two rules matter:

- **Counts come only from tabular data.** The passages are a relevance-ranked
  sample of the corpus, so a total derived from them is wrong in a way that
  reads as authoritative. With no tabular evidence, the answer gives no number.
- **An appendix passage is attributed.** The prompt is told whose words each
  excerpt holds, and never to present an appendix as the nämnd's position.

Empty sections render as `(inget)` rather than as blank, so an absent count
reads as "not established" rather than "not mentioned".

## Settings

`ChatAgentSettings` (`agents/config.py`) — loop bounds live next to the agent
they govern, not in [`llm_config.yaml`](/reference/llm-config.md), the same way
`SqlAgentSettings` does:

| Setting | Default | Meaning |
|---|---|---|
| `chat_agent_max_iterations` | 8 | Tool-loop budget |
| `chat_agent_max_documents_read` | 5 | Decisions readable in full per run; exceeding it is a refusal, not an error |
| `chat_agent_max_chunks_cited` | 12 | Passages the answer may be built from |
| `chat_agent_search_limit` | 8 | Decisions one search returns |
| `chat_agent_chunks_per_decision` | 2 | Passages per decision one search returns |

The last two are the cost levers. Measured against the real corpus, the
deterministic default of three passages per decision put ~33,000 characters of
verbatim text into a single tool result — which the loop then re-sends on every
later iteration; two brings it to ~26,000. Two is enough to judge a decision's
relevance, and the whole text is a `read_decision` away.

Together with `chat_agent_max_iterations` they are also the latency levers. A turn is
budgeted at **under a minute** ([NFR1b](/prd.md)); a turn that misses that is a loop
going round more times than the question needs, not a slow model, so the iteration cap
and the amount of text each search puts in front of it are what to reach for.

Search itself runs under [`SearchSettings`](/packages/api.md), the same bounds
`POST /api/search` uses, so the two paths cannot drift apart.

## Observability

Traced with `source="agents.chat"` — one record per loop iteration, since each
is its own billed call — plus `agents.chat.read` for the reader,
[`agents.sql`](/api/sql-agent.md#observability) for counting, and
`ai.synthesize_answer` for the streamed answer, or
`ai.reply_from_context` when the turn ended on the conversation instead. All of them share one
`interaction_id`, which is what makes "what did this question cost" a sum over
one key: `run_chat_agent` opens an `interaction_scope` that **inherits** the id
the API already put in the trace context rather than minting its own, so
`query_corpus` — itself another `interaction_scope` — joins the same turn
instead of starting a separate one. Every sub-agent invocation also opens its own
`agent_run_scope`, which always mints — the counting agent, and each individual
reading. A turn can make several `query_corpus` calls and read up to
`chat_agent_max_documents_read` decisions, and those are identical in every other
correlation key they carry, so this is the only thing that tells them apart. See
[LLM Observability](/observability.md).

## Exercising it without the API

`uv run python scripts/run_agent.py chat questions.txt` runs the agent over a
whole file of questions without starting the API — see [the LLM task
runner](/playbooks/live-testing.md#option-d-llm-task-runner-scriptsrun_agentpy).
The record keeps the tool trail as well as the answer, because most of what goes
wrong in an agent run is visible in which tools it reached for.
