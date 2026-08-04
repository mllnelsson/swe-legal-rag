---
type: Decision
title: Structural fields are parsed, not inferred
description: Why case number, decision number, decision date, category, and lagrum citations are extracted by rule alone with no LLM fallback, and where LLM fallback is used instead.
tags: [decisions, extraction, llm, rules, parsing]
timestamp: 2026-08-04T00:00:00Z
---

# Structural fields are parsed, not inferred

**Status:** Accepted

Measured against all 25 real documents in `data/store/documents.json`, every parser
failure in `shared.segmentation` and `worker-extract`'s rule-based pass turned out to be a
deterministic one-line defect in a regex — not a case the corpus is genuinely too
irregular to describe with rules. Two were severe: the appendix-label regex missed
`BILAGA A` (upper case, 22 of 25 decisions), which swallowed 43% of the corpus's
characters into an unindexed trailer; and the kyrkoordningen citation patterns required
the statute's name before the lagrum, when 213 of 215 real citations write it after,
leaving `EntityType.REGULATION` an entirely empty vocabulary. Fixing those and seven
smaller defects moved every measured metric to, or near, 100% — see the before/after
tables in [metadata worker](/pipeline/metadata.md) and [extract
worker](/pipeline/extract.md) — without adding a single model call. See [decision
document structure](/reference/document-structure.md) for the anchors themselves.

## Decision

**Case number, decision number, decision date, category, and lagrum/regulation citations
stay rule-based, with no LLM fallback.** These are *structural* fields: a fixed layout the
nämnd's own template guarantees, not prose a model has to interpret.

## Why not LLM fallback

A regex that gets a field right 100% of the time on the observed corpus must not be
delegated to a model whose failure mode is a *plausible wrong value* — strictly worse
than the regex's own failure mode, `None`. `None` is detectable: a document with a missing
`case_number` shows up as one to go fix. A hallucinated `2025-0017` on the wrong document
silently misfiles it and corrupts the [document references](/data-model/document-references.md)
graph that the whole citation-resolution machinery depends on — precisely the failure
canonicalisation and the self-citation guard exist to prevent (see [document
structure](/reference/document-structure.md)). Given a rule that is already right across
the corpus, LLM fallback only adds that risk; it buys nothing a regex fix does not already
provide, at real per-document cost.

The corollary: this is a decision about *this* pipeline's regexes on *this* corpus, not a
blanket rule against LLM fallback anywhere. It holds because the corpus turned out to be
more regular than the code had assumed, and it would not survive a corpus that genuinely
varied in its structural layout — see [testing](/testing.md) for why the fixture set has
to track the corpus's actual variants, not an idealised one, for this decision to keep
holding.

## Where LLM fallback is correct, and stays

Structural fields are not the whole of extraction. LLM fallback is deliberately kept for
fields that have no fixed enumeration or fixed shape to write a rule against:

* **Open-vocabulary entities in [worker-extract](/pipeline/extract.md)** —
  `_KNOWN_ROLES` and `_KNOWN_LEGAL_CONCEPTS` are closed `frozenset`s. They will always
  miss a role or a legal concept nobody has enumerated yet, a coverage gap a regex cannot
  close by construction, unlike a one-line defect in a fixed-format field.
* **Prose-shaped fields** — `decision_outcome` and `category` are read off a fixed
  position first, but a decision that phrases its outcome or heading unusually needs
  judgement a regex does not have.
* **Generative summaries** — [chunk worker](/pipeline/chunk.md)'s document summary is
  synthesis, not extraction; there is no rule to write in the first place.

This round of fixes also makes that fallback fire *less* — worth recording so it is not
read as the fallback becoming less useful. `_is_result_complete`'s entity-density check
(see [extract worker](/pipeline/extract.md)) sizes its threshold off `segments.body`
alone but counts entities found across body *and* appendices. Before the appendix-label
fix, `segments.appendices` came back empty for 22 of 25 corpus documents — their appendix
text had been swallowed into `trailer` instead, unscanned by any extraction strategy — so
the entity count dropped while the threshold, sized off `body` alone, did not move. The
check judged those results incomplete more often than the body-only extraction actually
warranted, and paid for an LLM call on the strength of a wrong count. Fixing the
segmentation fixes what the density check is measuring, not just the appendix content
itself.

# Citations

[1] `data/store/documents.json` — the 25-document corpus the before/after metrics in
[metadata worker](/pipeline/metadata.md) and [extract worker](/pipeline/extract.md) were
measured against.
