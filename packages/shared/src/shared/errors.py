"""Domain error types raised by the shared package.

Defined here (rather than raising bare ``ValueError``) so callers can catch the
specific failure at a system boundary without string-matching messages.
"""

__all__ = ["SharedError", "BackendConfigError", "QueueHandlerError"]


class SharedError(Exception):
    """Base class for every error raised by the shared package."""


class BackendConfigError(SharedError):
    """A storage or queue backend was requested that is not known/configured."""


class QueueHandlerError(SharedError):
    """A message was dispatched to a topic that has no registered handler."""
