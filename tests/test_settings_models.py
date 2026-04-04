"""Tests for model routing settings."""

import os
import pytest
from gclaw.settings import Settings


def test_settings_model_routing_defaults():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    s = Settings()
    assert s.model_routing_enabled is False
    assert s.gemma_endpoint_id == ""
    assert s.nemotron_endpoint_id == ""
    assert s.nemotron_provider == "vertex"


def test_settings_model_routing_enabled():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    os.environ["GEMMA_ENDPOINT_ID"] = "projects/apexfoundation/locations/us-central1/endpoints/111"
    os.environ["NEMOTRON_ENDPOINT_ID"] = "projects/apexfoundation/locations/us-central1/endpoints/222"
    os.environ["NEMOTRON_PROVIDER"] = "nim"
    try:
        s = Settings()
        assert s.model_routing_enabled is True
        assert "111" in s.gemma_endpoint_id
        assert "222" in s.nemotron_endpoint_id
        assert s.nemotron_provider == "nim"
    finally:
        for key in ["MODEL_ROUTING_ENABLED", "GEMMA_ENDPOINT_ID",
                     "NEMOTRON_ENDPOINT_ID", "NEMOTRON_PROVIDER"]:
            os.environ.pop(key, None)
