"""Nightly price + context-window sync for the persistent ModelCatalog.

Fetches two upstream sources:

1. LiteLLM's ``model_prices_and_context_window.json`` on GitHub — the
   canonical community-maintained pricing table; updated multiple times
   per week; covers Vertex Gemini, OpenAI, Anthropic, and many others;
   includes ``cache_read_input_token_cost`` for Gemini + Anthropic.

2. OpenRouter's ``/api/v1/models`` — live per-model pricing + context
   lengths for everything it brokers.

Reconciles both into each :class:`ModelRecord` in the catalog by
``model_id`` exact match and ``provider.kind`` affinity:

* ``OPENROUTER`` providers prefer OpenRouter data.
* Everything else prefers LiteLLM data, falling back to OpenRouter.

Idempotent: diffs each record and only calls
:meth:`CatalogService.update_model` when at least one of
``context_window`` / ``max_output_tokens`` / ``cost.input_per_mtok`` /
``cost.output_per_mtok`` / ``cost.cache_read_per_mtok`` actually
changed.

Designed to be driven by a Cloud Scheduler POST to
``/admin/price-sync`` (see crons/price_sync.json). Also safely callable
at boot for cold-cache initialization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Protocol

logger = logging.getLogger(__name__)


# Source URLs — pinned to stable paths; override via function args in tests.
LITELLM_PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


class _HttpFetcher(Protocol):
    def get_json(self, url: str) -> Any: ...  # pragma: no cover


class HttpxFetcher:
    """Default fetcher using httpx. Stubbable in tests."""

    def get_json(self, url: str) -> Any:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()


# ── Normalization helpers ─────────────────────────────────────────────


def _per_mtok(raw_per_tok: Any) -> float | None:
    """Convert a $/token rate (LiteLLM/OpenRouter native) to $/MTok."""
    if raw_per_tok is None:
        return None
    try:
        value = float(raw_per_tok)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value * 1_000_000


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


# ── Upstream parsers ──────────────────────────────────────────────────


def parse_litellm(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{model_id: {input_per_mtok, output_per_mtok, cache_read_per_mtok,
    context_window, max_output_tokens, provider}}`` from the raw JSON.

    Skips the ``sample_spec`` sentinel entry LiteLLM ships in the table.
    """
    out: dict[str, dict[str, Any]] = {}
    for model_id, rec in (payload or {}).items():
        if model_id == "sample_spec" or not isinstance(rec, dict):
            continue
        out[model_id] = {
            "input_per_mtok": _per_mtok(rec.get("input_cost_per_token")),
            "output_per_mtok": _per_mtok(rec.get("output_cost_per_token")),
            "cache_read_per_mtok": _per_mtok(
                rec.get("cache_read_input_token_cost")
            ),
            "context_window": _int_or_none(rec.get("max_input_tokens")),
            "max_output_tokens": _int_or_none(rec.get("max_output_tokens")),
            "provider": rec.get("litellm_provider") or "",
        }
    return out


def parse_openrouter(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a normalized map from OpenRouter's ``GET /api/v1/models``."""
    out: dict[str, dict[str, Any]] = {}
    for rec in (payload or {}).get("data", []) or []:
        if not isinstance(rec, dict):
            continue
        mid = rec.get("id") or ""
        if not mid:
            continue
        pricing = rec.get("pricing") or {}
        out[mid] = {
            "input_per_mtok": _per_mtok(pricing.get("prompt")),
            "output_per_mtok": _per_mtok(pricing.get("completion")),
            "cache_read_per_mtok": _per_mtok(pricing.get("input_cache_read")),
            "context_window": _int_or_none(rec.get("context_length")),
            "max_output_tokens": _int_or_none(
                (rec.get("top_provider") or {}).get("max_completion_tokens")
            ),
            "provider": "openrouter",
        }
    return out


# ── Reconciliation ────────────────────────────────────────────────────


@dataclass
class SyncResult:
    total: int = 0
    updated: int = 0
    unchanged: int = 0
    missing_upstream: int = 0
    errors: int = 0
    changes: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "missing_upstream": self.missing_upstream,
            "errors": self.errors,
            "changes": self.changes,
        }


def _pick_upstream(
    model_id: str,
    provider_kind: str,
    litellm: dict[str, dict[str, Any]],
    openrouter: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick the best upstream record for a given model, or None."""
    if provider_kind == "openrouter" and model_id in openrouter:
        return openrouter[model_id]
    if model_id in litellm:
        return litellm[model_id]
    if model_id in openrouter:
        return openrouter[model_id]
    return None


def _diff_model(
    record: Any, upstream: dict[str, Any]
) -> dict[str, Any] | None:
    """Return a dict of field updates for ``catalog_service.update_model``
    when the upstream differs from the stored record, or ``None``."""
    updates: dict[str, Any] = {}
    new_ctx = upstream.get("context_window")
    if new_ctx is not None and new_ctx != getattr(record, "context_window", None):
        updates["context_window"] = new_ctx

    new_max_out = upstream.get("max_output_tokens")
    if (
        new_max_out is not None
        and new_max_out != getattr(record, "max_output_tokens", None)
    ):
        updates["max_output_tokens"] = new_max_out

    current_cost = getattr(record, "cost", None)
    cost_updates: dict[str, Any] = {}
    for key in ("input_per_mtok", "output_per_mtok", "cache_read_per_mtok"):
        new_val = upstream.get(key)
        if new_val is None:
            continue
        cur_val = getattr(current_cost, key, None) if current_cost else None
        # Treat as changed when the new value differs by > 1e-9 $/MTok
        # (fpa noise is not meaningful).
        if cur_val is None or abs(float(cur_val) - float(new_val)) > 1e-9:
            cost_updates[key] = new_val
    if cost_updates:
        current_dump: dict[str, Any] = (
            current_cost.model_dump() if current_cost is not None else {}
        )
        merged = {**current_dump, **cost_updates}
        updates["cost"] = merged

    return updates or None


def sync_catalog_prices(
    catalog_service: Any,
    *,
    fetcher: _HttpFetcher | None = None,
    provider_resolver: Callable[[str], str] | None = None,
    litellm_url: str = LITELLM_PRICES_URL,
    openrouter_url: str = OPENROUTER_MODELS_URL,
) -> SyncResult:
    """Sync every model in the catalog against LiteLLM + OpenRouter.

    ``provider_resolver(provider_id) -> kind_str`` — used to decide
    which upstream takes precedence. When omitted we call
    ``catalog_service.list_providers()`` once and build the map.
    """
    fetcher = fetcher or HttpxFetcher()
    result = SyncResult()

    litellm_failed = False
    try:
        litellm_raw = fetcher.get_json(litellm_url)
        litellm = parse_litellm(litellm_raw)
    except Exception as e:
        logger.warning("price_sync: LiteLLM fetch failed: %s", e)
        litellm = {}
        litellm_failed = True

    openrouter_failed = False
    try:
        openrouter_raw = fetcher.get_json(openrouter_url)
        openrouter = parse_openrouter(openrouter_raw)
    except Exception as e:
        logger.warning("price_sync: OpenRouter fetch failed: %s", e)
        openrouter = {}
        openrouter_failed = True

    if litellm_failed and openrouter_failed:
        # Real network outage on both sides — don't mass-mark everything
        # as missing_upstream, which would spam the changelog with phantom
        # entries. Just bail.
        logger.warning("price_sync: both upstream fetches failed; aborting")
        return result

    # Resolve provider kinds once.
    if provider_resolver is None:
        provider_kinds: dict[str, str] = {}
        try:
            for prov in catalog_service.list_providers():
                kind = getattr(prov, "kind", None)
                provider_kinds[prov.id] = (
                    kind.value if hasattr(kind, "value") else str(kind or "")
                )
        except Exception:
            logger.warning(
                "price_sync: provider list failed", exc_info=True
            )

        def _resolve(pid: str) -> str:
            return provider_kinds.get(pid, "")

        provider_resolver = _resolve

    try:
        records: Iterable[Any] = catalog_service.list_models()
    except Exception:
        logger.warning(
            "price_sync: catalog list_models failed", exc_info=True
        )
        return result

    for rec in records:
        result.total += 1
        model_id = getattr(rec, "model_id", None)
        if not model_id:
            continue
        kind = provider_resolver(getattr(rec, "provider_id", "") or "")
        upstream = _pick_upstream(model_id, kind, litellm, openrouter)
        if upstream is None:
            result.missing_upstream += 1
            continue
        updates = _diff_model(rec, upstream)
        if updates is None:
            result.unchanged += 1
            continue
        try:
            catalog_service.update_model(rec.id, **updates)
            result.updated += 1
            result.changes.append(
                {"model_id": model_id, "fields": sorted(updates.keys())}
            )
        except Exception:
            result.errors += 1
            logger.warning(
                "price_sync: update_model failed for %s", model_id, exc_info=True
            )

    logger.info(
        "price_sync: total=%d updated=%d unchanged=%d missing=%d errors=%d",
        result.total,
        result.updated,
        result.unchanged,
        result.missing_upstream,
        result.errors,
    )
    return result
