from datetime import datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from worker_crawl.errors import ODataRequestError, ODataResponseError
from worker_crawl.odata import (
    ODataConfig,
    decision_source_url,
    fetch_decision_tags,
    fetch_decisions,
)

BASE_URL = "https://example.org/odata/"
DOCUMENTS_URL = f"{BASE_URL}documents/"
TAGS_URL = f"{BASE_URL}tags/"

CONFIG = ODataConfig(
    base_url=BASE_URL,
    api_key="test-key",
    web_id=1374643,
    document_url_template="https://example.org/default.aspx?id={document_id}&ptid=",
    page_size=2,
    request_timeout=5,
    rate_limit_delay=0.0,
    max_retries=3,
)


def _document(document_id: int) -> dict:
    return {
        "documentId": document_id,
        "headline": f"Beslut {document_id}",
        "publishDate": "2025-10-29T08:53:09+01:00",
    }


def _page(rows: list[dict], count: int) -> httpx.Response:
    return httpx.Response(200, json={"@odata.count": count, "value": rows})


def _query_of(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(request.url)).query)


def test_decision_source_url_is_keyed_on_document_id() -> None:
    assert (
        decision_source_url(CONFIG, 2953158)
        == "https://example.org/default.aspx?id=2953158&ptid="
    )


@respx.mock
def test_fetch_decision_tags_parses_rows() -> None:
    route = respx.get(TAGS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "databaseId": 100104828,
                        "name": "Överklagandenämndens beslut 2025",
                    }
                ]
            },
        )
    )

    tags = fetch_decision_tags(CONFIG)

    assert [(tag.database_id, tag.name) for tag in tags] == [
        (100104828, "Överklagandenämndens beslut 2025")
    ]
    query = _query_of(route.calls[0].request)
    assert query["apikey"] == ["test-key"]
    assert query["$filter"] == ["startswith(name,'Överklagandenämndens beslut')"]


@respx.mock
def test_fetch_decisions_sends_the_mandatory_tag_filter() -> None:
    route = respx.get(DOCUMENTS_URL).mock(return_value=_page([], 0))

    fetch_decisions(CONFIG, [100104828, 760887])

    sent_filter = _query_of(route.calls[0].request)["$filter"][0]
    # Without tags/any(...) the listing returns every binary file on the web, not just
    # decisions -- so this clause must always be present.
    assert "tags/any(t: t/databaseId in (100104828,760887))" in sent_filter
    assert "published eq true" in sent_filter
    assert "sqlDocumentType in('F')" in sent_filter
    assert "webId in (1374643)" in sent_filter


@respx.mock
def test_fetch_decisions_pages_until_count_is_reached() -> None:
    route = respx.get(DOCUMENTS_URL).mock(
        side_effect=[
            _page([_document(1), _document(2)], 5),
            _page([_document(3), _document(4)], 5),
            _page([_document(5)], 5),
        ]
    )

    listings = fetch_decisions(CONFIG, [1])

    assert [listing.document_id for listing in listings] == [1, 2, 3, 4, 5]
    assert route.call_count == 3
    skips = [_query_of(call.request)["$skip"][0] for call in route.calls]
    assert skips == ["0", "2", "4"]


@respx.mock
def test_fetch_decisions_collapses_rows_repeated_across_pages() -> None:
    # publishdate is not unique, so the same row can appear on two pages.
    respx.get(DOCUMENTS_URL).mock(
        side_effect=[
            _page([_document(1), _document(2)], 4),
            _page([_document(2), _document(3)], 4),
        ]
    )

    listings = fetch_decisions(CONFIG, [1])

    assert [listing.document_id for listing in listings] == [1, 2, 3]


@respx.mock
def test_fetch_decisions_stops_on_an_empty_page() -> None:
    route = respx.get(DOCUMENTS_URL).mock(
        side_effect=[_page([_document(1)], 99), _page([], 99)]
    )

    listings = fetch_decisions(CONFIG, [1])

    assert len(listings) == 1
    assert route.call_count == 2


def test_fetch_decisions_without_tags_makes_no_request() -> None:
    with respx.mock:
        route = respx.get(DOCUMENTS_URL)
        assert fetch_decisions(CONFIG, []) == []
        assert route.call_count == 0


@respx.mock
def test_listing_parses_headline_and_publish_date() -> None:
    respx.get(DOCUMENTS_URL).mock(return_value=_page([_document(2953158)], 1))

    listing = fetch_decisions(CONFIG, [1])[0]

    assert listing.headline == "Beslut 2953158"
    assert listing.published_at == datetime.fromisoformat("2025-10-29T08:53:09+01:00")


@respx.mock
def test_listing_tolerates_missing_headline_and_date() -> None:
    respx.get(DOCUMENTS_URL).mock(
        return_value=_page(
            [{"documentId": 42, "headline": None, "publishDate": None}], 1
        )
    )

    listing = fetch_decisions(CONFIG, [1])[0]

    assert listing.document_id == 42
    assert listing.headline == ""
    assert listing.published_at is None


@respx.mock
def test_row_without_document_id_is_rejected() -> None:
    respx.get(DOCUMENTS_URL).mock(return_value=_page([{"headline": "orphan"}], 1))

    with pytest.raises(ODataResponseError):
        fetch_decisions(CONFIG, [1])


@respx.mock
def test_server_errors_are_retried_then_succeed() -> None:
    route = respx.get(DOCUMENTS_URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            _page([_document(1)], 1),
        ]
    )

    with patch("worker_crawl.odata.time.sleep") as sleep:
        listings = fetch_decisions(CONFIG, [1])

    assert len(listings) == 1
    assert route.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


@respx.mock
def test_client_errors_are_not_retried() -> None:
    route = respx.get(DOCUMENTS_URL).mock(return_value=httpx.Response(403))

    with pytest.raises(ODataRequestError, match="403"):
        fetch_decisions(CONFIG, [1])

    assert route.call_count == 1


@respx.mock
def test_exhausted_retries_raise() -> None:
    respx.get(DOCUMENTS_URL).mock(return_value=httpx.Response(500))

    with patch("worker_crawl.odata.time.sleep"), pytest.raises(ODataRequestError):
        fetch_decisions(CONFIG, [1])


@respx.mock
def test_non_json_payload_is_rejected() -> None:
    respx.get(DOCUMENTS_URL).mock(return_value=httpx.Response(200, text="<html/>"))

    with pytest.raises(ODataResponseError):
        fetch_decisions(CONFIG, [1])


@respx.mock
def test_payload_without_value_array_is_rejected() -> None:
    respx.get(DOCUMENTS_URL).mock(return_value=httpx.Response(200, json={"odd": True}))

    with pytest.raises(ODataResponseError):
        fetch_decisions(CONFIG, [1])
