"""Cost estimation helpers for usage telemetry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.models.catalog import ModelRecord


def estimate_cost_usd(
    model: "ModelRecord", tokens_in: int, tokens_out: int
) -> float | None:
    """Estimate the USD cost of a completion given the model's catalog record.

    Returns None when either rate is missing — downstream should treat that
    as "unknown cost" rather than zero.
    """
    cost = getattr(model, "cost", None)
    if cost is None:
        return None
    if cost.input_per_mtok is None or cost.output_per_mtok is None:
        return None
    return (
        (tokens_in or 0) * cost.input_per_mtok
        + (tokens_out or 0) * cost.output_per_mtok
    ) / 1_000_000
