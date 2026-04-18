"""Unit tests for gclaw.observability.tracing.init_tracing.

Tracing state is process-global in OTel; pytest runs these in a single
process so we rely on the init_tracing idempotency guard and the no-op
short-circuit to keep the tests independent.
"""

from __future__ import annotations

import pytest

from gclaw.settings import Settings


def _settings(tmp_path, **overrides) -> Settings:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(exist_ok=True)
    base = dict(
        gcp_project_id="test-project",
        gcp_location="us-central1",
        gemini_pro_model="gemini-2.5-flash",
        gemini_flash_model="gemini-2.5-flash",
        firestore_database="(default)",
        config_dir=str(config_dir),
    )
    base.update(overrides)
    return Settings(**base)


def test_init_tracing_is_noop_when_disabled(tmp_path):
    from gclaw.observability.tracing import init_tracing

    s = _settings(tmp_path, observability_enabled=False)
    assert init_tracing(s) is None


def test_init_tracing_builds_provider_when_enabled(tmp_path):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider

    from gclaw.observability.tracing import init_tracing

    s = _settings(
        tmp_path,
        observability_enabled=True,
        otel_service_name="gclaw-test",
        otel_sampling_ratio=1.0,
        otel_exporter_otlp_endpoint="",
    )
    provider = init_tracing(s)
    # Provider is either a fresh TracerProvider or an existing one from a
    # prior test in the same process. Either way, it must be a SDK provider.
    assert isinstance(provider, TracerProvider)


def test_init_tracing_missing_project_id_still_returns_provider(tmp_path):
    """Cloud Trace exporter skips when project_id is empty, but the
    provider is still built so OTLP and instrumentors work."""
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider

    from gclaw.observability.tracing import init_tracing

    s = _settings(
        tmp_path,
        gcp_project_id="",
        observability_enabled=True,
    )
    provider = init_tracing(s)
    assert isinstance(provider, TracerProvider)
