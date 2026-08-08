"""Regex extraction of entities and cross-references from a segmented decision.

Two rules shape everything here, both consequences of decision PDFs carrying the
appealed decision as an appendix (see :mod:`shared.segmentation`):

* **References come from the body only.** A reference found in an appendix is the
  *lower instance* citing something, not Överklagandenämnden. The trailer is
  excluded too — it holds the document's own identifiers, so scanning it made every
  decision cite itself.
* **Only the holding confers primacy.** Relevance used to be positional (latter 60 %
  of the text), which an appendix inverts: the tail of the document *is* the appealed
  decision, so its entities were the ones being promoted.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ai.dtos import EntityResult, ExtractedEntity, ExtractedReference
from shared.enums import EntityRelevance, EntityType
from shared.segmentation import (
    DocumentSegments,
    normalize_case_number,
    normalize_cited_decision_number,
)
from worker_extract.entities import deduplicate_entities

# A citation is an anchor word followed by a list of numbers. Both halves matter:
#
#   * The **anchor** is what picks the identifier space, because the two spaces
#     share a shape — "ÖN 2020-36" is ärende 2020-0036 while "beslut 2020-36" is
#     decision 36/2020. It is also what keeps bare fractions and dates in prose
#     from being read as citations at all.
#   * The **list** is what the previous single-shot patterns missed. The corpus
#     writes "nämndens beslut 13/2011, 31/2011 och 16/2015", and requiring the
#     anchor before every item found only the first — 54 references over the
#     2020-2026 corpus where scanning the list finds 116.
#
# The PDF wraps mid-list, so one line break is allowed wherever a space is.
_REF_GAP = r"[ \t]*\n?[ \t]*"
_REF_SEPARATOR = r"[ \t]*[/–-][ \t]*"
# The guards `shared.segmentation` already applies: a following date component
# disqualifies the match, so "beslutet 2024-10-\n14" is a date, not decision
# 10/2024. `\s` and not `[ \t]`, precisely because the line may break there.
_REF_NOT_A_DATE = r"\b(?![-–/]\s*\d)"

# "ÖN 2025-0017", "ÖN dnr 2025-0017", "ärende ÖN 2022/2" — the ärendenummer space.
_CASE_ANCHOR_RE = re.compile(
    rf"\b(?:ärende[nt]?{_REF_GAP})?ÖN{_REF_GAP}(?:dnr{_REF_GAP})?", re.IGNORECASE
)
_CASE_IDENT_RE = re.compile(
    rf"\d{{4}}{_REF_SEPARATOR}(?!(?:19|20)\d{{2}}\b)\d{{1,4}}{_REF_NOT_A_DATE}"
)

# "beslut 13/2025", the hyphen spelling one decision uses, and the year-first
# spelling the registry uses in its own headlines — see
# `shared.segmentation.normalize_cited_decision_number` for why that is a
# beslutsnummer and not an ärendenummer.
_DECISION_ANCHOR_RE = re.compile(rf"\bbeslut(?:et|en)?{_REF_GAP}", re.IGNORECASE)
_DECISION_IDENT_RE = re.compile(
    rf"(?:\d{{1,3}}{_REF_SEPARATOR}(?:19|20)\d{{2}}"
    rf"|(?:19|20)\d{{2}}{_REF_SEPARATOR}\d{{1,3}}){_REF_NOT_A_DATE}"
)

# What continues a list rather than ending it: "25/2007, 06/2008 och 14/2016".
# The conjunctions are word-anchored so none of them can match the front of a
# longer word; the comma needs no such guard.
_REF_LIST_SEPARATOR_RE = re.compile(
    rf"{_REF_GAP}(?:,|(?:och|samt|respektive)\b){_REF_GAP}", re.IGNORECASE
)

# Kyrkoordningen is cited by two names and in both orders. Measured over the
# corpus, 213 citations put the lagrum first ("58 kap. 1 § kyrkoordningen") and 2
# put the name first — the reverse of what the patterns used to assume, which is
# why EntityType.REGULATION was an empty vocabulary.
#
# `KO` is matched case-sensitively and word-anchored: lowercased it is a common
# Swedish noun. Requiring the name at all is also what keeps the other statutes
# cited in the identical "N kap. M §" shape — tryckfrihetsförordningen, OSL,
# rättegångsbalken — out of the regulation vocabulary.
_KYRKOORDNINGEN = r"(?:i[ \t]+)?(?:[Kk]yrkoordningen|KO)\b"
_CHAPTER = r"(?P<chapter>\d{1,3})[ \t]*kap\.?"
# "1", "1 a", "7-8", "7 och 8" — the corpus writes ranges both ways.
_SECTIONS = (
    r"(?P<sections>\d{1,3}(?:[ \t]*[a-z]\b)?"
    r"(?:[ \t]*(?:[-–]|och)[ \t]*\d{1,3}(?:[ \t]*[a-z]\b)?)*)[ \t]*§{1,2}"
)
# "tredje stycket", "första stycket 4", "p. 4". Matched so the citation is not cut
# short before the statute's name, then dropped from the canonical form below.
_SUBCLAUSE = (
    r"(?:[ \t]+(?:första|andra|tredje|fjärde|femte|sjätte|sjunde|sista)"
    r"[ \t]+stycket)?"
    r"(?:[ \t]*(?:punkten[ \t]*|p\.[ \t]*)?\d{1,2})?"
)

_REGULATION_PATTERNS = [
    re.compile(rf"\b{_CHAPTER}[ \t]*{_SECTIONS}{_SUBCLAUSE}[ \t]+{_KYRKOORDNINGEN}"),
    re.compile(rf"\b(?:[Kk]yrkoordningen|KO)[ \t]+{_CHAPTER}[ \t]*{_SECTIONS}"),
    re.compile(r"\bKO[ \t]+(?P<chapter>\d{1,3}):(?P<sections>\d{1,3})\b"),
    # The spelled-out word order: "kyrkoordningen kapitel 32 § 5".
    re.compile(
        r"\b[Kk]yrkoordningen[ \t]+kapitel[ \t]+(?P<chapter>\d{1,3})"
        r"(?:[ \t]*§[ \t]*(?P<sections>\d{1,3}))?"
    ),
    # A whole chapter: "54 kap. kyrkoordningen", "58 kapitlet kyrkoordningen".
    re.compile(
        rf"\b(?P<chapter>\d{{1,3}})[ \t]*kap(?:\.|itlet)?[ \t]+{_KYRKOORDNINGEN}"
    ),
]

# Both range spellings collapse to a hyphen so one provision has one name.
_REGULATION_SECTION_SEPARATOR_RE = re.compile(r"[ \t]*(?:[-–]|och)[ \t]*")

# How many provisions a section range may name before it is kept whole rather than
# expanded. "57 kap. 8-19 §§" is the header lagrum line of 54 decisions — the
# statutory basis of the appeal, not a targeted citation — and splitting it into
# twelve entities would bury the provisions a decision actually turns on. Short
# ranges are the opposite case: "47 kap. 1-3 §§" beside "47 kap. 1 §" and "47 kap.
# 2 §" is one provision set written twice.
_MAX_EXPANDED_SECTIONS = 6

# A plain numeric range in the canonical section slot. Lettered sections ("1 a") and
# three-part lists are deliberately not expanded — enumerating them needs knowledge
# of the statute that a regex does not have.
_SECTION_RANGE_RE = re.compile(r"^(?P<first>\d{1,3})-(?P<last>\d{1,3})$")

# The two canonical shapes document-level subsumption compares. Parsing back what
# `_canonical_regulations` emitted keeps the entity list the only thing that has to
# cross between the body, the holding and the appendices.
_CANONICAL_CHAPTER_RE = re.compile(r"^(?P<chapter>\d{1,3}) kap\. kyrkoordningen$")
_CANONICAL_RANGE_RE = re.compile(
    r"^(?P<chapter>\d{1,3}) kap\. (?P<first>\d{1,3})-(?P<last>\d{1,3}) §§ kyrkoordningen$"
)

# The bodies a decision names, and the word order they are named in.
_PARISH_HEADS = ("församling", "stift", "pastorat")

# One word of a name: a capital and its lower-case tail. `pastorat` is here because
# the corpus names one 224 times and the patterns used to ignore it entirely.
#
# Excluding lower-case words is what bounds the run: "Kyrkofullmäktige i Y
# församling" stops at "Y" because "i" cannot join it. The old pattern took up to
# three words of any case and produced "kyrkofullmäktige i y församling", "beslut
# kyrkofullmäktige i y församling" and "motpart kyrkofullmäktige i y församling" as
# three entities for one body.
#
# Note what this vocabulary is worth: 134 of the 185 decisions are anonymised, so
# the names it finds are mostly the placeholders "X stift" and "Y församling". That
# is the corpus telling the truth about itself, not the extractor failing.
_NAME_WORD = r"[A-ZÅÄÖ][a-zåäö]*"
_PARISH_RE = re.compile(
    rf"\b(?P<name>{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,2}})"
    rf"[ \t]+(?P<head>{'|'.join(_PARISH_HEADS)})\b"
)

_KNOWN_ROLES = frozenset(
    {
        "kyrkoherde",
        "kyrkoråd",
        "kyrkofullmäktige",
        "biskop",
        "domkapitel",
        "kontraktsprost",
        "domprost",
        "stiftsstyrelse",
        "präst",
    }
)

_KNOWN_LEGAL_CONCEPTS = frozenset(
    {
        "överklagande",
        "behörighet",
        "jäv",
        "verkställighet",
        "tjänstetillsättning",
        "överklaganderätt",
        "tjänsteförseelse",
        "disciplinärende",
    }
)

# Swedish definite/genitive suffixes the keyword lookups tolerate.
_INFLECTION_SUFFIX = r"(?:en|et|s|ns|ts|n|t|r)?"

# Capitalised words that open a line, a sentence or a table row rather than a name.
# Derived from the corpus rather than from Swedish grammar: these are the words
# actually seen leading a parish match ("Motpart Y församling", "Eftersom S stift",
# the generic "En församling"), and the list grows when a new one shows up.
#
# Roles are stripped for the same reason and lose nothing: "Motpart Kyrkofullmäktige
# Y församling" is a table row, and `kyrkofullmäktige` is already extracted as a ROLE
# entity in its own right.
_NON_NAME_WORDS = _KNOWN_ROLES | frozenset(
    {
        "att",
        "av",
        "de",
        "den",
        "det",
        "eftersom",
        "en",
        "ett",
        "för",
        "från",
        "huruvida",
        "i",
        "motpart",
        "och",
        "som",
        "till",
        "ägare",
    }
)


def extract_references(segments: DocumentSegments) -> list[ExtractedReference]:
    """Find citations to other decisions, in either identifier space.

    Every spelling is canonicalised so `reference_service` can resolve it against
    `documents.case_number` / `documents.decision_number`. The canonical forms are
    disjoint, so the resulting string alone says which column to try.
    """
    references: list[ExtractedReference] = []
    seen: set[str] = set()

    matchers = (
        (_CASE_ANCHOR_RE, _CASE_IDENT_RE, normalize_case_number),
        (_DECISION_ANCHOR_RE, _DECISION_IDENT_RE, normalize_cited_decision_number),
    )
    for anchor, ident, normalize in matchers:
        for start, cited in _cited_identifiers(segments.body, anchor, ident):
            canonical = normalize(cited)
            if canonical is None or canonical in seen:
                continue
            seen.add(canonical)
            references.append(
                ExtractedReference(
                    case_number=canonical,
                    reference_context=_extract_sentence(segments.body, start),
                )
            )
    return references


def _cited_identifiers(
    body: str, anchor: re.Pattern[str], ident: re.Pattern[str]
) -> Iterator[tuple[int, str]]:
    """Every identifier an anchor introduces, including the rest of its list.

    Yields the anchor's own offset with each one so the whole list shares the
    sentence that introduced it — the second item of "beslut 25/2007, 06/2008"
    has no context of its own worth keeping.
    """
    for match in anchor.finditer(body):
        position = match.end()
        while (cited := ident.match(body, position)) is not None:
            yield match.start(), cited.group(0)
            position = cited.end()
            separator = _REF_LIST_SEPARATOR_RE.match(body, position)
            if separator is None:
                break
            position = separator.end()


def extract_entities_rule_based(segments: DocumentSegments) -> list[ExtractedEntity]:
    """Extract entities from the body and every appendix.

    The holding is scanned first at PRIMARY; because it is a slice of the body,
    every holding entity is also found at MENTIONED and de-duplication resolves the
    pair in PRIMARY's favour. Appendix entities stay MENTIONED unconditionally —
    they belong to the appealed decision, not to this one.

    Regulation subsumption runs last, over the merged list: whether a chapter is
    also cited at section level is a fact about the whole decision, not about the
    segment a citation happened to sit in.
    """
    entities = _entities_in(segments.holding or "", EntityRelevance.PRIMARY)
    entities += _entities_in(segments.body, EntityRelevance.MENTIONED)
    for appendix in segments.appendices:
        entities += _entities_in(appendix.text, EntityRelevance.MENTIONED)
    return _drop_subsumed_regulations(deduplicate_entities(entities))


def extract_rule_based(segments: DocumentSegments) -> EntityResult:
    return EntityResult(
        entities=extract_entities_rule_based(segments),
        references=extract_references(segments),
    )


async def extract_rule_based_strategy(
    segments: DocumentSegments, case_number: str | None = None
) -> EntityResult:
    """`extract_rule_based` in `ExtractionStrategy` shape.

    Async and accepting `case_number` only to satisfy the common signature.
    Rule-based extraction does no I/O and does not need the case number:
    excluding the trailer already removes the document's own identifiers.
    """
    return extract_rule_based(segments)


def _entities_in(text: str, relevance: EntityRelevance) -> list[ExtractedEntity]:
    if not text:
        return []
    found = (
        [(name, EntityType.REGULATION) for name in _match_regulations(text)]
        + [(name, EntityType.PARISH) for name in _match_parishes(text)]
        + [(name, EntityType.ROLE) for name in _match_keywords(text, _KNOWN_ROLES)]
        + [
            (name, EntityType.LEGAL_CONCEPT)
            for name in _match_keywords(text, _KNOWN_LEGAL_CONCEPTS)
        ]
    )
    return [
        ExtractedEntity(name=name, type=entity_type, relevance=relevance)
        for name, entity_type in found
    ]


def _match_regulations(text: str) -> list[str]:
    """Cited kyrkoordningen provisions, one canonical name each.

    Run over whitespace-collapsed text so a citation the PDF broke across a line
    wrap still matches; entity names carry no offsets, so nothing downstream
    depends on the original positions.
    """
    collapsed = " ".join(text.split())
    names: list[str] = []
    seen: set[str] = set()
    for pattern in _REGULATION_PATTERNS:
        for match in pattern.finditer(collapsed):
            for name in _canonical_regulations(match):
                if name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def _canonical_regulations(match: re.Match[str]) -> list[str]:
    """The provisions one citation names: ``N kap. M § kyrkoordningen`` each.

    Follows the order the corpus overwhelmingly uses, so both citation orders and
    both names of the statute collapse to one entity rather than four.

    The sub-clause is deliberately dropped: "58 kap. 18 §" and "58 kap. 18 §
    tredje stycket" cite the same provision, and keeping them apart fragments the
    vocabulary the entity graph exists to join on.

    Usually one name. A short range yields one per section, so a decision citing
    both "47 kap. 1-3 §§" and "47 kap. 1 §" has one vocabulary rather than two
    overlapping ones. A long range stays whole — see `_MAX_EXPANDED_SECTIONS` for
    why the cap is where it is.
    """
    chapter = match.group("chapter")
    sections = match.groupdict().get("sections")
    if sections is None:
        return [f"{chapter} kap. kyrkoordningen"]

    normalized = _REGULATION_SECTION_SEPARATOR_RE.sub("-", " ".join(sections.split()))
    expanded = _expand_section_range(normalized)
    if expanded is not None:
        return [f"{chapter} kap. {section} § kyrkoordningen" for section in expanded]

    marker = "§§" if "-" in normalized else "§"
    return [f"{chapter} kap. {normalized} {marker} kyrkoordningen"]


def _expand_section_range(sections: str) -> list[str] | None:
    """The sections a short numeric range names, or ``None`` to keep it whole."""
    match = _SECTION_RANGE_RE.match(sections)
    if match is None:
        return None

    first, last = int(match.group("first")), int(match.group("last"))
    if first >= last or last - first + 1 > _MAX_EXPANDED_SECTIONS:
        return None
    return [str(section) for section in range(first, last + 1)]


def _drop_subsumed_regulations(
    entities: list[ExtractedEntity],
) -> list[ExtractedEntity]:
    """Remove regulations another citation on the same document already covers.

    Two redundancies survive canonicalisation, and both read on the decision page
    as one provision listed several ways:

    * a bare chapter says nothing a document that also cites "47 kap. 1 §" has not
      already said;
    * a range inside a longer range of the same chapter — "57 kap. 8-18 §§" against
      "57 kap. 8-19 §§".

    Only a range is ever dropped into a range, never a single section. The long
    ranges `_canonical_regulations` leaves unexpanded are broad statutory bases:
    letting "8 kap. 7-39 §§" swallow "8 kap. 12 §" would delete the one provision
    the decision turns on.
    """
    regulations = [e for e in entities if e.type is EntityType.REGULATION]
    names = {entity.name for entity in regulations}
    ranges = [
        parsed
        for entity in regulations
        if (parsed := _parse_canonical_range(entity.name)) is not None
    ]
    subsumed = {name for name in names if _is_subsumed(name, names, ranges)}
    return [
        entity
        for entity in entities
        if not (entity.type is EntityType.REGULATION and entity.name in subsumed)
    ]


def _parse_canonical_range(name: str) -> tuple[str, int, int] | None:
    """``(chapter, first, last)`` for a canonical range name, else ``None``."""
    match = _CANONICAL_RANGE_RE.match(name)
    if match is None:
        return None
    return match.group("chapter"), int(match.group("first")), int(match.group("last"))


def _is_subsumed(
    name: str, names: set[str], ranges: list[tuple[str, int, int]]
) -> bool:
    chapter_match = _CANONICAL_CHAPTER_RE.match(name)
    if chapter_match is not None:
        prefix = f"{chapter_match.group('chapter')} kap. "
        return any(other != name and other.startswith(prefix) for other in names)

    own = _parse_canonical_range(name)
    if own is None:
        return False

    chapter, first, last = own
    return any(
        other == chapter
        and (other_first, other_last) != (first, last)
        and other_first <= first
        and last <= other_last
        for other, other_first, other_last in ranges
    )


def _match_parishes(text: str) -> list[str]:
    """Named parishes, dioceses and pastorat, one canonical name each.

    The name is built from its parts rather than echoed from the source, so the
    head noun is always spelled the same way and the leading words the pattern had
    to allow through do not become part of it.
    """
    names: list[str] = []
    seen: set[str] = set()
    for match in _PARISH_RE.finditer(text):
        words = _drop_leading_non_name(match.group("name").split())
        if not words:
            continue
        name = f"{' '.join(words)} {match.group('head')}".lower()
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _drop_leading_non_name(words: list[str]) -> list[str]:
    """Strip the leading words that are not part of the name — see `_NON_NAME_WORDS`.

    Leading only. A name's own words are never reconsidered once the run has
    started, so "Mellersta Y pastorat" keeps both of its.
    """
    index = 0
    while index < len(words) and _is_non_name_word(words[index]):
        index += 1
    return words[index:]


def _is_non_name_word(word: str) -> bool:
    lowered = word.lower()
    return any(
        re.fullmatch(re.escape(other) + _INFLECTION_SUFFIX, lowered)
        for other in _NON_NAME_WORDS
    )


def _match_keywords(text: str, keywords: frozenset[str]) -> list[str]:
    # Sorted so extraction output is stable run to run: frozenset iteration order
    # depends on per-process string hash seeding.
    lowered = text.lower()
    return [
        keyword
        for keyword in sorted(keywords)
        if re.search(r"\b" + re.escape(keyword) + _INFLECTION_SUFFIX + r"\b", lowered)
    ]


def _extract_sentence(text: str, pos: int) -> str:
    sentence_start = max(0, text.rfind(".", 0, pos) + 1)
    sentence_end = text.find(".", pos)
    if sentence_end == -1:
        sentence_end = len(text)
    return text[sentence_start : sentence_end + 1].strip()
