"""Tests for startup Secret Manager bootstrap."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from gclaw.catalog.secret_bootstrap import bootstrap_secrets
from gclaw.migrate.seed_secrets import SecretSpec


def _make_fetch_stub(returns: dict[str, str | None]):
    def stub(project, spec):
        return returns.get(spec.name)
    return stub


ENV_SPEC = SecretSpec(
    name="gclaw-gh-token",
    description="GitHub PAT.",
    env_alias="GH_TOKEN",
    bootstrap="env",
)

FILE_SPEC = SecretSpec(
    name="gclaw-gws-credentials",
    description="GWS JSON.",
    env_alias="GOOGLE_WORKSPACE_CREDENTIALS_FILE",
    bootstrap="file",
    bootstrap_path="gws-credentials.json",
)

NONE_SPEC = SecretSpec(
    name="gclaw-openai-api-key",
    description="OpenAI.",
    env_alias="OPENAI_API_KEY",
    bootstrap="none",
)


def test_env_bootstrap_sets_env_var(monkeypatch, tmp_path):
    # clear any leak from a previous test
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({"gclaw-gh-token": "ghp_fake_token"}),
    ):
        result = bootstrap_secrets(
            project="p",
            tmp_dir=tmp_path,
            specs=(ENV_SPEC,),
        )

    assert os.environ["GH_TOKEN"] == "ghp_fake_token"
    assert result["applied"] == ["gclaw-gh-token→env:GH_TOKEN"]
    assert result["skipped"] == []
    assert result["failed"] == []


def test_file_bootstrap_writes_file_and_sets_env(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_WORKSPACE_CREDENTIALS_FILE", raising=False)
    payload = '{"client_id":"abc","client_secret":"xyz"}'

    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({"gclaw-gws-credentials": payload}),
    ):
        result = bootstrap_secrets(
            project="p",
            tmp_dir=tmp_path,
            specs=(FILE_SPEC,),
        )

    written = tmp_path / "gws-credentials.json"
    assert written.read_text() == payload
    # file mode 0600
    assert (written.stat().st_mode & 0o777) == 0o600
    assert os.environ["GOOGLE_WORKSPACE_CREDENTIALS_FILE"] == str(written)
    assert len(result["applied"]) == 1


def test_none_bootstrap_ignored(tmp_path):
    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({"gclaw-openai-api-key": "sk-real"}),
    ) as fetch:
        result = bootstrap_secrets(
            project="p",
            tmp_dir=tmp_path,
            specs=(NONE_SPEC,),
        )

    # bootstrap="none" is skipped entirely — not even fetched.
    fetch.assert_not_called()
    assert result == {"applied": [], "skipped": [], "failed": []}


def test_missing_secret_recorded_as_skipped(monkeypatch, tmp_path):
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({}),  # all missing
    ):
        result = bootstrap_secrets(
            project="p",
            tmp_dir=tmp_path,
            specs=(ENV_SPEC, FILE_SPEC),
        )

    assert "GH_TOKEN" not in os.environ
    assert set(result["skipped"]) == {"gclaw-gh-token", "gclaw-gws-credentials"}
    assert result["applied"] == []
    assert result["failed"] == []


def test_file_bootstrap_without_path_fails_gracefully(monkeypatch, tmp_path):
    bad_spec = SecretSpec(
        name="gclaw-bad",
        description="",
        env_alias="BAD",
        bootstrap="file",
        bootstrap_path="",  # missing
    )
    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({"gclaw-bad": "value"}),
    ):
        result = bootstrap_secrets(project="p", tmp_dir=tmp_path, specs=(bad_spec,))

    assert result["failed"] == ["gclaw-bad"]
    assert "BAD" not in os.environ


def test_unknown_bootstrap_mode_logged_and_failed(tmp_path):
    weird_spec = SecretSpec(
        name="gclaw-weird",
        description="",
        env_alias="WEIRD",
        bootstrap="telepathy",
    )
    with patch(
        "gclaw.catalog.secret_bootstrap._fetch_secret",
        side_effect=_make_fetch_stub({"gclaw-weird": "v"}),
    ):
        result = bootstrap_secrets(project="p", tmp_dir=tmp_path, specs=(weird_spec,))

    assert result["failed"] == ["gclaw-weird"]


def test_fetch_secret_swallows_sdk_errors(tmp_path):
    """_fetch_secret must return None on any SDK failure — bootstrap relies on it."""
    from gclaw.catalog import secret_bootstrap

    # Force import failure inside _fetch_secret by monkey-patching the client.
    class BoomClient:
        def access_secret_version(self, name):
            raise RuntimeError("sdk exploded")

    with patch.object(
        secret_bootstrap,
        "_fetch_secret",
        wraps=secret_bootstrap._fetch_secret,
    ):
        with patch(
            "google.cloud.secretmanager.SecretManagerServiceClient",
            return_value=BoomClient(),
        ):
            value = secret_bootstrap._fetch_secret("p", ENV_SPEC)

    assert value is None
