"""Cost estimation helpers for usage telemetry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from gclaw.catalog.service import CatalogService
    from gclaw.models.catalog import ModelRecord

logger = logging.getLogger(__name__)


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


def build_catalog_cost_lookup(
    catalog_service: "CatalogService",
) -> Callable[[str, int, int], float | None]:
    """Return a cost_lookup callable that resolves ``event.name`` (a
    model_id like ``gemini-2.5-flash``) against the catalog and uses the
    matching model's ``ModelCost`` to estimate USD via
    :func:`estimate_cost_usd`.

    Caches ``model_id -> ModelCost`` for the process lifetime. On a cache
    miss we refresh once from ``catalog_service.list_models()`` so newly
    added models are picked up without a restart. If still missing, the
    lookup returns ``None`` (unknown cost).

    Only enabled catalog models are considered; the first enabled model
    whose ``model_id`` matches exactly wins.
    """
    cache: dict[str, object] = {}  # model_id -> ModelCost

    def _refresh() -> None:
        cache.clear()
        try:
            models = catalog_service.list_models()
        except Exception:
            logger.warning(
                "cost_lookup: catalog list_models failed", exc_info=True,
            )
            return
        for m in models:
            if not getattr(m, "enabled", True):
                continue
            mid = getattr(m, "model_id", None)
            if mid is None or mid in cache:
                continue
            cache[mid] = getattr(m, "cost", None)

    def _lookup(model_name: str, tokens_in: int, tokens_out: int) -> float | None:
        if model_name not in cache:
            _refresh()
        if model_name not in cache:
            return None
        cost = cache[model_name]
        if cost is None:
            return None

        class _Stub:
            pass

        stub = _Stub()
        stub.cost = cost  # type: ignore[attr-defined]
        return estimate_cost_usd(stub, tokens_in, tokens_out)  # type: ignore[arg-type]

    return _lookup
