"""Metadata browse, facets and the graph reads, against real Postgres.

Whether a filter reaches the SQL is not observable through a mock session, so
these run for real. They cover the repository functions the search API added:
paged browse, the facet vocabulary, and the joined graph reads that resolve an
edge to the thing on its other end.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from shared.dtos.chunk import ChunkCreate
from shared.dtos.document import DocumentCreate, DocumentUpdate
from shared.dtos.document_entity import DocumentEntityCreate
from shared.dtos.document_reference import DocumentReferenceCreate
from shared.dtos.entity import EntityCreate
from shared.dtos.search import DocumentFilter
from shared.dtos.unresolved_reference import UnresolvedReferenceCreate
from shared.enums import ChunkSection, EntityRelevance, EntityType

_SWEDISH_TEXT = "Kyrkorådet beslutade att bifalla överklagandet."


async def _seed_document(
    document_repo,
    session: AsyncSession,
    *,
    source_url: str,
    case_number: str | None = None,
    decision_number: str | None = None,
    decision_date: date | None = None,
    decision_outcome: str | None = None,
    category: str | None = None,
    headline: str | None = None,
    raw_text: str | None = _SWEDISH_TEXT,
) -> uuid.UUID:
    doc = await document_repo.create(
        session, DocumentCreate(source_url=source_url, source_headline=headline)
    )
    await document_repo.update(
        session,
        doc.id,
        DocumentUpdate(
            raw_text=raw_text,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            decision_outcome=decision_outcome,
            category=category,
        ),
    )
    await session.commit()
    return doc.id


async def _link_keyword(
    entity_repo,
    doc_entity_repo,
    document_repo,
    session: AsyncSession,
    name: str,
    *,
    count: int,
) -> uuid.UUID:
    """Seed `count` searchable documents all classified under one keyword."""
    entity = await entity_repo.upsert(
        session, EntityCreate(name=name, type=EntityType.KEYWORD)
    )
    for index in range(count):
        document_id = await _seed_document(
            document_repo,
            session,
            source_url=f"https://example.com/{name}-{index}.pdf",
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=entity.id,
                relevance=EntityRelevance.PRIMARY,
            ),
        )
    await session.commit()
    return entity.id


class TestListFilteredDocuments:
    async def test_unparsed_documents_are_excluded(
        self, document_repo, search_repo, session
    ):
        await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/b.pdf",
            raw_text=None,
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(), limit=10
        )

        assert len(rows) == 1

    async def test_date_filter_narrows_the_result(
        self, document_repo, search_repo, session
    ):
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/old.pdf",
            decision_date=date(2019, 6, 1),
        )
        recent = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/new.pdf",
            decision_date=date(2024, 6, 1),
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(date_from=date(2024, 1, 1)), limit=10
        )

        assert [row.id for row in rows] == [recent]

    async def test_case_number_matches_exactly(
        self, document_repo, search_repo, session
    ):
        target = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/a.pdf",
            case_number="2024-0142",
        )
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/b.pdf",
            case_number="2024-0143",
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(case_number="2024-0142"), limit=10
        )

        assert [row.id for row in rows] == [target]

    async def test_newest_first_ordering_puts_undated_documents_last(
        self, document_repo, search_repo, session
    ):
        undated = await _seed_document(
            document_repo, session, source_url="https://example.com/undated.pdf"
        )
        older = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/older.pdf",
            decision_date=date(2020, 1, 1),
        )
        newer = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/newer.pdf",
            decision_date=date(2024, 1, 1),
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(), limit=10
        )

        assert [row.id for row in rows] == [newer, older, undated]

    async def test_paging_does_not_repeat_or_skip_documents(
        self, document_repo, search_repo, session
    ):
        for index in range(5):
            await _seed_document(
                document_repo,
                session,
                source_url=f"https://example.com/{index}.pdf",
                decision_date=date(2024, 1, 1),
            )

        first = await search_repo.list_filtered_documents(
            session, DocumentFilter(), limit=2, offset=0
        )
        second = await search_repo.list_filtered_documents(
            session, DocumentFilter(), limit=2, offset=2
        )

        assert len({row.id for row in first} & {row.id for row in second}) == 0

    async def test_count_matches_the_filter_not_the_page(
        self, document_repo, search_repo, session
    ):
        for index in range(4):
            await _seed_document(
                document_repo, session, source_url=f"https://example.com/{index}.pdf"
            )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(), limit=2
        )
        total = await search_repo.count_filtered_documents(session, DocumentFilter())

        assert len(rows) == 2
        assert total == 4


class TestFacets:
    async def test_facets_report_values_with_counts_and_the_date_range(
        self, document_repo, search_repo, session
    ):
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/a.pdf",
            category="Utlämnande av handlingar",
            decision_outcome="avslår överklagandet",
            decision_date=date(2020, 3, 1),
        )
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/b.pdf",
            category="Utlämnande av handlingar",
            decision_outcome="bifaller överklagandet",
            decision_date=date(2024, 7, 1),
        )

        facets = await search_repo.get_facets(session)

        assert facets.document_count == 2
        assert facets.earliest_decision_date == date(2020, 3, 1)
        assert facets.latest_decision_date == date(2024, 7, 1)
        categories = {value.value: value.count for value in facets.categories}
        assert categories == {"Utlämnande av handlingar": 2}
        assert len(facets.decision_outcomes) == 2

    async def test_facet_values_actually_match_documents(
        self, document_repo, search_repo, session
    ):
        """The contract of a filter vocabulary: every value it offers finds something."""
        await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/a.pdf",
            category="Tjänstetillsättning",
        )

        facets = await search_repo.get_facets(session)

        for value in facets.categories:
            rows = await search_repo.list_filtered_documents(
                session, DocumentFilter(category=value.value), limit=10
            )
            assert len(rows) == value.count

    async def test_entity_type_facet_counts_documents_not_entities(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        for name in ("offentlighetsprincipen", "partsinsyn"):
            entity = await entity_repo.upsert(
                session, EntityCreate(name=name, type=EntityType.LEGAL_CONCEPT)
            )
            await doc_entity_repo.upsert(
                session,
                DocumentEntityCreate(
                    document_id=document_id,
                    entity_id=entity.id,
                    relevance=EntityRelevance.PRIMARY,
                ),
            )
        await session.commit()

        facets = await search_repo.get_facets(session)

        by_type = {value.value: value.count for value in facets.entity_types}
        assert by_type[EntityType.LEGAL_CONCEPT] == 1


class TestKeywordFacetAndFilter:
    async def test_facet_reports_the_sokord_vocabulary_with_document_counts(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        shared_keyword = await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "jäv", count=2
        )
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "avvisning", count=1
        )
        assert shared_keyword is not None

        facets = await search_repo.get_facets(session)

        assert [(v.value, v.count) for v in facets.keywords] == [
            ("jäv", 2),
            ("avvisning", 1),
        ]

    async def test_facet_excludes_unparsed_documents(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        # A decision with no raw_text is not searchable, so offering its keyword
        # would hand back a filter value that then matches nothing.
        document_id = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/a.pdf",
            raw_text=None,
        )
        entity = await entity_repo.upsert(
            session, EntityCreate(name="osynlig", type=EntityType.KEYWORD)
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=entity.id,
                relevance=EntityRelevance.PRIMARY,
            ),
        )
        await session.commit()

        facets = await search_repo.get_facets(session)

        assert [v.value for v in facets.keywords] == []

    async def test_filter_narrows_to_documents_carrying_the_keyword(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "jäv", count=2
        )
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "avvisning", count=1
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(keywords=["jäv"]), limit=10
        )

        assert len(rows) == 2

    async def test_filter_matches_exactly_not_by_substring(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        # Unlike `entity_names`, which is a free-text ILIKE: the facet publishes
        # the exact vocabulary, so a partial value is a caller error, not a hint.
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "avvisning", count=1
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(keywords=["avvis"]), limit=10
        )

        assert rows == []

    async def test_filter_is_case_insensitive_on_the_callers_side(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "jäv", count=1
        )

        rows = await search_repo.list_filtered_documents(
            session, DocumentFilter(keywords=["Jäv"]), limit=10
        )

        assert len(rows) == 1

    async def test_keyword_and_entity_filters_compose(
        self, document_repo, entity_repo, doc_entity_repo, search_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/both.pdf"
        )
        for name, entity_type in (
            ("jäv", EntityType.KEYWORD),
            ("kyrkoordningen 32 kap", EntityType.REGULATION),
        ):
            entity = await entity_repo.upsert(
                session, EntityCreate(name=name, type=entity_type)
            )
            await doc_entity_repo.upsert(
                session,
                DocumentEntityCreate(
                    document_id=document_id,
                    entity_id=entity.id,
                    relevance=EntityRelevance.PRIMARY,
                ),
            )
        await _link_keyword(
            entity_repo, doc_entity_repo, document_repo, session, "jäv", count=1
        )
        await session.commit()

        rows = await search_repo.list_filtered_documents(
            session,
            DocumentFilter(keywords=["jäv"], entity_types=[EntityType.REGULATION]),
            limit=10,
        )

        assert [row.id for row in rows] == [document_id]


class TestEntityBrowse:
    async def test_entities_are_listed_with_document_counts(
        self, document_repo, entity_repo, doc_entity_repo, session
    ):
        entity = await entity_repo.upsert(
            session,
            EntityCreate(name="offentlighetsprincipen", type=EntityType.LEGAL_CONCEPT),
        )
        for index in range(2):
            document_id = await _seed_document(
                document_repo, session, source_url=f"https://example.com/{index}.pdf"
            )
            await doc_entity_repo.upsert(
                session,
                DocumentEntityCreate(
                    document_id=document_id,
                    entity_id=entity.id,
                    relevance=EntityRelevance.MENTIONED,
                ),
            )
        await session.commit()

        rows = await entity_repo.list_entities(session, limit=10)

        assert len(rows) == 1
        assert rows[0].document_count == 2

    async def test_entities_with_no_documents_are_omitted(self, entity_repo, session):
        await entity_repo.upsert(
            session, EntityCreate(name="föräldralös", type=EntityType.LEGAL_CONCEPT)
        )
        await session.commit()

        rows = await entity_repo.list_entities(session, limit=10)

        assert rows == []

    async def test_type_and_name_filters_narrow_the_listing(
        self, document_repo, entity_repo, doc_entity_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        for name, entity_type in (
            ("offentlighetsprincipen", EntityType.LEGAL_CONCEPT),
            ("kyrkoordningen 54 kap", EntityType.REGULATION),
        ):
            entity = await entity_repo.upsert(
                session, EntityCreate(name=name, type=entity_type)
            )
            await doc_entity_repo.upsert(
                session,
                DocumentEntityCreate(
                    document_id=document_id,
                    entity_id=entity.id,
                    relevance=EntityRelevance.PRIMARY,
                ),
            )
        await session.commit()

        by_type = await entity_repo.list_entities(
            session, entity_type=EntityType.REGULATION, limit=10
        )
        by_name = await entity_repo.list_entities(
            session, name_query="offentlighet", limit=10
        )

        assert [row.name for row in by_type] == ["kyrkoordningen 54 kap"]
        assert [row.name for row in by_name] == ["offentlighetsprincipen"]
        assert await entity_repo.count_entities(session) == 2


class TestGraphReads:
    async def test_document_entities_resolve_to_names_with_primary_first(
        self, document_repo, entity_repo, doc_entity_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        mentioned = await entity_repo.upsert(
            session, EntityCreate(name="aaa-nämnd", type=EntityType.ROLE)
        )
        primary = await entity_repo.upsert(
            session,
            EntityCreate(name="zzz-princip", type=EntityType.LEGAL_CONCEPT),
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=mentioned.id,
                relevance=EntityRelevance.MENTIONED,
            ),
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=document_id,
                entity_id=primary.id,
                relevance=EntityRelevance.PRIMARY,
            ),
        )
        await session.commit()

        rows = await doc_entity_repo.list_entities_for_document(session, document_id)

        # Alphabetical ordering alone would put the mentioned role first.
        assert [row.name for row in rows] == ["zzz-princip", "aaa-nämnd"]
        assert rows[0].type == EntityType.LEGAL_CONCEPT

    async def test_documents_for_entity_carry_identity_and_honour_relevance(
        self, document_repo, entity_repo, doc_entity_repo, session
    ):
        entity = await entity_repo.upsert(
            session,
            EntityCreate(name="offentlighetsprincipen", type=EntityType.LEGAL_CONCEPT),
        )
        primary_doc = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/primary.pdf",
            case_number="2024-0142",
            decision_number="12/2024",
            headline="Beslut om utlämnande",
        )
        mentioned_doc = await _seed_document(
            document_repo, session, source_url="https://example.com/mentioned.pdf"
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=primary_doc,
                entity_id=entity.id,
                relevance=EntityRelevance.PRIMARY,
            ),
        )
        await doc_entity_repo.upsert(
            session,
            DocumentEntityCreate(
                document_id=mentioned_doc,
                entity_id=entity.id,
                relevance=EntityRelevance.MENTIONED,
            ),
        )
        await session.commit()

        every = await doc_entity_repo.list_documents_for_entity(
            session, entity.id, limit=10
        )
        only_primary = await doc_entity_repo.list_documents_for_entity(
            session, entity.id, relevance=EntityRelevance.PRIMARY, limit=10
        )

        assert len(every) == 2
        assert every[0].document_id == primary_doc
        assert every[0].case_number == "2024-0142"
        assert every[0].decision_number == "12/2024"
        assert every[0].headline == "Beslut om utlämnande"
        assert [row.document_id for row in only_primary] == [primary_doc]
        assert (
            await doc_entity_repo.count_documents_for_entity(
                session, entity.id, relevance=EntityRelevance.PRIMARY
            )
            == 1
        )

    async def test_references_resolve_both_directions_in_one_call(
        self, document_repo, doc_ref_repo, session
    ):
        middle = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/middle.pdf",
            case_number="2024-0142",
        )
        cited = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/cited.pdf",
            case_number="2020-0031",
            headline="Tidigare beslut",
        )
        citing = await _seed_document(
            document_repo,
            session,
            source_url="https://example.com/citing.pdf",
            case_number="2025-0009",
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=middle,
                target_document_id=cited,
                reference_context="Jämför ÖN 2020-0031.",
            ),
        )
        await doc_ref_repo.upsert(
            session,
            DocumentReferenceCreate(
                source_document_id=citing,
                target_document_id=middle,
                reference_context="Se ÖN 2024-0142.",
            ),
        )
        await session.commit()

        edges = await doc_ref_repo.list_references_for_document(session, middle)

        assert [edge.document_id for edge in edges.outgoing] == [cited]
        assert edges.outgoing[0].case_number == "2020-0031"
        assert edges.outgoing[0].headline == "Tidigare beslut"
        assert edges.outgoing[0].reference_context == "Jämför ÖN 2020-0031."
        assert [edge.document_id for edge in edges.incoming] == [citing]
        assert edges.incoming[0].case_number == "2025-0009"

    async def test_unresolved_references_are_readable_by_source_document(
        self, document_repo, unresolved_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        await unresolved_repo.upsert(
            session,
            UnresolvedReferenceCreate(
                source_document_id=document_id,
                target_case_number="2019-0031",
                reference_context="Jämför ÖN 2019-0031.",
            ),
        )
        await session.commit()

        rows = await unresolved_repo.get_by_source_document_id(session, document_id)

        assert [row.target_case_number for row in rows] == ["2019-0031"]


class TestChunkReads:
    async def test_chunks_come_back_in_reading_order_with_sections(
        self, document_repo, chunk_repo, session
    ):
        document_id = await _seed_document(
            document_repo, session, source_url="https://example.com/a.pdf"
        )
        await chunk_repo.bulk_create(
            session,
            [
                ChunkCreate(
                    document_id=document_id,
                    chunk_index=1,
                    chunk_text="andra stycket",
                    section=ChunkSection.APPENDIX,
                    appendix_label="Bilaga A",
                ),
                ChunkCreate(
                    document_id=document_id,
                    chunk_index=0,
                    chunk_text="första stycket",
                    section=ChunkSection.BODY,
                ),
            ],
        )
        await session.commit()

        rows = await chunk_repo.get_by_document_id(session, document_id)

        assert [row.chunk_index for row in rows] == [0, 1]
        assert rows[0].section == ChunkSection.BODY
        assert rows[1].section == ChunkSection.APPENDIX
        assert rows[1].appendix_label == "Bilaga A"
