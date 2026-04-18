"""ModelCatalog nightly price-sync — parsers + reconciliation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from gclaw.models.catalog import ModelCost, ModelRecord
from gclaw.models.price_sync import (
    parse_litellm,
    parse_openrouter,
    sync_catalog_prices,
)


class _FakeFetcher:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get_json(self, url: str) -> Any:
        self.calls.append(url)
        if url in self._responses:
            return self._responses[url]
        raise RuntimeError(f"unexpected URL: {url}")


def _mk_model(**overrides) -> ModelRecord:
    base = dict(
        provider_id="prov_x",
        model_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
    )
    base.update(overrides)
    return ModelRecord(**base)


# ── parsers ───────────────────────────────────────────────────────────


def test_parse_litellm_converts_per_token_to_per_mtok():
    raw = {
        "sample_spec": {"note": "skip me"},
        "gemini-2.5-flash": {
            "input_cost_per_token": 1.25e-7,  # $0.125 / MTok
            "output_cost_per_token": 1e-6,    # $1 / MTok
            "cache_read_input_token_cost": 3.125e-8,  # $0.03125 / MTok
            "max_input_tokens": 1048576,
            "max_output_tokens": 8192,
            "litellm_provider": "vertex_ai",
        },
    }
    parsed = parse_litellm(raw)
    assert "sample_spec" not in parsed
    entry = parsed["gemini-2.5-flash"]
    assert abs(entry["input_per_mtok"] - 0.125) < 1e-9
    assert abs(entry["output_per_mtok"] - 1.0) < 1e-9
    assert abs(entry["cache_read_per_mtok"] - 0.03125) < 1e-9
    assert entry["context_window"] == 1048576
    assert entry["max_output_tokens"] == 8192


def test_parse_openrouter_shape():
    raw = {
        "data": [
            {
                "id": "anthropic/claude-opus-4.5",
                "context_length": 200000,
                "pricing": {
                    "prompt": "0.00001500",
                    "completion": "0.00007500",
                    "input_cache_read": "0.00000150",
                },
                "top_provider": {"max_completion_tokens": 8192},
            },
            {"id": "bad/entry-no-price"},
        ]
    }
    parsed = parse_openrouter(raw)
    entry = parsed["anthropic/claude-opus-4.5"]
    assert abs(entry["input_per_mtok"] - 15.0) < 1e-9
    assert abs(entry["output_per_mtok"] - 75.0) < 1e-9
    assert abs(entry["cache_read_per_mtok"] - 1.5) < 1e-9
    assert entry["context_window"] == 200000
    # Missing pricing → None fields but still indexed.
    assert "bad/entry-no-price" in parsed
    assert parsed["bad/entry-no-price"]["input_per_mtok"] is None


# ── reconciliation ────────────────────────────────────────────────────


def test_sync_updates_model_when_upstream_differs():
    svc = MagicMock()
    rec = _mk_model(
        cost=ModelCost(input_per_mtok=0.0625, output_per_mtok=0.25),
        context_window=32_000,
    )
    svc.list_models.return_value = [rec]
    svc.list_providers.return_value = []
    svc.update_model.return_value = rec

    fetcher = _FakeFetcher({
        "LL": {
            "gemini-2.5-flash": {
                "input_cost_per_token": 1.25e-7,
                "output_cost_per_token": 1e-6,
                "cache_read_input_token_cost": 3.125e-8,
                "max_input_tokens": 1_048_576,
                "max_output_tokens": 8192,
                "litellm_provider": "vertex_ai",
            },
        },
        "OR": {"data": []},
    })

    result = sync_catalog_prices(
        svc,
        fetcher=fetcher,
        litellm_url="LL",
        openrouter_url="OR",
    )
    assert result.total == 1
    assert result.updated == 1
    assert result.unchanged == 0

    call = svc.update_model.call_args
    assert call.args == (rec.id,)
    updates = call.kwargs
    assert updates["context_window"] == 1_048_576
    assert updates["max_output_tokens"] == 8192
    assert abs(updates["cost"]["input_per_mtok"] - 0.125) < 1e-9
    assert abs(updates["cost"]["cache_read_per_mtok"] - 0.03125) < 1e-9


def test_sync_is_idempotent_when_nothing_changed():
    svc = MagicMock()
    rec = _mk_model(
        cost=ModelCost(
            input_per_mtok=0.125,
            output_per_mtok=1.0,
            cache_read_per_mtok=0.03125,
        ),
        context_window=1_048_576,
        max_output_tokens=8192,
    )
    svc.list_models.return_value = [rec]
    svc.list_providers.return_value = []

    fetcher = _FakeFetcher({
        "LL": {
            "gemini-2.5-flash": {
                "input_cost_per_token": 1.25e-7,
                "output_cost_per_token": 1e-6,
                "cache_read_input_token_cost": 3.125e-8,
                "max_input_tokens": 1_048_576,
                "max_output_tokens": 8192,
                "litellm_provider": "vertex_ai",
            },
        },
        "OR": {"data": []},
    })

    result = sync_catalog_prices(
        svc, fetcher=fetcher, litellm_url="LL", openrouter_url="OR",
    )
    assert result.updated == 0
    assert result.unchanged == 1
    svc.update_model.assert_not_called()


def test_sync_missing_upstream_counted_not_updated():
    svc = MagicMock()
    rec = _mk_model(model_id="exotic/unknown-model")
    svc.list_models.return_value = [rec]
    svc.list_providers.return_value = []

    fetcher = _FakeFetcher({"LL": {}, "OR": {"data": []}})
    result = sync_catalog_prices(
        svc, fetcher=fetcher, litellm_url="LL", openrouter_url="OR",
    )
    assert result.total == 1
    assert result.missing_upstream == 1
    assert result.updated == 0


def test_sync_survives_update_exception():
    svc = MagicMock()
    rec = _mk_model()
    svc.list_models.return_value = [rec]
    svc.list_providers.return_value = []
    svc.update_model.side_effect = RuntimeError("firestore flaky")

    fetcher = _FakeFetcher({
        "LL": {
            "gemini-2.5-flash": {
                "input_cost_per_token": 1.25e-7,
                "output_cost_per_token": 1e-6,
                "max_input_tokens": 1_048_576,
                "litellm_provider": "vertex_ai",
            },
        },
        "OR": {"data": []},
    })
    result = sync_catalog_prices(
        svc, fetcher=fetcher, litellm_url="LL", openrouter_url="OR",
    )
    assert result.errors == 1
    assert result.updated == 0


def test_sync_openrouter_takes_precedence_for_openrouter_providers():
    """An OPENROUTER-kind provider model prefers OpenRouter pricing over
    LiteLLM even when both sources list the model."""
    svc = MagicMock()
    rec = _mk_model(
        provider_id="prov_or",
        model_id="anthropic/claude-opus-4.5",
    )
    svc.list_models.return_value = [rec]

    prov = MagicMock()
    prov.id = "prov_or"
    prov.kind = MagicMock()
    prov.kind.value = "openrouter"
    svc.list_providers.return_value = [prov]

    fetcher = _FakeFetcher({
        "LL": {
            "anthropic/claude-opus-4.5": {
                "input_cost_per_token": 1e-9,  # garbage LiteLLM value
                "output_cost_per_token": 1e-9,
                "max_input_tokens": 1,
                "litellm_provider": "anthropic",
            },
        },
        "OR": {
            "data": [
                {
                    "id": "anthropic/claude-opus-4.5",
                    "context_length": 200_000,
                    "pricing": {
                        "prompt": "0.00001500",
                        "completion": "0.00007500",
                    },
                },
            ]
        },
    })

    sync_catalog_prices(
        svc, fetcher=fetcher, litellm_url="LL", openrouter_url="OR",
    )
    updates = svc.update_model.call_args.kwargs
    # OpenRouter wins.
    assert updates["context_window"] == 200_000
    assert abs(updates["cost"]["input_per_mtok"] - 15.0) < 1e-9
