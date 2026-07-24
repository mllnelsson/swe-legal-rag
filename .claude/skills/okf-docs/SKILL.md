---
name: okf-docs
description: Read, write, and maintain documentation in the Open Knowledge Format (OKF v0.1) — a bundle of markdown concept files with YAML frontmatter. Use when creating or editing any file under the docs bundle, when adding a concept for a new table/API/metric/playbook, when updating index.md or log.md, or when checking a bundle for conformance.
---

# OKF documentation

Docs in this repo are an OKF **knowledge bundle**: a directory tree of markdown
files, each describing one **concept**. OKF v0.1 is a draft spec — treat the
structural rules below as fixed and everything else as local convention.

Bundle root: `./documentation/`

## Hard rules (conformance)

A bundle is conformant only if all three hold. Never break these:

1. Every non-reserved `.md` file has a parseable YAML frontmatter block.
2. Every frontmatter block has a non-empty `type` field.
3. `index.md` and `log.md` are **reserved filenames** at every level. They are
   never concept documents. Never name a concept `index.md` or `log.md`.

## Concept documents

```yaml
---
type: <required — short string, e.g. Service, API Endpoint, Metric, Playbook>
title: <human-readable display name>
description: <one sentence; this is what index.md and search snippets show>
resource: <canonical URI of the thing described; omit for abstract concepts>
tags: [<tag>, <tag>]
timestamp: <ISO 8601, e.g. 2026-07-24T14:30:00Z — last meaningful change>
---
```

Only `type` is required. `title`, `description`, `resource`, `tags`, and
`timestamp` are recommended in that priority order. Additional producer-defined
keys are allowed; preserve unknown keys when editing a file rather than
stripping them.

**Concept ID** is the file path minus `.md` — `tables/users.md` is `tables/users`.
Renaming a file changes its ID and breaks inbound links.

### Type vocabulary

Type values are not centrally registered, but consistency within a bundle is
what makes filtering useful. Use only these values; propose additions rather
than inventing them inline:

- `Spec` — a product/system requirement document (e.g. the PRD)
- `Table` — a database table
- `Service` — a pipeline worker (a deployable unit)
- `Package` — a code package (llm-core, ai, shared, api)
- `Repository` — a data-access module bridging SQLAlchemy models (DAOs) and Pydantic DTOs, injected as a Protocol-typed namespace
- `API Endpoint` — a single route and its wire contract
- `Decision` — an architecture decision record (carries a `Status:`)
- `Playbook` — an operational procedure
- `Reference` — reference material / mirrored external contract
- `Concept` — a cross-cutting design concept (architecture overview, worker patterns, retrieval agent, testing strategy)

### Body

Favor structural markdown — headings, tables, lists, fenced code — over
freeform prose. Structure helps both human scanning and agent retrieval.

No body sections are required. These headings have conventional meaning and
should be used when applicable: `# Schema`, `# Examples`, `# Citations`.

## Cross-linking

Use **absolute, bundle-relative** links beginning with `/`:

```markdown
See the [customers table](/tables/customers.md) for the join key.
```

This form survives moving a document within its subdirectory. Relative links
(`./other.md`) are legal but discouraged.

A link asserts an untyped relationship — the *kind* of relationship is carried
by the surrounding prose, not the link. Write the sentence so the relationship
is legible.

Broken links are tolerated by the spec and often represent not-yet-written
knowledge. Do not delete a link merely because its target is missing, and do
not create a stub file just to satisfy one.

## index.md

Optional in any directory, supporting progressive disclosure — letting a reader
see what exists before opening files.

**Index files contain no frontmatter.** The single exception: the bundle-root
`index.md` may carry `okf_version: "0.1"`, and that is the only place
frontmatter is permitted in an index.

```markdown
# Section Heading

* [Title](relative-url) - description copied from the target's frontmatter
* [Subdirectory](subdir/) - what this group covers
```

Entry descriptions should be the `description` field of the linked concept. When
you change a concept's `description`, update every index entry pointing at it.

## log.md

Optional at any level. Flat list of date-grouped entries, **newest first**.
Date headings must be ISO 8601 `YYYY-MM-DD`.

```markdown
# Directory Update Log

## 2026-07-24
* **Update**: Added retry semantics to [payments API](/api/payments.md).
* **Creation**: Established the [oncall playbook](/playbooks/oncall.md).
```

The leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is
convention, not requirement. Keep entries to one line and link the concept.

## Citations

External sources backing claims go under a `# Citations` heading at the bottom,
numbered:

```markdown
# Citations

[1] [Upstream API changelog](https://example.com/changelog)
```

## Anti-patterns

- **Concept docs are not changelogs.** History belongs in `log.md`. A concept
  describes the thing as it is *now*, in present tense, with no "previously
  this returned X" narration.
- **One concept per file.** If a file needs two `type` values, it is two files.
- **Do not document a code change that changes nothing a reader relies on.**
  Refactors, renamed internals, and test changes usually warrant no doc edit at
  all. Silence is a valid outcome.
- **Do not invent `type` values** to fit an awkward document. Reshape the
  document or propose a vocabulary addition.
- **Do not bump `timestamp` on cosmetic edits.** It means last *meaningful*
  change, and readers use it to judge staleness.
- **Do not create stub concepts** with a frontmatter block and an empty body to
  satisfy a link. An unresolved link is better than a hollow file.

## Before finishing

- Every touched file still has `type` in its frontmatter.
- `timestamp` updated on files with substantive changes, left alone otherwise.
- New concepts are listed in their directory's `index.md`.
- A `log.md` entry exists for creations and substantive updates.
- New links use the `/`-absolute form.
