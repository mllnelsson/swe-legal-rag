from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from ai.dtos import DateFilter, DecomposeResult
from api.services.query_planner import QueryPlan, plan_query


def _decompose_result(
    filters: DateFilter | None = None,
    categories: list[str] | None = None,
    entity_refs: list[str] | None = None,
    semantic_query: str = "test query",
) -> DecomposeResult:
    return DecomposeResult(
        filters=filters,
        categories=categories if categories is not None else [],
        entity_refs=entity_refs if entity_refs is not None else [],
        semantic_query=semantic_query,
    )


@pytest.mark.asyncio
async def test_plan_query_no_filters():
    result = _decompose_result(semantic_query="vad gäller för överklaganden")
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ):
        plan = await plan_query("vad gäller för överklaganden", [])

    assert isinstance(plan, QueryPlan)
    assert plan.semantic_query == "vad gäller för överklaganden"
    assert plan.filter.date_from is None
    assert plan.filter.date_to is None
    assert plan.filter.category is None
    assert plan.filter.entity_names == []


@pytest.mark.asyncio
async def test_plan_query_maps_date_filters():
    result = _decompose_result(
        filters=DateFilter(start=date(2022, 1, 1), end=date(2023, 12, 31)),
        semantic_query="kyrkorådet beslut",
    )
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ):
        plan = await plan_query("beslut från 2022 till 2023", [])

    assert plan.filter.date_from == date(2022, 1, 1)
    assert plan.filter.date_to == date(2023, 12, 31)


@pytest.mark.asyncio
async def test_plan_query_maps_first_category():
    result = _decompose_result(categories=["Kyrkogårdsförvaltning", "Ekonomi"])
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ):
        plan = await plan_query("kyrkogård", [])

    assert plan.filter.category == "Kyrkogårdsförvaltning"


@pytest.mark.asyncio
async def test_plan_query_empty_categories_gives_none_category():
    result = _decompose_result(categories=[])
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ):
        plan = await plan_query("generell fråga", [])

    assert plan.filter.category is None


@pytest.mark.asyncio
async def test_plan_query_maps_entity_refs():
    result = _decompose_result(entity_refs=["Skattkärrens församling", "kyrkorådet"])
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ):
        plan = await plan_query("vad beslutade skattkärren?", [])

    assert plan.filter.entity_names == ["Skattkärrens församling", "kyrkorådet"]


@pytest.mark.asyncio
async def test_plan_query_passes_history_to_decompose():
    result = _decompose_result()
    history = [{"role": "user", "content": "Tidigare fråga"}]
    with patch(
        "api.services.query_planner.ai.decompose_query",
        new=AsyncMock(return_value=result),
    ) as mock:
        await plan_query("Följdfråga", history)

    mock.assert_called_once_with("Följdfråga", history, provider=None)
