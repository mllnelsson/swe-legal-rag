"""Read the crawler's headline into the parts it concatenates.

The OData listing gives each decision a headline of the form
``Beslut 2026-23  Avskrivning`` — the beslutsnummer and the decision's title run
together. It is stored verbatim in ``documents.source_headline`` because that
column's contract is "what the listing said", but neither half is much use
glued to the other:

* the beslutsnummer half corroborates what the PDF's own trailer says, and is
  the only source when the trailer spells it in a way the parser missed;
* the title half duplicates ``documents.category``, so leaving it in place makes
  every API response repeat the decision number it already carries as a field.

Note the year-first order — ``Beslut 2026-23`` — which is the *reverse* of the
``Beslut: 23/2026`` the PDF trailer uses for the same identifier.

Pure: no I/O, no logging. Callers decide what to do with the parts.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

__all__ = ["SourceHeadline", "headline_title", "parse_source_headline"]


class SourceHeadline(BaseModel):
    """A crawler headline split into its beslutsnummer and its title."""

    model_config = ConfigDict(frozen=True)

    decision_number: str
    title: str


# "Beslut 2026-23  Avskrivning" — the listing sometimes doubles the space, and
# the sequence is written without the zero padding the ärendenummer uses.
_SOURCE_HEADLINE_RE = re.compile(
    r"^[ \t]*Beslut[ \t]+(?P<year>\d{4})-(?P<sequence>\d{1,3})[ \t]+(?P<title>\S.*?)[ \t]*$"
)


def parse_source_headline(headline: str | None) -> SourceHeadline | None:
    """Split a crawler headline, or ``None`` if it is not in that shape.

    The beslutsnummer comes back in the same canonical ``N/YYYY`` space as
    :func:`shared.segmentation.normalize_decision_number`, so the two sources are
    directly comparable.
    """
    if headline is None:
        return None

    match = _SOURCE_HEADLINE_RE.match(headline)
    if match is None:
        return None

    return SourceHeadline(
        decision_number=f"{int(match.group('sequence'))}/{match.group('year')}",
        title=match.group("title"),
    )


def headline_title(headline: str | None) -> str | None:
    """The headline without its ``Beslut YYYY-NN`` prefix.

    Falls back to the headline unchanged when it is not in that shape: a
    presentation helper must never lose text it did not understand.
    """
    if headline is None:
        return None

    parsed = parse_source_headline(headline)
    return parsed.title if parsed is not None else headline
