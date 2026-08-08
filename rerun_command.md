# Applying branch `feature/feedback-after-ingest` to `overklagan`

`overklagan` is yours — nothing in this branch has been run against it. Everything below
was run verbatim against the `overklagan_coding_agent` sandbox first; the observed
numbers are recorded at each step so you can tell a good run from a bad one.

Run the four steps **in order**. Step 2 will refuse to complete until step 1 has.

Total wall time on the sandbox: about 4 minutes for step 4, plus however long the
metadata pass takes (step 3 makes one LLM call per document that needs a fallback).

---

## 0. Where `overklagan` is right now

```bash
psql -d overklagan -At -F ' | ' -c "
select (select count(*) from documents),
       (select count(*) from documents where case_number is null),
       (select count(*) from documents where case_number ~ '^(DK|Dk|S|ÖN)'),
       (select count(*) from documents where case_number like '%/%'),
       (select count(*) from document_references),
       (select count(*) from unresolved_references),
       (select version_num from alembic_version);"
```

Expected before you start: `185 | 43 | 6 | 9 | 23 | 30 | 005`.

Those 43 nulls and 15 malformed `case_number`s are the **previous** branch's fix not yet
applied — this database has not had a metadata pass since that landed. That is why step 3
exists and is not optional.

---

## 1. Delete the duplicate 21/2021

The OData listing published decision 21/2021 twice, under document ids 2265536 and
2266136. Both rows hold byte-identical `raw_text` (md5 `4afea151…`), 5 chunks and 11
entity links each. Crawl no longer creates the second one, but it does not remove the one
already there — and the unique constraint added in step 2 will refuse to build until it
is gone.

Keep the earlier publication (2265536, 2021-09-03). No foreign key to `documents`
cascades, so the children go first, in this order:

```bash
psql -d overklagan -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
CREATE TEMP TABLE dup AS
  SELECT id FROM documents WHERE source_document_id = 2266136;
DELETE FROM chunks                WHERE document_id        IN (SELECT id FROM dup);
DELETE FROM document_entities     WHERE document_id        IN (SELECT id FROM dup);
DELETE FROM document_references   WHERE source_document_id IN (SELECT id FROM dup)
                                     OR target_document_id IN (SELECT id FROM dup);
DELETE FROM unresolved_references WHERE source_document_id IN (SELECT id FROM dup);
DELETE FROM tasks                 WHERE document_id        IN (SELECT id FROM dup);
DELETE FROM documents             WHERE id                 IN (SELECT id FROM dup);
-- must print 1
SELECT count(*) AS remaining_21_2021 FROM documents WHERE decision_number = '21/2021';
COMMIT;
SQL
```

On the sandbox this deleted 5 chunks, 10 entity links, 7 tasks and 1 document, and
printed `1`. If it prints `2`, stop — the wrong row matched.

## 2. Migrate

```bash
uv run alembic upgrade head          # 005 -> 006
```

Adds `documents.source_decision_number`, backfills it from `source_headline`, then adds
`uq_documents_source_decision_number`. The constraint is the check that step 1 worked: if
a duplicate is still present the migration aborts with

```
could not create unique index "uq_documents_source_decision_number"
DETAIL:  Key (source_decision_number)=(21/2021) is duplicated.
```

and rolls back cleanly, leaving the column absent and the revision at 005.

Verify — expected `184 | 0`, i.e. every document got a key:

```bash
psql -d overklagan -At -F ' | ' -c "
select count(*), count(*) filter (where source_decision_number is null) from documents;"
```

## 3. Re-run metadata

Applies the previous branch's fix: the slash spelling of an ärendenummer is read, and an
LLM-supplied identifier that does not canonicalise is stored as `NULL` rather than as a
plausible wrong value.

```bash
for id in $(psql -d overklagan -At -c "select id from documents order by decision_date;"); do
  uv run python scripts/run_step.py metadata "$id"
done
```

Verify — expected `2 | 0 | 0`, the two being 14/2020 and 25/2020, which genuinely have no
`Ärendenummer:` line in the source:

```bash
psql -d overklagan -At -F ' | ' -c "
select count(*) filter (where case_number is null),
       count(*) filter (where case_number ~ '^(DK|Dk|S|ÖN)'),
       count(*) filter (where case_number like '%/%')
from documents;"
```

Spot-check a few: 5/2021 → `2021-0002`, 4/2020 → `2020-0012`, 20/2022 → `2022-0015`,
16/2020 → `2020-0019`, 1/2021 → `2020-0036`.

## 4. Clear and rebuild the cross-references

**The truncate is required, not tidiness.** `document_references` has no delete path —
`persist`/`upsert` only ever adds. Step 3 changes 58 documents' identifiers, so a citation
that previously resolved to the wrong target would leave that wrong edge behind forever.
Both tables are derived entirely from document text plus those identifiers, so dropping
and rebuilding them is safe and is the only way to be sure nothing stale survives.

Entity links need no equivalent step: extract deletes a document's missing links itself
(`delete_missing_for_document`). Orphaned rows left in `entities` are harmless — the
`/vokabular` counts join through `document_entities`.

```bash
psql -d overklagan -v ON_ERROR_STOP=1 -c "TRUNCATE document_references, unresolved_references;"

for id in $(psql -d overklagan -At -c "select id from documents order by decision_date;"); do
  uv run python scripts/run_step.py extract "$id"
done
```

`decision_date` order matters: a document citing a *later* decision parks as unresolved
and is promoted by `reconcile_references` when that later document is extracted.

Verify:

```bash
psql -d overklagan -At -F ' | ' -c "
select (select count(*) from document_references),
       (select count(*) from unresolved_references);"
```

Sandbox result: **28 | 83** (was 23 | 30). The rise is the citation-list fix — 54
identifiers extracted corpus-wide before, 116 after, with none of the old ones lost. Most
of the new ones are unresolved because they cite pre-2020 decisions genuinely outside the
corpus.

Two citations resolve that never did before; both should come back as rows:

```bash
psql -d overklagan -At -F ' -> ' -c "
select s.decision_number, t.decision_number
from document_references r
join documents s on s.id = r.source_document_id
join documents t on t.id = r.target_document_id
where (s.decision_number, t.decision_number)
      in (('23/2022','24/2020'), ('25/2026','15/2022'));"
```

---

## Not needed

- **download, parse, chunk, embed** — untouched by this branch. No re-download, no
  re-embed.
- **A re-crawl** — the crawl fix prevents a *future* duplicate. It cannot remove the
  existing one, which is what step 1 is for.

## Still unverified against a real host

The retry fix (219 retries against 221 calls) is proved by unit tests and a loopback
server: 0 retries with it, 3 without, over 4 messages. It has **not** been exercised
against `api.berget.ai`, because the extract pass in step 4 made zero LLM calls —
rule-based extraction was complete for all 184 sandbox documents. Step 3's metadata pass
is the first real test: watch for `openai._base_client: Retrying request` in its output.
There should be none.
