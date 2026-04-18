"""Tests for the builtin-tool seeder — idempotent upsert into the catalog."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.builtin_registry import (
    clear_registry_for_tests,
    tool_export,
)
from gclaw.tools.catalog.models import ToolKind
from gclaw.tools.catalog.seeder import seed_builtin_tools
from gclaw.tools.catalog.service import ToolCatalogService
from tests._tool_catalog_fakes import FakeToolRepo


@pytest.fixture(autouse=True)
def _reset():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


@pytest.fixture
def service():
    return ToolCatalogService(tool_repo=FakeToolRepo())


def _make_two_registered_tools():
    @tool_export(description="search the web")
    def web_search(query: str) -> str:
        return query

    @tool_export(description="fetch a url")
    def fetch_url(url: str) -> str:
        return url


def test_seeder_creates_one_row_per_registered(service):
    _make_two_registered_tools()
    stats = seed_builtin_tools(service)
    assert stats["created"] == 2
    assert stats["existing"] == 0
    assert len(service.list_tools()) == 2

    # Both are BUILTIN kind pointing at the function paths we registered.
    kinds = {t.kind for t in service.list_tools()}
    assert kinds == {ToolKind.BUILTIN}


def test_seeder_is_idempotent(service):
    _make_two_registered_tools()
    seed_builtin_tools(service)
    # Second run must not create duplicates.
    stats = seed_builtin_tools(service)
    assert stats["created"] == 0
    assert stats["existing"] == 2
    assert len(service.list_tools()) == 2


def test_seeder_preserves_user_overrides(service):
    """If the user disabled a seeded tool, reseeding must not re-enable it."""
    _make_two_registered_tools()
    seed_builtin_tools(service)
    # User disables one:
    tool = next(t for t in service.list_tools() if t.name == "web_search")
    service.update_tool(tool.id, enabled=False)

    seed_builtin_tools(service)
    restored = service.get_tool(tool.id)
    assert restored.enabled is False  # user intent wins over reseed


def test_seeder_creates_only_new_on_registry_growth(service):
    @tool_export()
    def first():
        return None

    seed_builtin_tools(service)
    assert len(service.list_tools()) == 1

    @tool_export()
    def second():
        return None

    stats = seed_builtin_tools(service)
    assert stats["created"] == 1
    assert stats["existing"] == 1
    assert len(service.list_tools()) == 2
