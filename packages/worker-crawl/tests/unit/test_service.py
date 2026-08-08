import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from shared.dtos.document import DocumentRead
from shared.dtos.task import TaskRead
from shared.enums import PipelineStep
from shared.queue.base import QueueMessage
from worker_crawl.errors import UnknownYearError
from worker_crawl.odata import DecisionListing, ODataConfig
from worker_crawl.service import process_crawl
from worker_crawl.tags import DecisionTag
from worker_crawl.years import YearSelection

DOCUMENT_URL_TEMPLATE = "https://example.org/default.aspx?id={document_id}&ptid="

ODATA_CONFIG = ODataConfig(
    base_url="https://example.org/odata/",
    api_key="test-key",
    web_id=1374643,
    document_url_template=DOCUMENT_URL_TEMPLATE,
    page_size=10,
    request_timeout=5,
    rate_limit_delay=0.0,
    max_retries=1,
)

TAGS_2025 = [
    DecisionTag(database_id=100104828, name="Överklagandenämndens beslut 2025")
]
SELECT_2025 = YearSelection(years=(2025,))


def _url(document_id: int) -> str:
    return DOCUMENT_URL_TEMPLATE.format(document_id=document_id)


def _listing(document_id: int, headline: str = "Beslut") -> DecisionListing:
    return DecisionListing(
        document_id=document_id,
        headline=headline,
        published_at=datetime(2025, 3, 4, tzinfo=timezone.utc),
    )


def _make_doc_read(
    source_url: str,
    source_document_id: int | None = None,
    source_decision_number: str | None = None,
) -> DocumentRead:
    now = datetime.now(tz=timezone.utc)
    return DocumentRead(
        id=uuid.uuid4(),
        source_url=source_url,
        source_document_id=source_document_id,
        source_decision_number=source_decision_number,
        source_headline=None,
        source_published_at=None,
        gcs_uri=None,
        raw_text=None,
        summary=None,
        case_number=None,
        decision_number=None,
        decision_date=None,
        decision_outcome=None,
        category=None,
        created_at=now,
        updated_at=now,
    )


def _make_task_read(document_id: uuid.UUID, step: str, status: str) -> TaskRead:
    return TaskRead(
        id=uuid.uuid4(),
        document_id=document_id,
        step=step,
        status=status,
        error_message=None,
        started_at=None,
        completed_at=None,
    )


def _make_source(
    listings: list[DecisionListing], tags: list[DecisionTag] | None = None
) -> MagicMock:
    source = MagicMock()
    source.fetch_decision_tags.return_value = TAGS_2025 if tags is None else tags
    source.fetch_decisions.return_value = listings
    source.decision_source_url = lambda _config, document_id: _url(document_id)
    return source


def _make_deps(
    listings: list[DecisionListing],
    existing_urls: set[str] | None = None,
    tags: list[DecisionTag] | None = None,
) -> tuple[dict, MagicMock, MagicMock, MagicMock]:
    existing_urls = existing_urls or set()

    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    doc_repo = MagicMock()
    task_repo = MagicMock()
    publisher = MagicMock()
    source = _make_source(listings, tags)

    async def get_by_source_url(_session, url: str) -> DocumentRead | None:
        return _make_doc_read(url) if url in existing_urls else None

    doc_repo.get_by_source_url = get_by_source_url

    # Stateful, so a second listing entry for a decision this run already stored
    # is found the same way it would be in Postgres.
    stored_by_decision_number: dict[str, DocumentRead] = {}

    async def get_by_source_decision_number(
        _session, decision_number: str
    ) -> DocumentRead | None:
        return stored_by_decision_number.get(decision_number)

    doc_repo.get_by_source_decision_number = get_by_source_decision_number

    async def create_doc(_session, dto):
        doc = _make_doc_read(
            dto.source_url, dto.source_document_id, dto.source_decision_number
        )
        if dto.source_decision_number is not None:
            stored_by_decision_number[dto.source_decision_number] = doc
        return doc

    doc_repo.create = create_doc

    async def create_task(_session, dto):
        return _make_task_read(dto.document_id, dto.step, dto.status)

    task_repo.create = create_task

    kwargs = dict(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        source=source,
        odata_config=ODATA_CONFIG,
        selection=SELECT_2025,
        topic=PipelineStep.DOWNLOAD,
    )
    return kwargs, session, publisher, source


@pytest.mark.asyncio
async def test_run_creates_documents_for_new_listings() -> None:
    kwargs, session, publisher, _ = _make_deps([_listing(1), _listing(2)])

    result = await process_crawl(**kwargs)

    assert result.total_found == 2
    assert result.new_documents == 2
    assert result.skipped == 0
    assert result.years_crawled == (2025,)
    assert result.tags_used == 1
    assert publisher.publish.call_count == 2
    assert session.commit.call_count == 2


@pytest.mark.asyncio
async def test_run_persists_listing_metadata() -> None:
    captured: list = []
    kwargs, _session, _publisher, _ = _make_deps([_listing(2953158, "Beslut 2025-21")])

    async def capture_create(_session, dto):
        captured.append(dto)
        return _make_doc_read(dto.source_url, dto.source_document_id)

    kwargs["document_repo"].create = capture_create

    await process_crawl(**kwargs)

    assert len(captured) == 1
    dto = captured[0]
    assert dto.source_document_id == 2953158
    assert dto.source_headline == "Beslut 2025-21"
    assert dto.source_published_at == datetime(2025, 3, 4, tzinfo=timezone.utc)
    assert dto.source_url == _url(2953158)


@pytest.mark.asyncio
async def test_run_skips_existing_documents() -> None:
    kwargs, _session, publisher, _ = _make_deps(
        [_listing(1), _listing(2)], existing_urls={_url(1)}
    )

    result = await process_crawl(**kwargs)

    assert (result.total_found, result.new_documents, result.skipped) == (2, 1, 1)
    assert publisher.publish.call_count == 1


@pytest.mark.asyncio
async def test_one_decision_published_under_two_ids_is_crawled_once() -> None:
    # The listing did exactly this for 21/2021 — ids 2265536 and 2266136, three
    # days apart, byte-identical text. Neither the URL nor the document id sees
    # it; the headline names the decision itself.
    headline = "Beslut 2021-21 Beslutsprövning"
    kwargs, _session, publisher, _ = _make_deps(
        [_listing(2265536, headline), _listing(2266136, headline)]
    )

    result = await process_crawl(**kwargs)

    assert (result.total_found, result.new_documents, result.skipped) == (2, 1, 1)
    assert publisher.publish.call_count == 1


@pytest.mark.asyncio
async def test_the_parsed_beslutsnummer_is_stored_as_the_dedup_key() -> None:
    captured: list = []
    kwargs, _session, _publisher, _ = _make_deps(
        [_listing(2953158, "Beslut 2025-21 Avvisning")]
    )

    async def capture_create(_session, dto):
        captured.append(dto)
        return _make_doc_read(dto.source_url, dto.source_document_id)

    kwargs["document_repo"].create = capture_create

    await process_crawl(**kwargs)

    assert captured[0].source_decision_number == "21/2025"


@pytest.mark.asyncio
async def test_an_unparsable_headline_is_still_crawled() -> None:
    # Nullable for exactly this: a headline the parser does not recognise must
    # not cost the decision its place in the corpus.
    captured: list = []
    kwargs, _session, publisher, _ = _make_deps([_listing(1, "Protokollsutdrag")])

    async def capture_create(_session, dto):
        captured.append(dto)
        return _make_doc_read(dto.source_url, dto.source_document_id)

    kwargs["document_repo"].create = capture_create

    result = await process_crawl(**kwargs)

    assert result.new_documents == 1
    assert captured[0].source_decision_number is None
    assert publisher.publish.call_count == 1


@pytest.mark.asyncio
async def test_two_unparsable_headlines_do_not_collide() -> None:
    # NULL is not a dedup key: Postgres permits repeated NULLs under UNIQUE, and
    # so must the lookup that precedes it.
    kwargs, _session, publisher, _ = _make_deps(
        [_listing(1, "Protokollsutdrag"), _listing(2, "Protokollsutdrag")]
    )

    result = await process_crawl(**kwargs)

    assert (result.new_documents, result.skipped) == (2, 0)
    assert publisher.publish.call_count == 2


@pytest.mark.asyncio
async def test_run_returns_empty_result_for_no_listings() -> None:
    kwargs, _session, publisher, _ = _make_deps([])

    result = await process_crawl(**kwargs)

    assert (result.total_found, result.new_documents, result.skipped) == (0, 0, 0)
    publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_run_publishes_correct_message() -> None:
    kwargs, _session, publisher, _ = _make_deps([_listing(7)])

    await process_crawl(**kwargs)

    topic, message = publisher.publish.call_args[0]
    assert topic == "download"
    assert isinstance(message, QueueMessage)
    assert message.document_id is not None
    assert message.task_id is not None


@pytest.mark.asyncio
async def test_run_selects_only_requested_year_tags() -> None:
    tags = [
        DecisionTag(database_id=100100768, name="Överklagandenämndens beslut 2024"),
        DecisionTag(database_id=100104828, name="Överklagandenämndens beslut 2025"),
    ]
    kwargs, _session, _publisher, source = _make_deps([], tags=tags)

    await process_crawl(**kwargs)

    _config, tag_ids = source.fetch_decisions.call_args[0]
    assert tuple(tag_ids) == (100104828,)


@pytest.mark.asyncio
async def test_run_raises_when_no_tag_matches_requested_year() -> None:
    kwargs, _session, _publisher, _ = _make_deps(
        [],
        tags=[DecisionTag(database_id=1, name="Överklagandenämndens beslut 2019")],
    )

    with pytest.raises(UnknownYearError):
        await process_crawl(**kwargs)


@pytest.mark.asyncio
async def test_run_commits_before_publish() -> None:
    committed_before_publish: list[int] = []
    commit_count = [0]

    session = MagicMock()

    async def track_commit():
        commit_count[0] += 1

    session.commit = track_commit
    session.rollback = AsyncMock()

    def track_publish(_topic, _message):
        committed_before_publish.append(commit_count[0])

    doc_repo = MagicMock()
    task_repo = MagicMock()
    publisher = MagicMock()
    publisher.publish.side_effect = track_publish
    doc_repo.get_by_source_url = AsyncMock(return_value=None)
    doc_repo.create = AsyncMock(return_value=_make_doc_read(_url(1), 1))
    task_repo.create = AsyncMock(
        side_effect=lambda _session, dto: _make_task_read(
            dto.document_id, dto.step, dto.status
        )
    )

    await process_crawl(
        session=session,
        document_repo=doc_repo,
        task_repo=task_repo,
        queue_publisher=publisher,
        source=_make_source([_listing(1)]),
        odata_config=ODATA_CONFIG,
        selection=SELECT_2025,
        topic=PipelineStep.DOWNLOAD,
    )

    assert committed_before_publish == [1], "commit must happen before publish"


@pytest.mark.asyncio
async def test_run_continues_after_per_document_failure() -> None:
    kwargs, _session, publisher, _ = _make_deps([_listing(1), _listing(2)])

    async def create_doc(_session, dto):
        if dto.source_document_id == 1:
            raise RuntimeError("network failure")
        return _make_doc_read(dto.source_url, dto.source_document_id)

    kwargs["document_repo"].create = create_doc

    result = await process_crawl(**kwargs)

    assert result.total_found == 2
    assert result.new_documents == 1
    assert publisher.publish.call_count == 1


@pytest.mark.asyncio
async def test_run_handles_integrity_error_as_duplicate() -> None:
    kwargs, session, publisher, _ = _make_deps([_listing(1)])
    kwargs["document_repo"].create = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("unique constraint"))
    )

    result = await process_crawl(**kwargs)

    assert (result.total_found, result.new_documents, result.skipped) == (1, 0, 1)
    session.rollback.assert_called_once()
    publisher.publish.assert_not_called()
