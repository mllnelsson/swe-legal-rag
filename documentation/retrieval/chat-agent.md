---
type: Concept
title: Conversational Agent
description: The agent behind the chat endpoint — a GLM tool loop over the deterministic retrieval tool set with one terminal tool, `answer`, and a plain no-tool reply as the other way a turn ends; two Mistral sub-agents for reading and counting; and a streamed writing call that marks each claim with the passage handle it rests on.
tags: [retrieval, agent, tool-loop, sse, synthesis]
timestamp: 2026-08-22T00:00:00Z
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
  ├─ tool_loop(..., terminal_tools={"answer"})       GLM-5.2, blocking
  │    list_vocabulary()          → tool_call / tool_result
  │    search_decisions(...)      → tool_call / tool_result
  │    query_corpus(...)          → tool_call / sql / tool_result   [Mistral-M]
  │    read_decision(...)         → tool_call / tool_result         [Mistral-M]
  │    answer(annotations, gaps)  ─┐ terminal, loop ends
  │    (model writes prose, calls no tool) ─┘ loop ends, that message is the reply
  │
  ├─ ai.synthesize_answer(evidence bundle)          GLM-5.2, streaming
  │    → sources → token* → done
  └─ (no evidence gathered: the orchestrator's own message is the reply)
       → sources(empty) → token(whole) → done
```

**Two phases, and the split is the point.** The loop gathers evidence without
streaming, and one final call writes the prose. Not because
`LLMProvider.generate_stream` cannot take tools — that is a limit of this
project's own OpenAI-compatible wrapper, not the underlying API, which streams
tool calls fine — but because a synthesis prompt built fresh from the selected
evidence beats writing from the loop's own history, which carries every search
result verbatim and every dead end. Carrying the evidence in a single synthesis
prompt rather than in the loop is also what keeps it affordable: a passage
placed in the loop is re-sent on every later iteration, while one placed in the
synthesis prompt is sent once.

The synthesis prompt is **fresh and compact** — the selected passages, each
marked with its handle, plus the reader's extracts, the SQL rows and the
agent's annotations and gaps — not the loop's own history. It is also where the
answer becomes Swedish: the orchestrator reasons in English over Swedish
passages and tool results, and the synthesis step writes the Swedish prose the
user reads. The one exception is a turn that needed no evidence — there the
orchestrator writes the (Swedish) reply itself, since there is no second call
to hand it to.

## Models

| Job | Role | Model | Why |
|---|---|---|---|
| Orchestration + the answer | `chat` | GLM-5.2 | Plans, selects evidence, writes the user-facing Swedish |
| Reading one decision | `read` | Mistral-Medium-3.5-128B | Sees a whole document, so it wants context length |
| Counting | `sql` | Mistral-Medium-3.5-128B | The [SQL agent's](/api/sql-agent.md) own role, unchanged |

See [LLM configuration](/reference/llm-config.md).

## Tools

Ten callable services collapse to five, plus one terminal tool that calls
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
| `answer(annotations, gaps)` | — terminal |

`list_vocabulary` lists categories, outcomes and keywords unconditionally, but
legal concepts only for a `contains` lookup — `DocumentFacets` carries no
`concepts` field, so a bare call carries a `concepts_note` explaining that
rather than an empty list, which would read as "the corpus has none".

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

A passage handle does double duty: it is also the marker the synthesis prompt
writes into the answer (`[c3]`) and the field a client resolves that marker
against in `event: sources`. See [what the answer may
assert](#what-the-answer-may-assert).

## Two ways a turn can end

A conversation holds two kinds of message, and collapsing them is a real defect
rather than a missing nicety: a greeting driven into the tool loop spends an
embedding pass and ~18 seconds searching for nothing, and answers "tack" with a
report on a search nobody wanted. [PRD S8](/prd.md), conversational follow-ups,
is what the second ending exists to meet.

It needs no machinery of its own. [`tool_loop`](/packages/llm-core.md) returns
when the model calls no tool, so a turn needing no evidence ends the way a tool
loop ordinarily ends: the model writes the reply itself and calls nothing, and
that message is what the caller gets. **A caller must therefore read
`message.tool_calls` to tell the two endings apart** — empty means the model
chose to answer in prose, and discarding that message sends the user the
no-evidence line instead of the answer it just wrote.

| Ending | For | Written by |
|---|---|---|
| `answer(annotations, gaps)` | A question the corpus answers | `ANSWER_SYNTHESIS`, from the selected evidence, streamed |
| No tool call | A greeting, a thank-you, a question about the previous answer | `CHAT_ORCHESTRATION` itself, in the same call that decided not to search, delivered whole |

Both endings carry `sources`, empty for the second and truthfully so — that
answer rests on the conversation, not on any decision. Only the first streams
token by token; the second is one message, which for a couple of sentences
costs nothing and saves a second model round-trip.

**The honesty rules for a no-tool reply now live in the orchestration
prompt**, since that model is the one writing it. With no evidence in front of
it, a model asked to be helpful will invent the law, so `CHAT_ORCHESTRATION`
says the reply may build only on the conversation history and the user's
message: no case number, no date, no rule that is not already in what has been
said. Asked something the history does not cover, it says the question needs
looking up rather than guessing. The same section says never to use this as a
shortcut past research — a legal question it has not looked up is a search,
however small it sounds.

The check is ordered before the evidence gate, so the three empty-handed
endings stay distinct:

| State | What the user gets |
|---|---|
| No tool call | The reply the model wrote, delivered whole |
| `answer` called with no passages | "Jag hittade inget i besluten…" — no model call |
| Loop exhausted | A terminal `ErrorEvent`, no `done` |

### The terminal `answer` tool is the reranking

`llm_core.tool_loop` normally returns when the model stops calling tools, which
makes termination incidental and the final assistant message throwaway prose.
Naming `answer` a [terminal tool](/packages/llm-core.md) makes the ending
deliberate and the handoff machine-readable — and the selection *is* the
reranking: the agent names which passages carry the answer as a tool call, not
as a separate LLM round-trip. The rerank step the previous chat pipeline had was
not carried over.

Each named passage is structured, not a bare handle: `carries` says what it
establishes and an optional `caution` says what the writer must watch for
("bilaga, underinstansens ord"). A handle cannot be cited without saying what
it carries, which is what keeps the writing step's guidance structured all the
way through rather than degrading into freeform prose the model could smuggle
a finding through.

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

The synthesis prompt is given five sections, any of which may be empty:
passages (each marked with its handle and case), readings, tabular data, the
agent's annotations, and its gaps. Rules that matter:

- **Counts come only from tabular data.** The passages are a relevance-ranked
  sample of the corpus, so a total derived from them is wrong in a way that
  reads as authoritative. With no tabular evidence, the answer gives no number.
- **An appendix passage is attributed.** The prompt is told whose words each
  excerpt holds, and never to present an appendix as the nämnd's position.
- **An annotation is guidance, never a source.** `carries` says what a passage
  establishes and `caution` what to watch for, but the writer verifies every
  claim against the passage text itself. Freeform notes had no enforceable line
  between guidance ("c3 carries the deadline rule") and a claim ("the deadline
  is three weeks"); structured fields have nowhere to put the second.
- **Every claim is marked with the handle it rests on.** The prompt asks for
  `[c3]` directly after the sentence it supports — `[c3][c7]` when several
  passages support one sentence, no marker at all for a claim resting only on
  tabular data.
- **`gaps` says what the evidence does not reach**, in place of the answer
  papering over it.
- **Plain text only.** No headings, markdown or bullet lists — the client
  renders the answer as text, so any markup the model wrote would reach the
  reader as literal characters on screen.

Empty sections render as `(inget)` rather than as blank, so an absent count
reads as "not established" rather than "not mentioned".

`event: sources` carries one entry per cited **passage**, not per decision —
collapsing two passages of the same decision would leave one handle
unresolvable — and it is emitted **before** the token stream, since the
selection is fixed the moment `answer()` runs and a marker should be
resolvable the instant it arrives. See [the sources
event](/api/chat-endpoint.md#event-sources).

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

Together with `chat_agent_max_iterations` and `chat_agent_max_documents_read` they are
also the latency levers. A turn is budgeted at **under a minute**
([NFR1b](/prd.md)), and a turn that misses it is usually one that went round more
times, or read more decisions, than the question needed — not a slow model.
`read_decision` is the one to watch: each call is a whole document through the
`read` role, so a run that spends its budget of five adds several sub-agent
round-trips to a loop that was already several iterations long. Measured on a broad
question ("Vad har nämnden sagt om jäv?"), four iterations plus four readings ran to
roughly four minutes, while the same question answered from passages alone came in
under two. The prompt tells the orchestrator to read only when the passages leave the
question open; the cap is what holds when it reads anyway.

Search itself runs under [`SearchSettings`](/packages/api.md), the same bounds
`POST /api/search` uses, so the two paths cannot drift apart.

## Observability

Traced with `source="agents.chat"` — one record per loop iteration, since each
is its own billed call — plus `agents.chat.read` for the reader,
[`agents.sql`](/api/sql-agent.md#observability) for counting, and
`ai.synthesize_answer` for the streamed answer. A turn that ends with no tool
call writes no separate record for the reply: it is part of the same
`agents.chat` iteration that decided not to search, so a greeting is one record
total rather than two. All of them share one
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
