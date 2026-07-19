class CrawlError(Exception):
    """Base class for crawl worker failures."""


class ODataRequestError(CrawlError):
    """The Svenska kyrkan OData API could not be reached or returned an error."""


class ODataResponseError(CrawlError):
    """The OData API responded, but the payload did not match the expected shape."""


class YearSpecError(CrawlError):
    """CRAWL_YEARS (or --years) could not be parsed."""


class UnknownYearError(CrawlError):
    """No decision tag exists for any of the requested years."""
