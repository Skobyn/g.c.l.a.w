"""Cost math for usage telemetry."""

from __future__ import annotations

from gclaw.models.catalog import ModelCost, ModelRecord
from gclaw.usage.cost import estimate_cost_usd


def _model(cost: ModelCost) -> ModelRecord:
    return ModelRecord(
        provider_id="p1",
        model_id="m1",
        display_name="test",
        cost=cost,
    )


def test_both_rates_present():
    m = _model(ModelCost(input_per_mtok=3.0, output_per_mtok=15.0))
    # 1_000_000 in-tokens @ $3/M + 500_000 out @ $15/M = 3 + 7.5 = 10.5
    assert estimate_cost_usd(m, 1_000_000, 500_000) == 10.5


def test_input_rate_missing():
    m = _model(ModelCost(input_per_mtok=None, output_per_mtok=5.0))
    assert estimate_cost_usd(m, 100, 200) is None


def test_output_rate_missing():
    m = _model(ModelCost(input_per_mtok=1.0, output_per_mtok=None))
    assert estimate_cost_usd(m, 100, 200) is None


def test_zero_tokens_returns_zero():
    m = _model(ModelCost(input_per_mtok=3.0, output_per_mtok=15.0))
    assert estimate_cost_usd(m, 0, 0) == 0.0


def test_none_tokens_treated_as_zero():
    m = _model(ModelCost(input_per_mtok=3.0, output_per_mtok=15.0))
    # duration helper handles None as zero
    assert estimate_cost_usd(m, None, None) == 0.0  # type: ignore[arg-type]
