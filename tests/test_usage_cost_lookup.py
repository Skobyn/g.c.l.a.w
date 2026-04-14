"""Tests for catalog-backed cost lookup + UsageRecorder integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gclaw.models.catalog import ModelCost, ModelRecord
from gclaw.usage.cost import build_catalog_cost_lookup
from gclaw.usage.recorder import UsageRecorder


def _make_model(
    model_id: str,
    *,
    enabled: bool = True,
    input_per_mtok: float | None = 1.0,
    output_per_mtok: float | None = 2.0,
) -> ModelRecord:
    return ModelRecord(
        provider_id="prov_test",
        model_id=model_id,
        display_name=model_id,
        enabled=enabled,
        cost=ModelCost(
            input_per_mtok=input_per_mtok,
            output_per_mtok=output_per_mtok,
        ),
    )


class _FakeCatalog:
    def __init__(self, models: list[ModelRecord]):
        self._models = list(models)
        self.list_models_calls = 0

    def list_models(self, provider_id: str | None = None) -> list[ModelRecord]:
        self.list_models_calls += 1
        return list(self._models)


def test_build_catalog_cost_lookup_returns_correct_usd():
    catalog = _FakeCatalog([
        _make_model("gemini-2.5-flash", input_per_mtok=0.3, output_per_mtok=2.5),
    ])
    lookup = build_catalog_cost_lookup(catalog)
    # 1_000_000 input tokens × $0.3 + 1_000_000 output tokens × $2.5
    cost = lookup("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.3 + 2.5)


def test_build_catalog_cost_lookup_unknown_model_returns_none():
    catalog = _FakeCatalog([_make_model("gemini-2.5-flash")])
    lookup = build_catalog_cost_lookup(catalog)
    assert lookup("nonexistent-model", 100, 200) is None


def test_recorder_calls_cost_lookup_when_cost_usd_missing():
    repo = MagicMock()
    lookup = MagicMock(return_value=0.000123)
    recorder = UsageRecorder(repo=repo, enabled=True, cost_lookup=lookup)

    recorder.record_model_call(
        model_id="gemini-2.5-flash",
        tokens_in=100,
        tokens_out=200,
    )
    lookup.assert_called_once_with("gemini-2.5-flash", 100, 200)
    event = repo.record.call_args[0][0]
    assert event.cost_usd == 0.000123


def test_recorder_preserves_explicit_cost_usd():
    repo = MagicMock()
    lookup = MagicMock(return_value=0.999)
    recorder = UsageRecorder(repo=repo, enabled=True, cost_lookup=lookup)

    recorder.record_model_call(
        model_id="gemini-2.5-flash",
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.05,
    )
    lookup.assert_not_called()
    event = repo.record.call_args[0][0]
    assert event.cost_usd == 0.05


def test_recorder_skips_lookup_when_tokens_unknown():
    repo = MagicMock()
    lookup = MagicMock(return_value=0.001)
    recorder = UsageRecorder(repo=repo, enabled=True, cost_lookup=lookup)

    recorder.record_model_call(
        model_id="gemini-2.5-flash",
        tokens_in=None,
        tokens_out=None,
    )
    lookup.assert_not_called()
    event = repo.record.call_args[0][0]
    assert event.cost_usd is None


def test_recorder_without_lookup_behaves_as_before():
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    recorder.record_model_call(
        model_id="gemini-2.5-flash",
        tokens_in=100,
        tokens_out=200,
    )
    event = repo.record.call_args[0][0]
    assert event.cost_usd is None


def test_cache_refresh_picks_up_newly_added_model():
    model_a = _make_model("model-a", input_per_mtok=1.0, output_per_mtok=1.0)
    catalog = _FakeCatalog([model_a])
    lookup = build_catalog_cost_lookup(catalog)

    # First call hits model-a, populates cache.
    assert lookup("model-a", 1_000_000, 0) == pytest.approx(1.0)
    first_calls = catalog.list_models_calls

    # Miss on unknown → triggers refresh.
    assert lookup("model-b", 1_000_000, 0) is None
    assert catalog.list_models_calls == first_calls + 1

    # Add model-b to the catalog. Next miss for model-b refreshes again.
    catalog._models.append(
        _make_model("model-b", input_per_mtok=4.0, output_per_mtok=0.0)
    )
    assert lookup("model-b", 1_000_000, 0) == pytest.approx(4.0)


def test_disabled_models_are_ignored():
    catalog = _FakeCatalog([
        _make_model("gemini-2.5-flash", enabled=False, input_per_mtok=0.3, output_per_mtok=2.5),
    ])
    lookup = build_catalog_cost_lookup(catalog)
    assert lookup("gemini-2.5-flash", 100, 200) is None
