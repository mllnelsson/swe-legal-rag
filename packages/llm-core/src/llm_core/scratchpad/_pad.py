"""A keyed working-memory an agent's tools write and its writer reads.

One `Scratchpad` is the single place a turn's gathered evidence lives. A tool
stores a full value under a stable key and hands the model back a `Handle` — the
key and a small *preview* — while the heavy value stays in the pad. Two things
then read the pad: the tool loop, which renders every preview into an
always-present *board* so the model sees what has been gathered so far without
re-reading it; and the writer (and any tool that needs an earlier value), which
`recall`s the full value by key.

The pad is domain-free. It is generic over the value type, so a host keeps its
records typed, and it serializes through a host-supplied value codec so those
typed values survive a round-trip to a store and back — the pad itself never
needs to know what a value is. Single-run and not thread-safe: one is created
per turn and the executors close over it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

# A preview must survive a round-trip through JSON: it is both returned to the
# model and folded into the persisted carry-over. Same contract as a context
# blob's values.
Preview = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Handle:
    """What a tool hands the model in place of a stored value.

    `key` addresses the full value in the pad; `preview` is the small,
    model-facing shorthand — enough to pick the next tool (a case number, a
    snippet), never the payload. The two are kept apart so a host names the key
    field whatever its prompt expects (`chunk_id`, `document_id`, ...).
    """

    key: str
    preview: Preview

    def as_dict(self, *, key_field: str = "key") -> dict[str, Any]:
        """`{key_field: key, **preview}` — the common flat render for a tool result."""
        return {key_field: self.key, **self.preview}


@dataclass(slots=True)
class _Entry[V]:
    value: V
    # `None` marks a small "K=V" entry: it has no separate heavy payload, so the
    # board and digest render the value itself. Such a value must be JSON-safe.
    preview: Preview | None


class Scratchpad[V]:
    """A keyed store an agent's tools write and its writer reads.

    Generic over the value type. Insertion order is preserved and stable, so the
    board and the digest read the same way every pass; re-`remember`ing an
    existing key overwrites in place and keeps that key's original position.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _Entry[V]] = {}

    def remember(self, key: str, value: V, *, preview: Preview | None = None) -> Handle:
        """Store `value` under `key`; return the `Handle` the tool gives the model.

        `preview` is the model-facing shorthand. Pass `None` for a small entry
        whose value *is* its own summary (a flag, a short list) — the value then
        renders directly on the board, and must be JSON-safe.
        """
        self._entries[key] = _Entry(value=value, preview=preview)
        return Handle(key=key, preview=self._preview_of(key))

    def recall(self, key: str) -> V:
        """The full value under `key`. Raises `KeyError` if absent."""
        return self._entries[key].value

    def get(self, key: str, default: V | None = None) -> V | None:
        entry = self._entries.get(key)
        return entry.value if entry is not None else default

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self) -> list[str]:
        """Every key, in insertion order."""
        return list(self._entries)

    def entries(self) -> Iterator[tuple[str, V]]:
        """`(key, value)` for every entry, in insertion order."""
        for key, entry in self._entries.items():
            yield key, entry.value

    def preview_of(self, key: str) -> Preview:
        """The model-facing preview for `key` (the value itself for a K=V entry)."""
        return self._preview_of(key)

    def _preview_of(self, key: str) -> Preview:
        entry = self._entries[key]
        if entry.preview is not None:
            return entry.preview
        # A K=V entry: the value is its own preview. Wrap a bare scalar/list so
        # the digest stays a dict-of-dicts.
        value = entry.value
        return value if isinstance(value, dict) else {"value": value}

    def digest(self) -> dict[str, Preview]:
        """`{key: preview}` for every entry, in insertion order.

        The JSON-safe shorthand of what the turn holds — what the board renders
        and what a planner is shown of an earlier turn.
        """
        return {key: self._preview_of(key) for key in self._entries}

    def render_board(self) -> str:
        """The dense text block the tool loop pins into the model's context.

        Empty string when the pad is empty, so a caller can skip injecting a
        board with nothing on it.
        """
        return "\n".join(
            f"{key}  {json.dumps(preview, ensure_ascii=False, sort_keys=True)}"
            for key, preview in self.digest().items()
        )

    def dump(
        self, encode: Callable[[str, V], Any], *, cap: int | None = None
    ) -> dict[str, Any]:
        """Serialize to a JSON-safe blob via the host's value `encode`.

        `cap`, when set, bounds the blob: every K=V entry is kept (it is small and
        cheap to carry), and only the most recent `cap` previewed (heavy) entries
        survive — older heavy entries are dropped, newest-wins, so a long-running
        conversation cannot grow the store without bound.
        """
        kept = self._capped_keys(cap)
        return {
            "entries": [
                {
                    "key": key,
                    "preview": self._entries[key].preview,
                    "value": encode(key, self._entries[key].value),
                }
                for key in kept
            ]
        }

    def _capped_keys(self, cap: int | None) -> list[str]:
        keys = list(self._entries)
        if cap is None:
            return keys
        heavy = [k for k in keys if self._entries[k].preview is not None]
        if len(heavy) <= cap:
            return keys
        dropped = set(heavy[: len(heavy) - cap])
        return [k for k in keys if k not in dropped]

    def restore(self, blob: dict[str, Any], decode: Callable[[str, Any], V]) -> None:
        """Replace this pad's contents with a `dump`ed blob's, via `decode`.

        In-place, so the pad the executors already closed over carries an earlier
        turn's entries into this one. A missing or empty blob clears the pad — a
        first turn simply starts fresh.
        """
        self._entries = {
            raw["key"]: _Entry(
                value=decode(raw["key"], raw["value"]), preview=raw.get("preview")
            )
            for raw in (blob or {}).get("entries", [])
        }

    @classmethod
    def load(
        cls, blob: dict[str, Any], decode: Callable[[str, Any], V]
    ) -> Scratchpad[V]:
        """A fresh pad reconstructed from `dump`'s blob via the host's `decode`.

        A missing or malformed blob yields an empty pad rather than raising, so a
        first turn (or a store that lost the key) simply starts fresh.
        """
        pad: Scratchpad[V] = cls()
        pad.restore(blob, decode)
        return pad
