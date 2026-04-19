"""End-to-end: catalog HTTP_API record → binding → bound callable → HTTP."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from gclaw.tools.catalog.binding import ToolBindingService
from gclaw.tools.catalog.models import (
    ApiKeyAuth,
    BearerAuth,
    HttpApiConfig,
    NoAuth,
)
from gclaw.tools.catalog.service import ToolCatalogService
from gclaw.tools.catalog.tester import probe_tool, set_openapi_deps
from tests._tool_catalog_fakes import FakeToolRepo

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def _spec() -> dict:
    with open(FIXTURE) as f:
        return yaml.safe_load(f)


@pytest.fixture(autouse=True)
def _reset_deps():
    set_openapi_deps(None, None)
    yield
    set_openapi_deps(None, None)


@pytest.fixture
def service():
    return ToolCatalogService(tool_repo=FakeToolRepo())


def test_binding_materializes_tool_per_operation(service):
    rec = service.create_tool(
        name="petstore",
        config=HttpApiConfig(
            spec_inline=_spec(),
            base_url="https://petstore.example.com/v2",
            auth=NoAuth(),
            allowed_operations=["getPetById", "findPetsByStatus"],
        ),
    )
    binding = ToolBindingService(
        catalog_service=service,
        secret_resolver=lambda _ref: None,
    )
    tools = binding.resolve_catalog_tools([rec.id])
    names = [t.__name__ for t in tools]
    assert set(names) == {"getPetById", "findPetsByStatus"}


@pytest.mark.asyncio
async def test_binding_calls_real_http_through_mock_transport(service):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": 42, "name": "fido"})

    rec = service.create_tool(
        name="petstore",
        config=HttpApiConfig(
            spec_inline=_spec(),
            base_url="https://petstore.example.com/v2",
            auth=BearerAuth(credential_ref="sm/path"),
            allowed_operations=["getPetById"],
        ),
    )
    transport = httpx.MockTransport(handler)
    binding = ToolBindingService(
        catalog_service=service,
        secret_resolver=lambda _ref: "tok",
        http_transport=transport,
    )
    tools = binding.resolve_catalog_tools([rec.id])
    assert len(tools) == 1
    out = await tools[0](petId=42)
    assert captured["url"].endswith("/pets/42")
    assert captured["auth"] == "Bearer tok"
    assert "fido" in out


@pytest.mark.asyncio
async def test_tester_http_api_branch_lists_operations(service):
    """Phase 5 probe: the test endpoint should fetch/parse the spec
    and return the first-N operation IDs."""
    set_openapi_deps(secret_resolver=lambda _ref: None, http_transport=None)

    rec = service.create_tool(
        name="petstore",
        config=HttpApiConfig(
            spec_inline=_spec(),
            base_url="https://x",
            auth=NoAuth(),
        ),
    )
    result = await probe_tool(rec)
    assert result["ok"] is True
    assert result["error"] is None
    ops = result["sample_response"]["operations"]
    assert "getPetById" in ops


@pytest.mark.asyncio
async def test_tester_http_api_without_deps_is_stub(service):
    # No openapi deps wired → Phase-2 stub shape with phase note.
    rec = service.create_tool(
        name="petstore",
        config=HttpApiConfig(
            spec_inline=_spec(),
            base_url="https://x",
            auth=NoAuth(),
        ),
    )
    result = await probe_tool(rec)
    assert result["ok"] is False
    assert "phase" in result["error"].lower()
