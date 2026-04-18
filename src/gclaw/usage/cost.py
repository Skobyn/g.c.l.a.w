"""Cost estimation helpers for usage telemetry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from gclaw.catalog.service import CatalogService
    from gclaw.models.catalog import ModelRecord

logger = logging.getLogger(__name__)


def estimate_cost_usd(
    model: "ModelRecord",
    tokens_in: int,
    tokens_out: int,
    tokens_cache_read: int | None = None,
) -> float | None:
    """Estimate the USD cost of a completion given the model's catalog record.

    When ``tokens_cache_read`` is provided (Gemini / Anthropic caching),
    those tokens are billed at ``cost.cache_read_per_mtok`` (typically
    ~25% of the input rate — a 4x cost delta) and deducted from the
    fresh-input count. Falls back to billing everything at input rate
    when the cache rate is missing.

    Returns None when either required rate is missing — downstream should
    treat that as "unknown cost" rather than zero.
    """
    cost = getattr(model, "cost", None)
    if cost is None:
        return None
    if cost.input_per_mtok is None or cost.output_per_mtok is None:
        return None

    tin = int(tokens_in or 0)
    tout = int(tokens_out or 0)
    tcache = int(tokens_cache_read or 0)

    cache_rate = getattr(cost, "cache_read_per_mtok", None)
    if tcache > 0 and cache_rate is not None:
        fresh_in = max(0, tin - tcache)
        return (
            fresh_in * cost.input_per_mtok
            + tcache * cache_rate
            + tout * cost.output_per_mtok
        ) / 1_000_000
    return (
        tin * cost.input_per_mtok + tout * cost.output_per_mtok
    ) / 1_000_000


def build_catalog_cost_lookup(
    catalog_service: "CatalogService",
) -> Callable[..., float | None]:
    """Return a cost_lookup callable that resolves ``event.name`` (a
    model_id like ``gemini-2.5-flash``) against the catalog and uses the
    matching model's ``ModelCost`` to estimate USD via
    :func:`estimate_cost_usd`.

    Signature: ``lookup(model_name, tokens_in, tokens_out, *, tokens_cache_read=None)``

    The trailing ``tokens_cache_read`` is keyword-only and optional for
    backwards compatibility with callers that don't track cache tokens
    yet (UsageRecorder today).

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

    def _lookup(
        model_name: str,
        tokens_in: int,
        tokens_out: int,
        *,
        tokens_cache_read: int | None = None,
    ) -> float | None:
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
        return estimate_cost_usd(
            stub,  # type: ignore[arg-type]
            tokens_in,
            tokens_out,
            tokens_cache_read=tokens_cache_read,
        )

    return _lookup


def build_catalog_context_lookup(
    catalog_service: "CatalogService",
) -> Callable[[str], int | None]:
    """Return a ``model_id -> context_window`` lookup.

    Used by Phase 4 LiveSpanProcessor / Phase 6 dashboard to compute
    context-window utilization %. Same caching pattern as
    :func:`build_catalog_cost_lookup`.
    """
    cache: dict[str, int | None] = {}

    def _refresh() -> None:
        cache.clear()
        try:
            models = catalog_service.list_models()
        except Exception:
            logger.warning(
                "context_lookup: catalog list_models failed", exc_info=True,
            )
            return
        for m in models:
            if not getattr(m, "enabled", True):
                continue
            mid = getattr(m, "model_id", None)
            if mid is None or mid in cache:
                continue
            cw = getattr(m, "context_window", None)
            cache[mid] = int(cw) if cw else None

    def _lookup(model_name: str) -> int | None:
        if model_name not in cache:
            _refresh()
        return cache.get(model_name)

    return _lookup
