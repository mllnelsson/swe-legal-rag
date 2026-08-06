---
type: Concept
title: Frontend
description: The React SPA at frontend/ — a filtered, browsable, traversable interface over the deterministic retrieval API only. No chat, no SSE, no LLM call from the browser; chat is a deferred phase.
tags: [frontend, ui, search, react, spa]
timestamp: 2026-08-06T00:00:00Z
---

# Frontend

A React single-page app at `frontend/` in this repo. It calls only the
deterministic [retrieval API](/api/index.md) — search, filters, documents,
concepts, keywords. **It does not call [`POST /api/chat`](/api/chat-endpoint.md)
at all**: no SSE connection, no session, no LLM-synthesized answer anywhere in
the frontend. The forward-looking note that used to sit in this concept —
"a future UI would call search/documents/concepts directly rather than through
the chat agent" — is what this frontend is.

## Stack

Vite + React 19 + TypeScript, `react-router` for routing, TanStack Query for
server state, Vitest + Testing Library for tests. Styling is plain CSS against
the [design system](#design-system)'s custom properties — no Tailwind, no
shadcn/ui, no CSS framework. 15 direct dependencies total; the runtime set is
just `react`, `react-dom`, `react-router`, `@tanstack/react-query`.

## Routes

| Path | Page |
|---|---|
| `/` | Search home |
| `/sok` | Search results |
| `/beslut/:documentId` | Decision detail |
| `/sokord` | Keyword (Sökord) index |
| `/sokord/:entityId` | Decisions carrying one keyword |
| `/begrepp` | Concept index |
| `/begrepp/:entityId` | Decisions carrying one concept (`?typ=` scopes the entity type) |
| `/stil` | Dev-only component reference, not linked from app navigation |

All search filter state lives in the `/sok` query string, in
`src/features/search/search-params.ts`'s pure parse/serialize functions —
Swedish param names (`q`, `sokord`, `kategori`, `utfall`, `fran`, `tom`,
`refs`, `sida`) matching the interface's language — so every search is a
shareable, bookmarkable URL and nothing about the current search lives only in
React state.

## Generated API types

The TypeScript types the frontend builds against are generated, never hand
written — see [generated API types](/frontend/generated-types.md).

## Design system

The visual layer is ported from the project's `.claude/skills/design-tools/`
skill. Token CSS (`src/styles/tokens/`) is copied over verbatim, with one
change: `fonts.css`'s Google Fonts `@import` is replaced with self-hosted
`@font-face` rules. Fonts and the 24 Lucide icons used by the app are vendored
into `src/styles/fonts/` and `src/components/display/icon-paths.ts`
respectively, so **no third-party network request leaves the page at
runtime**.

The skill's linting layer (`_adherence.oxlintrc.json`) does not carry over as
shipped: oxlint does not implement the `no-restricted-syntax` rule type the
skill's rules are written as, and 30 of its 33 rules duplicate what TypeScript
already enforces on typed `.tsx` components (the skill's originals are
untyped `.jsx`). The three rules that check something a type system cannot —
no raw colour, no raw spacing value, no font outside the three the system
ships — are reimplemented in `frontend/scripts/check-tokens.mjs`, run by
`npm run lint`.

The skill's components carry US-litigation concepts with no counterpart in
this corpus, and those were dropped rather than mapped: `CitationCard`'s
`authority` (binding/persuasive/secondary) and `treatment` (Followed/
Criticized) fields do not exist here. `Badge` tones are renamed
`declared`/`inferred` instead — see [honesty rule
6](/frontend/honesty-rules.md).

## The honesty rules

The interface makes a set of deliberate, tested claims about what the corpus
data does and does not support — described in full at [search result honesty
rules](/frontend/honesty-rules.md). They are the domain-specific part of this
app; everything else is fairly generic search UI.

## A known retrieval limitation

Retrieval exposes no relevance signal to the client: the vector arm returns
its 50 nearest neighbours with no similarity floor, and RRF score is
rank-derived, so a nonsense query and a good one both produce a confident-
looking top hit (verified against the live API: a nonsense query still scores
its top hit around 0.01639, the same range as a real one). The practical
consequence is that the "no matches" empty state — [honesty rule
3](/frontend/honesty-rules.md) — is unreachable through a bad query alone;
only filters can empty a result set. The frontend mitigates this by noting
when no word in the query occurs anywhere in the corpus (via
`diagnostics.text_hit_counts`), but the actual fix is a backend change —
exposing per-chunk cosine distance, or flooring the vector arm — and is not
implemented here.

## Running it

```
uv run --package api uvicorn api.main:app --reload   # :8000
npm run dev                                            # :5173, in frontend/
```

`:5173` is already the API's default CORS origin, and Vite proxies `/api` to
`:8000`. Embeddings run locally (`embedding.provider: local`), so search
costs time rather than money, but the API still constructs the `structured`/
`chat` LLM roles at startup and needs either `BERGET_API_KEY` or
`LLM_PROVIDER=none` to start. `EMBEDDING_DIMENSION` must agree with
`llm_config.yaml`.

## Out of scope

Not in this version: saved matters or bookmarks, a marketing site, auth, a
mobile layout, and server-side query expansion (`expand: true` on
[`/api/search`](/api/search.md) is never sent — it is the one search parameter
that invokes an LLM role, so omitting it keeps the app runnable with no model
credentials configured).

Chat is a **deferred phase, not a rejected one**. The [PRD](/prd.md) still
specifies a chat interface (S3), a synthesized answer citing case numbers (S6)
and conversational follow-ups (S8); that work is planned once the search
functionality here is settled. This frontend is an interim deliverable against
that spec, which is why the PRD has not been amended to match it.

## Deployment

Not deployed — see [deployment state](/reference/deployment-state.md).
