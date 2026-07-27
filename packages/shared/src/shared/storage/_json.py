"""Shared JSON record serialization for append-style storage streams.

Both backends serialize through `dumps_record` so the bytes on disk and the
bytes in an object store cannot drift apart. A record written locally and the
same record written to GCS are byte-identical.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

# UTF-8 without escaping: every prompt in this project is Swedish, and
# \uXXXX-escaping them triples the size of a trace file for no benefit.
_JSON_ENSURE_ASCII = False

# Compact separators — these are machine-read streams, not documents.
_JSON_SEPARATORS = (",", ":")


def _coerce_unserializable(value: object) -> str:
    """Last-resort encoder for values `json` cannot represent.

    Trace records carry a caller-supplied context mapping whose values are
    opaque to the storage layer. Coercing an odd value to its string form is
    always better than dropping the whole record.
    """
    return str(value)


def dumps_record(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record,
        ensure_ascii=_JSON_ENSURE_ASCII,
        separators=_JSON_SEPARATORS,
        default=_coerce_unserializable,
    ).encode("utf-8")


def loads_record(data: bytes | str) -> Mapping[str, Any]:
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed
