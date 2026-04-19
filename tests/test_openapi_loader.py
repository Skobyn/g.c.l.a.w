"""Tests for OpenAPI spec loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from gclaw.tools.catalog.models import HttpApiConfig, NoAuth
from gclaw.tools.openapi_mcp.loader import load_spec

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _inline_spec() -> dict:
    import yaml
    with open(FIXTURE_DIR / "sample_openapi.yaml") as f:
        return yaml.safe_load(f)


def test_load_spec_from_inline_returns_operations():
    cfg = HttpApiConfig(
        spec_inline=_inline_spec(),
        base_url="https://petstore.example.com/v2",
        auth=NoAuth(),
    )
    ops = load_spec(cfg)
    ids = {op.operation_id for op in ops}
    # deletePet is deprecated and should be skipped by default
    assert ids == {"findPetsByStatus", "addPet", "getPetById"}


def test_load_spec_includes_method_and_path():
    cfg = HttpApiConfig(
        spec_inline=_inline_spec(),
        base_url="https://x",
        auth=NoAuth(),
    )
    ops = load_spec(cfg)
    by_id = {op.operation_id: op for op in ops}
    assert by_id["getPetById"].method == "GET"
    assert by_id["getPetById"].path == "/pets/{petId}"
    assert by_id["addPet"].method == "POST"
    assert by_id["addPet"].path == "/pets"


def test_load_spec_captures_parameters():
    cfg = HttpApiConfig(
        spec_inline=_inline_spec(),
        base_url="https://x",
        auth=NoAuth(),
    )
    ops = {op.operation_id: op for op in load_spec(cfg)}
    params = ops["getPetById"].parameters
    assert len(params) == 1
    assert params[0].name == "petId"
    assert params[0].location == "path"
    assert params[0].required is True


def test_load_spec_captures_request_body():
    cfg = HttpApiConfig(
        spec_inline=_inline_spec(),
        base_url="https://x",
        auth=NoAuth(),
    )
    ops = {op.operation_id: op for op in load_spec(cfg)}
    assert ops["addPet"].request_body is not None
    assert ops["addPet"].request_body["required"] is True


def test_load_spec_allowed_operations_filters():
    cfg = HttpApiConfig(
        spec_inline=_inline_spec(),
        base_url="https://x",
        auth=NoAuth(),
        allowed_operations=["getPetById"],
    )
    ops = load_spec(cfg)
    assert [op.operation_id for op in ops] == ["getPetById"]


def test_load_spec_missing_operation_id_synthesized():
    # Operations without explicit operationId get one derived from
    # method + path so the builder has a stable handle.
    cfg = HttpApiConfig(
        spec_inline={
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "paths": {
                "/items": {
                    "get": {"responses": {"200": {"description": "ok"}}}
                }
            },
        },
        base_url="https://x",
        auth=NoAuth(),
    )
    ops = load_spec(cfg)
    assert len(ops) == 1
    assert ops[0].operation_id  # non-empty
