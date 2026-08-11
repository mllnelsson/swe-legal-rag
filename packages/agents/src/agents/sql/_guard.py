"""Static checks on model-authored SQL, before it reaches Postgres.

Defence in depth, not the primary control. The real guarantee that nothing is
written is the read-only transaction in `_sandbox`; what this module adds is a
narrower reachable surface — one statement, only corpus tables, no payload-sized
columns — and error messages precise enough for the model to repair from.

Every check runs against a *normalised copy* of the statement with comments and
string literals removed, so a keyword inside `WHERE category ILIKE '%create%'`
cannot trip a rule. The statement that executes is always the caller's original.
"""

from __future__ import annotations

import re

from agents.errors import SqlRejectedError
from agents.sql._schema import (
    blocked_columns,
    exposed_tables,
    grounding_required_columns,
)
from agents.sql._semantic_model import SemanticModelDocument

__all__ = ["check_sql", "find_predicate_columns"]

_ALLOWED_HEAD_KEYWORDS = frozenset({"select", "with"})

# Statement kinds that may not appear anywhere, including inside a CTE. A
# data-modifying CTE (`WITH x AS (DELETE ... RETURNING ...)`) is a SELECT-headed
# statement that writes, which is exactly what the head-keyword check alone
# would miss.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "alter",
        "call",
        "comment",
        "copy",
        "create",
        "delete",
        "do",
        "drop",
        "execute",
        "grant",
        "insert",
        "lock",
        "merge",
        "prepare",
        "refresh",
        "reindex",
        "reset",
        "revoke",
        "set",
        "truncate",
        "update",
        "vacuum",
    }
)

# Server-side functions that read or write outside the corpus, or that let a
# query burn wall-clock time. `pg_*` is blocked wholesale by `_PG_IDENTIFIER`
# below; these are the ones that do not carry the prefix.
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "current_setting",
        "dblink",
        "lo_export",
        "lo_import",
        "set_config",
    }
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_DOLLAR_QUOTED = re.compile(r"\$\w*\$.*?\$\w*\$", re.DOTALL)

# A `*` sitting in a select-list position — followed by a comma or FROM. Written
# this way so `count(*)` (followed by `)`) and arithmetic like `100.0 * total`
# (followed by an identifier) both survive; the agent needs each of them.
_STAR_EXPANSION = re.compile(r"(?:^|[\s,(])(?:\w+\.)?\*\s*(?:,|from\b|$)")

# Table references. Only FROM/JOIN targets are checked rather than every word in
# the statement: a column alias called `sessions` is harmless, a `FROM sessions`
# is not, and scanning bare words would reject the former too.
_TABLE_REFERENCE = re.compile(r"\b(?:from|join)\s+(?!\()([a-z_][a-z0-9_.]*)")

# SQL functions that spell their arguments with FROM/IN as separators —
# `extract(year FROM decision_date)`, `substring(x FROM 1 FOR 2)`. The word after
# FROM there is a column, not a table, and year extraction is bread and butter
# for this agent. Their argument lists are blanked before table references are
# scanned; one level of nesting is enough for anything the model writes.
_KEYWORD_ARGUMENT_CALL = re.compile(
    r"\b(?:extract|substring|trim|overlay|position)\s*"
    r"\((?:[^()]|\([^()]*\))*\)"
)
_CTE_NAME = re.compile(r"(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(")
_PG_IDENTIFIER = re.compile(r"\bpg_\w+")
_IDENTIFIER = re.compile(r"\b[a-z_][a-z0-9_]*\b")


def _normalise(sql: str) -> str:
    """Lowercase the statement with comments and literals blanked out.

    Literals become `''` rather than vanishing so that token boundaries either
    side of them survive.
    """
    stripped = _BLOCK_COMMENT.sub(" ", sql)
    stripped = _LINE_COMMENT.sub(" ", stripped)
    stripped = _DOLLAR_QUOTED.sub(" '' ", stripped)
    stripped = _STRING_LITERAL.sub(" '' ", stripped)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _check_single_statement(normalised: str) -> None:
    if ";" in normalised.rstrip().rstrip(";"):
        raise SqlRejectedError(
            "Endast en sats åt gången. Ta bort allt efter det första semikolonet."
        )


def _check_head_keyword(normalised: str) -> None:
    head = normalised.split(None, 1)[0] if normalised else ""
    if head not in _ALLOWED_HEAD_KEYWORDS:
        raise SqlRejectedError(
            f"Satsen måste börja med SELECT eller WITH, inte {head.upper() or 'tomt'}."
        )


def _check_forbidden_keywords(normalised: str) -> None:
    tokens = set(_IDENTIFIER.findall(normalised))
    forbidden = sorted(tokens & _FORBIDDEN_KEYWORDS)
    if forbidden:
        raise SqlRejectedError(
            f"Otillåtet nyckelord: {', '.join(forbidden).upper()}. "
            "Frågan måste vara enbart läsande."
        )

    forbidden_calls = sorted(tokens & _FORBIDDEN_FUNCTIONS)
    if forbidden_calls:
        raise SqlRejectedError(f"Otillåten funktion: {', '.join(forbidden_calls)}.")

    system_identifiers = sorted(set(_PG_IDENTIFIER.findall(normalised)))
    if system_identifiers:
        raise SqlRejectedError(
            f"Systemobjekt är inte läsbara: {', '.join(system_identifiers)}."
        )


def _check_star_expansion(normalised: str) -> None:
    if _STAR_EXPANSION.search(normalised):
        raise SqlRejectedError(
            "SELECT * är inte tillåtet — vissa kolumner är för stora att returnera. "
            "Räkna upp de kolumner du faktiskt behöver. count(*) går bra."
        )


def _check_blocked_columns(normalised: str, blocked: frozenset[str]) -> None:
    referenced = sorted(set(_IDENTIFIER.findall(normalised)) & blocked)
    if referenced:
        raise SqlRejectedError(
            f"Kolumnen/kolumnerna {', '.join(referenced)} kan inte hämtas. "
            "De är för stora eller saknar läsbart innehåll."
        )


def _check_table_allowlist(normalised: str, exposed: frozenset[str]) -> None:
    # Blanked here and not in `_normalise`: the other checks still need to see
    # inside these calls, so that `substring(raw_text from 1)` is caught as a
    # read of a blocked column.
    scannable = _KEYWORD_ARGUMENT_CALL.sub(" x ", normalised)
    known = exposed | set(_CTE_NAME.findall(scannable))
    referenced = {name.split(".")[-1] for name in _TABLE_REFERENCE.findall(scannable)}
    unknown = sorted(referenced - known)
    if unknown:
        raise SqlRejectedError(
            f"Tabellen/tabellerna {', '.join(unknown)} är inte läsbara. "
            f"Tillgängliga tabeller: {', '.join(sorted(exposed))}."
        )


# Where a value starts being *tested* rather than merely selected.
_PREDICATE_START = re.compile(r"\b(?:where|having|on)\b")

# Where it stops. A predicate segment runs from one of the keywords above until
# one of these, rather than to the end of the statement: `GROUP BY category` and
# `ORDER BY name` name a column without testing it, and a JOIN's ON clause would
# otherwise drag every one of them into predicate context.
#
# `from` is deliberately absent. It cannot open a clause that a `select` has not
# already closed, and treating it as a terminator would truncate
# `substring(decision_outcome from 1 for 5) = '...'` into a grounding bypass.
_PREDICATE_END = re.compile(
    r"\b(?:select|group\s+by|order\s+by|limit|offset|fetch|window|"
    r"union|intersect|except)\b"
)


def _predicate_regions(normalised: str) -> list[str]:
    """The spans of a statement in which a column is being compared to something."""
    regions: list[str] = []
    for match in _PREDICATE_START.finditer(normalised):
        rest = normalised[match.end() :]
        end = _PREDICATE_END.search(rest)
        regions.append(rest if end is None else rest[: end.start()])
    return regions


def find_predicate_columns(
    sql: str, document: SemanticModelDocument | None = None
) -> set[tuple[str, str]]:
    """Which free-text columns `sql` filters on, as opposed to just returning.

    The distinction is what keeps forced grounding from being circular: the
    model's natural first move is `SELECT category, count(*) ... GROUP BY 1`,
    which *is* an act of grounding, and demanding it be grounded first would
    deadlock the loop. Only a column being compared against a value needs the
    agent to have looked at the vocabulary first.

    Column names are matched unqualified. Of the exposed tables only `entities`
    has a `name`, so the mapping back to a table is unambiguous; a false positive
    would in any case cost nothing worse than one extra lookup.
    """
    identifiers = {
        identifier
        for region in _predicate_regions(_normalise(sql))
        for identifier in _IDENTIFIER.findall(region)
    }
    return {
        (table, column)
        for table, column in grounding_required_columns(document)
        if column in identifiers
    }


def check_sql(sql: str, document: SemanticModelDocument | None = None) -> None:
    """Raise `SqlRejectedError` if `sql` may not be executed.

    The message is written for the model, not for a log: the tool executor hands
    it back as a tool result so the next iteration can correct the query.
    """
    normalised = _normalise(sql)
    if not normalised:
        raise SqlRejectedError("Tom fråga.")

    _check_single_statement(normalised)
    _check_head_keyword(normalised)
    _check_forbidden_keywords(normalised)
    _check_star_expansion(normalised)
    _check_blocked_columns(normalised, blocked_columns(document))
    _check_table_allowlist(normalised, exposed_tables(document))
