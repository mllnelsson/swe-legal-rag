"""Structural interface for the decision source injected into the crawl service.

Mirrors the repo-namespace convention in `shared.repositories._protocols`: members are
read-only `@property` returning a `Callable` so a *module* of functions (here
`worker_crawl.odata`) satisfies the Protocol structurally. See that module's docstring for
why the property form is required by ty.
"""

from collections.abc import Callable, Sequence
from typing import Protocol

from worker_crawl.odata import DecisionListing, ODataConfig
from worker_crawl.tags import DecisionTag


class DecisionSource(Protocol):
    @property
    def fetch_decision_tags(
        self,
    ) -> Callable[[ODataConfig], list[DecisionTag]]: ...
    @property
    def fetch_decisions(
        self,
    ) -> Callable[[ODataConfig, Sequence[int]], list[DecisionListing]]: ...
    @property
    def decision_source_url(self) -> Callable[[ODataConfig, int], str]: ...
