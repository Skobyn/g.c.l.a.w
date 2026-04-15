"""Tests for the Secret Manager seeder CLI."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from gclaw.migrate.seed_secrets import (
    PLACEHOLDER_VALUE,
    SECRETS,
    parse_values_file,
    seed_all,
    sm_path,
)


def test_sm_path_default_version():
    assert (
        sm_path("p", "s")
        == "projects/p/secrets/s/versions/latest"
    )


def test_sm_path_explicit_version():
    assert (
        sm_path("p", "s", version="3")
        == "projects/p/secrets/s/versions/3"
    )


def test_parse_values_file_strips_quotes(tmp_path):
    p = tmp_path / "v.env"
    p.write_text(
        '# comment\n'
        'FOO=bar\n'
        'QUOTED="abc"\n'
        "SQUOTED='xyz'\n"
        "\n"  # blank line
        "NOTAPAIR\n"  # ignored with warning
    )
    values = parse_values_file(str(p))
    assert values == {"FOO": "bar", "QUOTED": "abc", "SQUOTED": "xyz"}


def test_seed_all_dry_run_placeholder_by_default():
    results = seed_all(
        project="apex-internal-apps",
        values={},
        apply=False,
        use_env_fallback=False,
        placeholder_for_missing=True,
    )
    # one result per canonical secret
    assert len(results) == len(SECRETS)
    assert all(r["will_create"] for r in results)
    assert all(r["will_add_version"] for r in results)
    assert all(r["value_source"] == "placeholder" for r in results)


def test_seed_all_dry_run_no_placeholder_skips_versions():
    results = seed_all(
        project="p",
        values={},
        apply=False,
        use_env_fallback=False,
        placeholder_for_missing=False,
    )
    assert all(not r["will_add_version"] for r in results)


def test_seed_all_uses_values_file_by_canonical_name():
    results = seed_all(
        project="p",
        values={"watson-openai-api-key": "sk-real"},
        apply=False,
        use_env_fallback=False,
        placeholder_for_missing=True,
    )
    openai = next(r for r in results if r["name"] == "watson-openai-api-key")
    assert openai["value_source"] == "values-file"


def test_seed_all_uses_values_file_by_env_alias():
    results = seed_all(
        project="p",
        values={"ANTHROPIC_API_KEY": "sk-ant-real"},
        apply=False,
        use_env_fallback=False,
        placeholder_for_missing=True,
    )
    anth = next(r for r in results if r["name"] == "watson-anthropic-api-key")
    assert anth["value_source"] == "values-file"


def test_seed_all_env_fallback_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    results = seed_all(
        project="p",
        values={},
        apply=False,
        use_env_fallback=True,
        placeholder_for_missing=True,
    )
    oai = next(r for r in results if r["name"] == "watson-openai-api-key")
    assert oai["value_source"] == "env"


def test_seed_all_env_fallback_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    results = seed_all(
        project="p",
        values={},
        apply=False,
        use_env_fallback=False,
        placeholder_for_missing=True,
    )
    oai = next(r for r in results if r["name"] == "watson-openai-api-key")
    # With env-fallback disabled, value_source falls back to placeholder.
    assert oai["value_source"] == "placeholder"


def test_seed_all_apply_creates_and_versions(monkeypatch):
    """With --apply, each missing secret is created and a version is added."""
    client = MagicMock()

    # get_secret raises => secret doesn't exist
    class NotFound(Exception):
        pass

    def _get(name):
        raise NotFound("not found")

    client.get_secret.side_effect = _get
    fake_version = MagicMock()
    fake_version.name = "path/v/1"
    client.add_secret_version.return_value = fake_version

    with patch(
        "gclaw.migrate.seed_secrets._client_and_parent",
        return_value=(client, "projects/p"),
    ):
        results = seed_all(
            project="p",
            values={"OPENAI_API_KEY": "sk-real"},
            apply=True,
            use_env_fallback=False,
            placeholder_for_missing=True,
        )

    # create_secret called once per secret
    assert client.create_secret.call_count == len(SECRETS)
    # add_secret_version called once per secret (all have a value — placeholder or real)
    assert client.add_secret_version.call_count == len(SECRETS)
    # the openai one carries the real value
    calls_with_openai = [
        c for c in client.add_secret_version.call_args_list
        if "watson-openai-api-key" in c.kwargs["request"]["parent"]
    ]
    assert len(calls_with_openai) == 1
    assert calls_with_openai[0].kwargs["request"]["payload"]["data"] == b"sk-real"
    # All marked created
    assert all(r["created"] for r in results)


def test_seed_all_apply_idempotent_when_secret_exists():
    """If the secret already exists, we don't re-create but still add a version."""
    client = MagicMock()
    client.get_secret.return_value = MagicMock()  # exists — no exception
    client.add_secret_version.return_value = MagicMock(name="path/v/2")
    client.add_secret_version.return_value.name = "path/v/2"

    with patch(
        "gclaw.migrate.seed_secrets._client_and_parent",
        return_value=(client, "projects/p"),
    ):
        results = seed_all(
            project="p",
            values={},
            apply=True,
            use_env_fallback=False,
            placeholder_for_missing=True,
        )

    assert client.create_secret.call_count == 0
    assert client.add_secret_version.call_count == len(SECRETS)
    assert all(not r["created"] for r in results)
