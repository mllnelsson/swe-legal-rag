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

Reserved means those two filenames only. The week files under `log/` are
ordinary files as far as rule 1 goes and carry frontmatter — see
[log.md](#logmd).

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
- `Log` — one week of bundle history under `log/` (see [log.md](#logmd)); the
  only type that is not a concept

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

## Finding what to edit

A concept file can run to several hundred lines, and a typical edit changes well
under a tenth of one. Loading whole files to change a paragraph is the main way a
long editing pass runs out of room. **Search for the subject of the edit, and
read only what the search finds.**

1. **Search, don't browse.** Name the thing you are correcting — an identifier, a
   config key, a literal path, a number, the old wording — and grep the bundle
   for it. One command gives you both the file and the line:

   ```bash
   grep -rn 'install_file_tracing' documentation/ --include='*.md'
   grep -rn 'STORAGE_BACKEND' documentation/ --include='*.md'
   ```

   Search the **whole bundle**, not the file you assume is wrong. One fact
   restated across several files is the normal case, and the grep is what finds
   the copies you did not think of. An `index.md` tells you what exists; a grep
   tells you where a fact actually lives. Reach for the index when you need to
   know what concepts there are, and for a grep when you know what is wrong.

2. **Read the region, not the file.** Open each hit with an offset and a limit —
   roughly forty lines either side is enough to see the section it sits in:

   ```
   Read <file> offset=<hit line − 40> limit=80
   ```

   A partial read is enough to edit with; you do not have to load a file to
   change it. Widen only if the edit turns out to span more than you can see.

3. **Edit, then re-run the same search.** The grep that found the stale fact is
   what confirms it is gone — and catches the copies still standing.

Read a concept whole only when you are rewriting most of it, or when it is short
enough that the question does not arise.

## log.md

Optional at any level. History is **one file per week**, so no single file grows
without bound: `log.md` is a reserved index of weeks, and the entries live in
`log/week-of-<monday>.md` beside it, each `type: Log`.

A week is named for its **Monday** and filed under the month that Monday falls
in — one rule, used twice. The week of 2026-07-27 to 2026-08-02 is
`week-of-2026-07-27.md` under `## 2026-07`, its August entries included; a week
never splits across two files.

Within a week, entries are date-grouped **newest first** under ISO 8601
`YYYY-MM-DD` headings, and `log.md` lists the weeks newest first the same way.
The leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is
convention, not requirement. Keep an entry to one line and link the concept.

```markdown
---
type: Log
title: Documentation Update Log — week of 2026-08-17
description: Documentation bundle changes recorded in the week of 2026-08-17, newest first.
timestamp: 2026-08-22T00:00:00Z
---

# Documentation Update Log — week of 2026-08-17

## 2026-08-22
* **Update**: Added retry semantics to [payments API](/api/payments.md).
```

### Adding an entry

Today's date picks the file, never what the index happens to list. Compute this
Monday rather than counting back by hand — and not with `date -v-mon`, which is
BSD-only:

```bash
python3 -c "import datetime as d;t=d.date.today();print(t-d.timedelta(days=t.weekday()))"
```

1. `log/week-of-<that date>.md` is the file. If it is missing, create it with the
   frontmatter above and add its line to `log.md`, under that month's `## YYYY-MM`
   heading (adding the heading if the month is new). Starting a week is that and
   nothing more: **never move, merge or rewrite a past week's file.**
2. `head -40` that file for today's date heading. Insert under it, or add the
   heading at the top if today is not there yet. Never read or rewrite a week
   file whole.
3. If your entry is the newest in the week, bump that file's `timestamp`.

## Citations

External sources backing claims go under a `# Citations` heading at the bottom,
numbered:

```markdown
# Citations

[1] [Upstream API changelog](https://example.com/changelog)
```

## Anti-patterns

- **Concept docs are not changelogs.** History belongs in the week log. A concept
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
- An entry exists in this week's `log/week-of-<monday>.md` for creations and
  substantive updates, and that file is listed in `log.md`.
- New links use the `/`-absolute form.
