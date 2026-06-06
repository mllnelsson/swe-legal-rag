import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = "church-legal-db-crawler/0.1"

logger = logging.getLogger(__name__)


class CrawlClient:
    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    def fetch_pdf_urls(self, source_url: str) -> list[str]:
        with httpx.Client(timeout=self._timeout) as http:
            response = http.get(source_url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        urls: list[str] = []
        for tag in soup.find_all("a"):
            href = tag.get("href")
            if not href:
                continue
            if not str(href).lower().endswith(".pdf"):
                continue
            try:
                urls.append(urljoin(source_url, str(href)))
            except Exception:
                logger.warning("Skipping malformed URL: %s", href)

        return list(dict.fromkeys(urls))
