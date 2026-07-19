from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.config import RetrievalSettings
from api.services.answerer import (
    AnswerEvent,
    DoneEvent,
    SourceReference,
    SourcesEvent,
    TokenEvent,
    _build_sources,
    answer_query,
)
from api.services.retriever import RetrievedChunk


def _settings() -> RetrievalSettings:
    return RetrievalSettings(
        retrieval_top_k=4,
        retrieval_search_limit=10,
        retrieval_rerank_enabled=False,
    )


def _chunk(
    document_id: uuid.UUID | None = None,
    case_number: str = "2023/001",
    text: str = "Kyrkorådet beslutade att bifalla överklagandet.",
) -> RetrievedChunk:
    doc_id = document_id or uuid.uuid4()
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        chunk_text=text,
        chunk_index=0,
        case_number=case_number,
        decision_date=date(2023, 5, 1),
        decision_outcome="bifaller",
        category="Kyrkogård",
        gcs_uri=None,
        source_url="http://example.com/doc.pdf",
    )


class TestBuildSources:
    def test_single_chunk_produces_one_source(self):
        chunk = _chunk()
        sources = _build_sources([chunk], storage=None)
        assert len(sources) == 1
        assert isinstance(sources[0], SourceReference)
        assert sources[0].case_number == chunk.case_number

    def test_deduplicates_by_document(self):
        doc_id = uuid.uuid4()
        c1 = _chunk(document_id=doc_id, text="första stycket")
        c2 = _chunk(document_id=doc_id, text="andra stycket")
        sources = _build_sources([c1, c2], storage=None)
        assert len(sources) == 1
        assert sources[0].excerpt == "första stycket"[:200]

    def test_multiple_documents_give_multiple_sources(self):
        c1 = _chunk(document_id=uuid.uuid4())
        c2 = _chunk(document_id=uuid.uuid4())
        sources = _build_sources([c1, c2], storage=None)
        assert len(sources) == 2

    def test_excerpt_truncated_at_200_chars(self):
        long_text = "a" * 300
        chunk = _chunk(text=long_text)
        sources = _build_sources([chunk], storage=None)
        assert len(sources[0].excerpt) == 200

    def test_decision_date_serialized_as_string(self):
        chunk = _chunk()
        sources = _build_sources([chunk], storage=None)
        assert sources[0].decision_date == "2023-05-01"

    def test_no_storage_gives_none_pdf_url(self):
        chunk = _chunk()
        sources = _build_sources([chunk], storage=None)
        assert sources[0].pdf_url is None

    def test_storage_get_url_called_for_pdf(self):
        chunk = _chunk()
        storage = MagicMock()
        storage.get_url.return_value = "https://storage.example.com/signed"
        sources = _build_sources([chunk], storage=storage)
        assert sources[0].pdf_url == "https://storage.example.com/signed"
        storage.get_url.assert_called_once_with(
            f"documents/{chunk.document_id}/original.pdf"
        )

    def test_storage_error_gives_none_pdf_url(self):
        chunk = _chunk()
        storage = MagicMock()
        storage.get_url.side_effect = Exception("storage unavailable")
        sources = _build_sources([chunk], storage=storage)
        assert sources[0].pdf_url is None


class TestAnswerQuery:
    def _make_plan_mock(self):
        from api.services.query_planner import QueryPlan
        from shared.dtos.search import DocumentFilter

        plan = QueryPlan(semantic_query="kyrkorätt", filter=DocumentFilter())
        return AsyncMock(return_value=plan)

    def _make_retrieve_mock(self, chunks: list[RetrievedChunk]):
        return AsyncMock(return_value=chunks)

    @pytest.mark.asyncio
    async def test_yields_tokens_then_sources_then_done(self):
        chunk = _chunk()

        async def _fake_synthesize(*_args, **_kwargs):
            yield "Enligt "
            yield "beslut..."

        with (
            patch("api.services.answerer.plan_query", new=self._make_plan_mock()),
            patch(
                "api.services.answerer.retrieve", new=self._make_retrieve_mock([chunk])
            ),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
        ):
            events: list[AnswerEvent] = []
            async for event in answer_query(
                "Vad gäller?",
                [],
                MagicMock(),
                embedding_provider=MagicMock(),
                settings=_settings(),
            ):
                events.append(event)

        token_events = [e for e in events if isinstance(e, TokenEvent)]
        source_events = [e for e in events if isinstance(e, SourcesEvent)]
        done_events = [e for e in events if isinstance(e, DoneEvent)]

        assert len(token_events) == 2
        assert token_events[0].text == "Enligt "
        assert len(source_events) == 1
        assert len(done_events) == 1
        # order: tokens → sources → done
        assert events.index(source_events[0]) > events.index(token_events[-1])
        assert events.index(done_events[0]) == len(events) - 1

    @pytest.mark.asyncio
    async def test_sources_deduplicated_in_answer(self):
        doc_id = uuid.uuid4()
        c1 = _chunk(document_id=doc_id, text="chunk 1")
        c2 = _chunk(document_id=doc_id, text="chunk 2")

        async def _fake_synthesize(*_args, **_kwargs):
            yield "token"

        with (
            patch("api.services.answerer.plan_query", new=self._make_plan_mock()),
            patch(
                "api.services.answerer.retrieve", new=self._make_retrieve_mock([c1, c2])
            ),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
        ):
            events: list[AnswerEvent] = []
            async for event in answer_query(
                "Fråga",
                [],
                MagicMock(),
                embedding_provider=MagicMock(),
                settings=_settings(),
            ):
                events.append(event)

        source_events = [e for e in events if isinstance(e, SourcesEvent)]
        assert len(source_events[0].sources) == 1

    @pytest.mark.asyncio
    async def test_empty_chunks_gives_empty_sources(self):
        async def _fake_synthesize(*_args, **_kwargs):
            yield "Inga relevanta ärenden hittades."

        with (
            patch("api.services.answerer.plan_query", new=self._make_plan_mock()),
            patch("api.services.answerer.retrieve", new=self._make_retrieve_mock([])),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
        ):
            events: list[AnswerEvent] = []
            async for event in answer_query(
                "okänd fråga",
                [],
                MagicMock(),
                embedding_provider=MagicMock(),
                settings=_settings(),
            ):
                events.append(event)

        source_events = [e for e in events if isinstance(e, SourcesEvent)]
        assert source_events[0].sources == []

    @pytest.mark.asyncio
    async def test_history_passed_to_plan_query(self):
        history = [{"role": "user", "content": "Vad gäller?"}]

        async def _fake_synthesize(*_args, **_kwargs):
            yield "svar"

        plan_mock = self._make_plan_mock()
        with (
            patch("api.services.answerer.plan_query", new=plan_mock),
            patch("api.services.answerer.retrieve", new=self._make_retrieve_mock([])),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
        ):
            async for _ in answer_query(
                "Följdfråga",
                history,
                MagicMock(),
                embedding_provider=MagicMock(),
                settings=_settings(),
            ):
                pass

        plan_mock.assert_called_once_with("Följdfråga", history, llm_provider=None)

    @pytest.mark.asyncio
    async def test_append_turn_called_after_stream_with_chat_session_id(self):
        session_id = uuid.uuid4()

        async def _fake_synthesize(*_args, **_kwargs):
            yield "Enligt "
            yield "beslut..."

        db = MagicMock()

        with (
            patch("api.services.answerer.plan_query", new=self._make_plan_mock()),
            patch("api.services.answerer.retrieve", new=self._make_retrieve_mock([])),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
            patch("api.services.answerer.append_turn", new=AsyncMock()) as mock_append,
        ):
            async for _ in answer_query(
                "Vad gäller?",
                [],
                db,
                embedding_provider=MagicMock(),
                settings=_settings(),
                chat_session_id=session_id,
            ):
                pass

        mock_append.assert_called_once_with(
            session_id,
            "Vad gäller?",
            "Enligt beslut...",
            db,
        )

    @pytest.mark.asyncio
    async def test_append_turn_not_called_without_chat_session_id(self):
        async def _fake_synthesize(*_args, **_kwargs):
            yield "token"

        with (
            patch("api.services.answerer.plan_query", new=self._make_plan_mock()),
            patch("api.services.answerer.retrieve", new=self._make_retrieve_mock([])),
            patch("api.services.answerer.ai.synthesize_answer", _fake_synthesize),
            patch("api.services.answerer.append_turn", new=AsyncMock()) as mock_append,
        ):
            async for _ in answer_query(
                "Vad gäller?",
                [],
                MagicMock(),
                embedding_provider=MagicMock(),
                settings=_settings(),
            ):
                pass

        mock_append.assert_not_called()
