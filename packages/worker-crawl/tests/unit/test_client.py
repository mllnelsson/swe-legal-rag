import pytest
import respx
import httpx

from worker_crawl.client import CrawlClient


@pytest.fixture
def client() -> CrawlClient:
    return CrawlClient(timeout=5)


@respx.mock
def test_fetch_pdf_urls_returns_absolute_urls(client: CrawlClient) -> None:
    html = """<html><body>
        <a href="doc1.pdf">Doc 1</a>
        <a href="/docs/doc2.pdf">Doc 2</a>
        <a href="https://other.com/doc3.PDF">Doc 3</a>
        <a href="not-a-pdf.html">Not a PDF</a>
    </body></html>"""
    respx.get("https://example.com/decisions").mock(return_value=httpx.Response(200, text=html))

    urls = client.fetch_pdf_urls("https://example.com/decisions")

    assert urls == [
        "https://example.com/doc1.pdf",
        "https://example.com/docs/doc2.pdf",
        "https://other.com/doc3.PDF",
    ]


@respx.mock
def test_fetch_pdf_urls_deduplicates(client: CrawlClient) -> None:
    html = """<html><body>
        <a href="doc.pdf">First</a>
        <a href="doc.pdf">Duplicate</a>
    </body></html>"""
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=html))

    urls = client.fetch_pdf_urls("https://example.com/")

    assert urls == ["https://example.com/doc.pdf"]


@respx.mock
def test_fetch_pdf_urls_empty_page(client: CrawlClient) -> None:
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))

    urls = client.fetch_pdf_urls("https://example.com/")

    assert urls == []


@respx.mock
def test_fetch_pdf_urls_skips_anchors_without_href(client: CrawlClient) -> None:
    html = """<html><body>
        <a name="anchor">No href</a>
        <a href="doc.pdf">Has href</a>
    </body></html>"""
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=html))

    urls = client.fetch_pdf_urls("https://example.com/")

    assert urls == ["https://example.com/doc.pdf"]


@respx.mock
def test_fetch_pdf_urls_raises_on_http_error(client: CrawlClient) -> None:
    respx.get("https://example.com/").mock(return_value=httpx.Response(404))

    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_pdf_urls("https://example.com/")
