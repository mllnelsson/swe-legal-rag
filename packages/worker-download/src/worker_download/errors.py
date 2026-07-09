"""Domain error types for the download worker."""

__all__ = ["DownloadError"]


class DownloadError(Exception):
    """Raised when a PDF could not be fetched from its source URL."""
