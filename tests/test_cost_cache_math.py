"""Cache-aware cost math — Gemini implicit caching pricing.

A Gemini 2.5 Pro turn with 1M prompt tokens and 800K cache hits should
bill the 800K at the cache-read rate (~4x cheaper) and the remaining
200K at the full input rate. Before Phase 5 the full 1M was billed at
input rate — a ~4x overcharge.
"""

from __future__ import annotations

from gclaw.models.catalog import ModelCost, ModelRecord
from gclaw.usage.cost import estimate_cost_usd


def _model(**cost_kwargs) -> ModelRecord:
    return ModelRecord(
        provider_id="prov_x",
        model_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        cost=ModelCost(**cost_kwargs),
    )


def test_no_cache_tokens_keeps_legacy_math():
    m = _model(input_per_mtok=1.25, output_per_mtok=10.0)
    # 1M prompt * $1.25 + 1000 completion * $10 = $1.25 + $0.01 = $1.26
    assert estimate_cost_usd(m, 1_000_000, 1_000) == 1.26


def test_cache_read_discount_applied_when_rate_present():
    m = _model(
        input_per_mtok=1.25,
        output_per_mtok=10.0,
        cache_read_per_mtok=0.3125,  # ¼ of input — typical Gemini implicit-cache rate
    )
    # 1M prompt, 800K cached, 200K fresh, 1K out
    # = 200_000 * 1.25 / 1M + 800_000 * 0.3125 / 1M + 1_000 * 10 / 1M
    # = 0.25 + 0.25 + 0.01 = 0.51
    cost = estimate_cost_usd(m, 1_000_000, 1_000, tokens_cache_read=800_000)
    assert abs(cost - 0.51) < 1e-9


def test_cache_tokens_without_rate_falls_back_to_input_rate():
    m = _model(input_per_mtok=1.25, output_per_mtok=10.0)
    # Same as no-cache case — cache count is ignored when no cache rate.
    cost = estimate_cost_usd(m, 1_000_000, 1_000, tokens_cache_read=500_000)
    assert cost == 1.26


def test_cache_tokens_exceeding_input_clamp_to_zero_fresh():
    """If cache_read > tokens_in (weird upstream), don't double-charge
    the cache portion. Fresh input tokens clamp at 0."""
    m = _model(
        input_per_mtok=1.25,
        output_per_mtok=10.0,
        cache_read_per_mtok=0.3125,
    )
    cost = estimate_cost_usd(m, 500_000, 0, tokens_cache_read=1_000_000)
    # fresh = max(0, 500k - 1M) = 0, so only cache + out matter.
    # = 1_000_000 * 0.3125 / 1M = 0.3125
    assert abs(cost - 0.3125) < 1e-9


def test_missing_input_rate_returns_none_regardless_of_cache():
    m = _model(output_per_mtok=10.0)  # no input_per_mtok
    assert (
        estimate_cost_usd(m, 1_000_000, 1_000, tokens_cache_read=500_000)
        is None
    )
