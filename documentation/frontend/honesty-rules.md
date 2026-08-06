---
type: Concept
title: Search result honesty rules
description: The frontend's tested constraints on what it claims about a search result — each one exists because the data does not support the more convenient alternative.
tags: [frontend, ui, honesty, search, appendix, rrf]
timestamp: 2026-08-06T00:00:00Z
---

# Search result honesty rules

Eleven constraints the frontend enforces on how it presents search results and
decisions, each backed by a test in
`src/components/research/honesty-rules.test.tsx`. They are not generic UI
polish — each exists because the corpus or the [search
API](/api/search.md)'s response shape does not support the more convenient
alternative, and getting one wrong would put a claim on screen the data
cannot back up.

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
   the match was. `vector_rank` and `text_rank` badges are shown instead, and
   an arm that did not return a chunk (`null`) is simply omitted rather than
   shown as a zero. The field that does carry relevance is
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

`decision_outcome` facet values are also worth recording here: they are
verbatim holdings running 41–378 characters long, so the filter control
shortens the *label* it displays while still sending the underlying value
byte-identical to what `/api/filters` published.
