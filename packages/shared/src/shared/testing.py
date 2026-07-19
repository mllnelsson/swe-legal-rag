"""Test-support helpers shared across the package integration suites.

Not imported by production code — only by `tests/**/conftest.py`.
"""

from __future__ import annotations

import inspect
from functools import partial
from types import ModuleType, SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["bind_repo"]


def bind_repo(module: ModuleType, session: AsyncSession) -> Any:
    """Bind `session` as the first argument of every public function in a repository
    module.

    The repositories in `shared.repositories` are modules of functions taking an
    `AsyncSession` first. Integration tests, however, are written against a
    session-bound repo (`document_repo.create(dto)`). This returns a namespace whose
    attributes are the module's public functions with `session` already applied, so the
    existing test call sites keep working without threading the session through by hand.
    """
    bound = SimpleNamespace()
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if fn.__module__ == module.__name__ and not name.startswith("_"):
            setattr(bound, name, partial(fn, session))
    return bound
