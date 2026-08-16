---
type: Concept
title: Honesty rules
description: The frontend's tested constraints on what it claims — twelve about a search result, nine more about an answer a language model wrote. Each exists because the data does not support the more convenient alternative.
tags: [frontend, ui, honesty, search, agent, appendix, rrf]
timestamp: 2026-08-16T00:00:00Z
---

# Honesty rules

Twenty-one constraints the frontend enforces on what it puts on screen, each backed
by a test. They are not generic UI polish — each exists because the corpus or an
API's response shape does not support the more convenient alternative, and
getting one wrong would put a claim on screen the data cannot back up.

Two groups, in two test files:

| Rules | Surface | Test |
|---|---|---|
| 1–12 | [Search](/api/search.md) results and decisions | `src/components/research/honesty-rules.test.tsx` |
| 13–21 | [Agent mode](/frontend/overview.md) | `src/features/agent/agent-honesty-rules.test.tsx` |

The second group is the harder one. In search, every word on screen is either
the nämnd's own text or a label this app wrote; in agent mode the prose is
written by a language model, and these are the rules that keep a reader able to
tell what it rests on.

## Search results (1–12)

1. **Appendix text is not the nämnd's own words.** A chunk with
   `section: "appendix"` is the appealed lower-instance decision — often the
   very decision Överklagandenämnden overturned — and appendix chunks are 99
   of 206 chunks in the ingested corpus, not a rare edge case. Every appendix
   excerpt carries a marker naming it, and on the [decision
   page](/frontend/overview.md) that marker is sticky so it cannot be
   scrolled past unnoticed. See [appendices are labelled, not
   dropped](/decisions/appendix-segmentation.md).
2. **A widened search says so.** When
   `diagnostics.widened_to_appendices` is true — the body-only search found
   nothing and [retried against the whole document](/decisions/body-first-retrieval.md) —
   the results page shows a banner explaining that the matches came from
   appealed decisions, not the nämnd's own reasoning.
3. **Two distinct empty states, not one.** `candidate_document_count === 0`
   (the filters excluded every document) is shown differently from a query
   that matched nothing (`candidate_document_count: null`, no filter
   applied). The API distinguishes these deliberately in
   `diagnostics`, and collapsing them into one "no results" message would
   throw that distinction away. Both are reachable: the [similarity
   floor](/retrieval/deterministic-search.md#the-similarity-floor) means a
   query the corpus has nothing close to returns nothing, rather than its
   nearest neighbours.
4. **`score` is never rendered.** It is a rank-derived Reciprocal Rank Fusion
   value, observed in the range 0.016–0.033 on the live corpus — not a
   confidence percentage a reader could sensibly interpret. Because RRF works
   on rank, the top hit of *any* search scores 0.01639 regardless of how good
   the match was. What a card shows instead is **how the decision was found**,
   in words: "Innehåller dina ord" when the full-text arm returned it, "Träff
   på betydelse" when only the vector arm did. The rank *numbers* are not shown
   either — the list is already in rank order, so a "#3" beside the third card
   restates the position and reads as a score to a reader who does not know
   what a retrieval arm is. The field that does carry relevance is
   `vector_similarity` — see [`/api/search`](/api/search.md).
5. **`total` reads as a bare count, never a fraction of a corpus.** It is the
   size of the fused candidate pool (bounded by the search arm limit), not a
   corpus-wide match count — see [`/api/search`](/api/search.md) — so the
   frontend renders "15 träffar", never "1–10 av N".
6. **Declared and inferred entities are styled and labelled apart.**
   `keyword` entities are declared by the nämnd on its own `Sökord:` line;
   `regulation`/`legal_concept`/`role`/`parish` entities are inferred by
   extraction from the decision's prose. `Badge` tone is `declared` for the
   former and `inferred` for the latter — see [document
   detail](/api/document-detail.md) for the keyword/concept split.
7. **`unresolved_references` render as plain text, never as links.** A
   citation to a case the corpus does not hold has nothing to link to, and in
   the current corpus these outnumber resolved citation edges — treating them
   as dead links would be more common than treating them correctly.
8. **`case_number` and `decision_number` are always labelled and never
   conflated.** The corpus contains cases opened in one year and decided in
   another — e.g. case `2025-0035` decided as `14/2026` — so a decision card
   always shows "Ärendenummer" and "Beslut" as two separate, labelled values.
9. **`limit` is read from the response, never assumed from the request.**
   [`/api/search`](/api/search.md) silently clamps an out-of-range `limit`,
   so pagination reads the echoed value back rather than trusting what the
   client sent.
10. **`category` and `decision_outcome` are opaque free text, rendered
    exactly as returned.** They are lifted off the source PDFs by regex, not
    a controlled vocabulary — see [`/api/filters`](/api/filters.md) — and the
    corpus contains near-duplicate values (e.g. "Utlämnande av handling" and
    "Utlämnande av handlingar") that the frontend does not merge or
    normalize.
11. **A note about "träffarna nedan" is not shown when there are none.** Both
    summary notes — the appendix-widening banner and the matched-by-meaning
    note — make a claim about the result list, so each is gated on `total > 0`.
    Since the [similarity
    floor](/retrieval/deterministic-search.md#the-similarity-floor) landed, a
    widened search can come back empty too, which is what makes the gate
    necessary rather than theoretical.
12. **Phrasings the user did not type are attributed to the model.** With
    [query expansion](/retrieval/query-expansion.md) on, the summary's
    prominent line is `effective_queries` — the original question followed by
    variants a language model wrote. Unattributed, that presents generated
    text as the reader's own question. Three outcomes are distinguished, not
    two: variants were searched, the model proposed none, or expansion could
    not be fetched at all. The third matters because expansion fails open —
    the results are real, but the search that ran is not the search that was
    asked for, and without the note it is indistinguishable from a plain
    search.

`decision_outcome` facet values are also worth recording here: they are
verbatim holdings running 41–378 characters long, so the filter control
shortens the *label* it displays while still sending the underlying value
byte-identical to what `/api/filters` published.

## Agent mode (13–21)

These govern an answer a language model wrote, streamed over the [chat
endpoint](/api/chat-endpoint.md). The reader cannot check that prose against the
corpus themselves, so everything that would let them try has to survive onto the
screen.

13. **An appendix source is not the nämnd's words.** The same rule as 1, applied
    to `event: sources`. `section: "appendix"` is the appealed lower-instance
    decision — often the one Överklagandenämnden overturned — and every such
    source carries the marker, using the same `SectionBadge` the search results
    do. The excerpt is 200 characters of a passage the model saw in full, so it
    is a label for the reader, not the evidence.
14. **A count is never shown without the query behind it.** Whenever a turn
    emitted `event: sql`, the generated query, its rows, its `assumptions` and
    its `truncated` flag render beside the answer, and **not behind a collapsed
    disclosure** — a query the reader has to open is a query the reader who took
    the number at face value will not open. This is [the SQL agent's stated
    obligation on its caller](/api/sql-agent.md#the-consumers-obligation), not
    decoration. The attempt trail may collapse; the query that produced the
    answer may not. A `query_corpus` that could not build a query says so rather
    than rendering nothing.

    The block leads with the **rows**, and the SQL follows under "Så räknades de
    fram". Both are on screen and neither is collapsed; the order is what
    changed, because the reader this rule protects is the non-technical one, and
    a block that opens on `SELECT` reads as machinery — which is what a reader
    skips. The rows are the part they can actually check the number against.
15. **`error` is terminal.** The contract sends no `done` after one, so the UI
    stops on it: the failed turn is marked, whatever tokens arrived are kept —
    they are what the agent actually said — and nothing goes on claiming the
    answer is still being written.
16. **A `refused` tool result is a step, not a failure.** It is a policy decline
    the agent repairs from on its next iteration — an ungrounded filter, a spent
    reading budget. It renders as an ordinary step ("Avvaktade med filtret tills
    värdena var kända"), never as an error, and is visually distinct from a
    `status: "error"` result.
17. **Streaming text is not a finished answer.** A turn still receiving tokens
    carries a writing marker, and sources are not rendered until the frame
    carrying them has arrived. A sentence on screen may be about to be qualified
    by the next one.
18. **An aborted turn says the agent will not remember it.** The API appends a
    turn to the [session](/data-model/sessions.md) only after `done`, so a
    question stopped mid-answer is absent from the history the *next* question
    is answered against. Showing it as an ordinary turn would imply a continuity
    that does not exist.
19. **An empty source list is stated, not implied.** Both a search that found
    nothing and a turn that needed no search at all send `sources: []`.
    Rendering nothing there would leave the reader to assume the prose was
    sourced; it says the answer rests on no cited decision.
20. **The two identifier spaces stay apart.** The chat contract carries a
    `case_number` and no `decision_number`, so a source labels its ärendenummer
    as one and invents no beslutsnummer — the same distinction rule 8 makes on a
    decision card, where `2025-0035` is decided as `14/2026`.

21. **A reopened conversation shows what was said, not what it rested on.** The
    API persists the question and the answer only — never the passages, the
    reader's extracts or the SQL rows a turn gathered, which is what stops turn
    two re-sending turn one's documents (see [the sessions
    endpoints](/api/sessions.md)). So a turn read back out of a past
    conversation renders its prose with a plain marker saying the citations were
    not kept, and renders **no source list at all**. The empty-source statement
    rule 19 requires would be a different claim — "this answer cited nothing"
    rather than "we did not keep what it cited" — and only the second is true
    here. The turn's `interaction_id` survives, so the answer is still traceable
    even though its evidence is not on screen.

One more thing the interface shows for a reason rather than for polish: each
finished turn prints its `X-Interaction-Id`. That id spans everything the turn
cost, so "this answer was wrong" becomes a lookup in the [trace
stream](/observability.md) rather than a guess from timestamps.
