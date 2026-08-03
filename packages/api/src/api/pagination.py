from pydantic import BaseModel


class Page[T](BaseModel):
    """One slice of a larger result set.

    ``total`` counts everything matching the request, not the items returned, so
    a client can tell "these are all of them" from "there is more".
    """

    items: list[T]
    total: int
    limit: int
    offset: int


def clamp_limit(requested: int | None, *, default: int, maximum: int) -> int:
    """Keep a caller-supplied page size inside what the server will serve."""
    if requested is None:
        return default
    return max(1, min(requested, maximum))
