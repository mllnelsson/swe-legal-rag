"""File-based LLM tracing for this project — a thin wrapper over `agent_kit`.

The recorder, the JSON contract and the path layout now live in
`agent_kit.tracing`, which is domain-free and knows nothing about this project's
storage layout. The one project-specific fact is *where* traces go: under
`StorageSettings().local_storage_path`, so they sit beside the rest of the
local data and move with `STORAGE_BACKEND`/`LOCAL_STORAGE_PATH`.

This module supplies that root and re-exports the pieces callers already import
from `ai`, so `ai.install_file_tracing()` stays a no-argument call at every
composition root and traces land at the identical
`{LOCAL_STORAGE_PATH}/{LLM_TRACE_KEY_PREFIX}/{date}/{interaction_id}/...` path.

See [Observability](/observability.md) for the record schema and the wiring
invariant every process must follow.
"""

from __future__ import annotations

from pathlib import Path

from shared.config import StorageSettings

from agent_kit.tracing import (
    TRACE_SCHEMA_VERSION,
    FileTraceRecorder,
    LLMTraceConfig,
    relative_path_for,
    serialize_record,
)
from agent_kit.tracing import (
    install_file_tracing as _install_file_tracing,
)

__all__ = [
    "TRACE_SCHEMA_VERSION",
    "FileTraceRecorder",
    "LLMTraceConfig",
    "relative_path_for",
    "serialize_record",
    "install_file_tracing",
]


def install_file_tracing(
    root: Path | None = None, config: LLMTraceConfig | None = None
) -> FileTraceRecorder | None:
    """Install file tracing rooted under this project's local storage path.

    Idempotent and never raises — see `agent_kit.tracing.install_file_tracing`.
    When `root` is omitted it is computed as
    `StorageSettings().local_storage_path / config.directory_name`, which is the
    exact layout every reader and the pricing analysis already expect.
    """
    settings = config or LLMTraceConfig()
    resolved = root or (StorageSettings().local_storage_path / settings.directory_name)
    return _install_file_tracing(root=resolved, config=settings)
