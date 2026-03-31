"""Shared test fixtures."""

import os
import pytest
from gclaw.settings import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings pointing at a temporary config directory."""
    os.environ["GCP_PROJECT_ID"] = "test-project"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return Settings(
        gcp_project_id="test-project",
        gcp_location="us-central1",
        gemini_pro_model="gemini-2.5-flash",
        gemini_flash_model="gemini-2.5-flash",
        firestore_database="(default)",
        config_dir=str(config_dir),
    )
