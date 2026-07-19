"""Svenska kyrkan OData v4 client for the Överklagandenämnden decision listing.

The site's decision page is a JS search UI over an ASP.NET OData v4 endpoint
(`$metadata` reports `edmx Version="4.0"`, namespace
`SvenskaKyrkan.Contracts.V2.ExtensionsDb.Models`), so there are no PDF anchors to scrape.

The `tags/any(...)` clause in the document filter is **mandatory**. Dropping it does not
widen the result to "all decisions" -- it widens it to every binary file on webId 1374643
(~5039 rows of posters, ad creatives, protocols and annual reports). With the decision
tags applied the corpus is ~1073 documents.

I/O only; tag parsing and selection live in `tags`.
"""

import logging
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from worker_crawl.errors import ODataRequestError, ODataResponseError
from worker_crawl.tags import DECISION_TAG_PREFIX, DecisionTag

logger = logging.getLogger(__name__)

_USER_AGENT: Final = "church-legal-db-crawler/0.2"

# Decisions are CMS "file" documents on the Svenska kyrkan web.
SQL_DOCUMENT_TYPE_FILE: Final = "F"

# Retry only 5xx: a 4xx means the request itself was rejected and a retry cannot help.
HTTP_SERVER_ERROR: Final = 500
BACKOFF_BASE_SECONDS: Final = 2
MIN_ATTEMPTS: Final = 1

# Stop paging even if @odata.count disagrees with what the server actually returns, so a
# count bug upstream cannot spin this loop forever.
MAX_PAGES: Final = 500

# Tags are few (29 today); one page is enough.
TAG_PAGE_SIZE: Final = 500

_ODATA_COUNT: Final = "@odata.count"
_ODATA_VALUE: Final = "value"


class ODataConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str
    api_key: str
    web_id: int
    document_url_template: str
    page_size: int
    request_timeout: int
    rate_limit_delay: float
    max_retries: int


class DecisionListing(BaseModel):
    """One decision as described by the listing, before the PDF is fetched."""

    model_config = ConfigDict(frozen=True)

    document_id: int
    # Optional so one listing row with a blank headline or date cannot abort a whole
    # backfill; only the document id is load-bearing (it forms the download URL).
    headline: str = ""
    published_at: datetime | None = None


def decision_source_url(config: ODataConfig, document_id: int) -> str:
    """Canonical, stable URL for a decision PDF.

    Keyed on the CMS document id rather than the filename, so it does not change when a
    document is renamed. It 302-redirects to the real `/filer/...pdf` path, which is why
    the download worker must follow redirects.
    """
    return config.document_url_template.format(document_id=document_id)


def fetch_decision_tags(config: ODataConfig) -> list[DecisionTag]:
    payload = _get_json(
        config,
        "tags",
        {
            "$select": "databaseId,name",
            "$top": TAG_PAGE_SIZE,
            "$filter": f"startswith(name,{_quote(DECISION_TAG_PREFIX)})",
        },
    )
    return [_to_tag(row) for row in _rows(payload)]


def fetch_decisions(
    config: ODataConfig, tag_ids: Sequence[int]
) -> list[DecisionListing]:
    """Page through every decision carrying one of `tag_ids`.

    Results are de-duplicated by document id: `$orderBy` is on `publishdate`, which is not
    unique, so a row can repeat across page boundaries.
    """
    if not tag_ids:
        return []

    listings: dict[int, DecisionListing] = {}
    filter_expression = _build_decision_filter(config.web_id, tag_ids)
    total: int | None = None

    for page in range(MAX_PAGES):
        skip = page * config.page_size
        if total is not None and skip >= total:
            break
        if page > 0 and config.rate_limit_delay > 0:
            time.sleep(config.rate_limit_delay)

        payload = _get_json(
            config,
            "documents",
            {
                "$count": "true",
                "$select": "documentId,headline,publishDate",
                "$skip": skip,
                "$top": config.page_size,
                "$orderBy": "publishdate desc",
                "$filter": filter_expression,
            },
        )
        if total is None:
            total = _total_count(payload)

        rows = _rows(payload)
        if not rows:
            break
        for row in rows:
            listing = _to_listing(row)
            listings[listing.document_id] = listing
    else:
        logger.warning(
            "Stopped paging decisions at the %d-page cap; results may be incomplete.",
            MAX_PAGES,
        )

    if total is not None and len(listings) < total:
        logger.warning(
            "Listing reported %d decisions but only %d were collected.",
            total,
            len(listings),
        )
    return list(listings.values())


def _build_decision_filter(web_id: int, tag_ids: Sequence[int]) -> str:
    ids = ",".join(str(tag_id) for tag_id in tag_ids)
    return (
        f"published eq true "
        f"and sqlDocumentType in('{SQL_DOCUMENT_TYPE_FILE}') "
        f"and webId in ({web_id}) "
        f"and tags/any(t: t/databaseId in ({ids}))"
    )


def _get_json(
    config: ODataConfig, resource: str, params: dict[str, Any]
) -> dict[str, Any]:
    url = f"{config.base_url.rstrip('/')}/{resource}/"
    query = {"apikey": config.api_key, **params}
    last_error: Exception = ODataRequestError(f"No attempts made for {url}")

    with httpx.Client(
        timeout=config.request_timeout,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    ) as client:
        for attempt in range(max(MIN_ATTEMPTS, config.max_retries)):
            try:
                response = client.get(url, params=query)
                response.raise_for_status()
                return _decode(response, url)
            except httpx.HTTPStatusError as error:
                if error.response.status_code < HTTP_SERVER_ERROR:
                    raise ODataRequestError(
                        f"{resource} request rejected with "
                        f"{error.response.status_code}: {url}"
                    ) from error
                last_error = error
            except (httpx.ConnectError, httpx.TimeoutException) as error:
                last_error = error
            if attempt < config.max_retries - 1:
                time.sleep(BACKOFF_BASE_SECONDS**attempt)

    raise ODataRequestError(f"{resource} request failed: {url}") from last_error


def _decode(response: httpx.Response, url: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise ODataResponseError(f"Response from {url} was not JSON.") from error
    if not isinstance(payload, dict):
        raise ODataResponseError(f"Response from {url} was not a JSON object.")
    return payload


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get(_ODATA_VALUE)
    if not isinstance(rows, list):
        raise ODataResponseError(f"Payload has no {_ODATA_VALUE!r} array.")
    return rows


def _total_count(payload: dict[str, Any]) -> int | None:
    count = payload.get(_ODATA_COUNT)
    return count if isinstance(count, int) else None


def _to_tag(row: dict[str, Any]) -> DecisionTag:
    try:
        return DecisionTag(database_id=row["databaseId"], name=row["name"])
    except (KeyError, ValidationError) as error:
        raise ODataResponseError(f"Malformed tag row: {row!r}") from error


def _to_listing(row: dict[str, Any]) -> DecisionListing:
    try:
        return DecisionListing(
            document_id=row["documentId"],
            headline=row.get("headline") or "",
            published_at=row.get("publishDate"),
        )
    except (KeyError, ValidationError) as error:
        raise ODataResponseError(f"Malformed document row: {row!r}") from error


def _quote(value: str) -> str:
    """Render a string literal for an OData filter (single quotes are doubled)."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"
