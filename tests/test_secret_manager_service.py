"""Tests for SecretManagerService wrapper."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from gclaw.catalog.secret_manager import (
    SecretManagerNotFoundError,
    SecretManagerPermissionError,
    SecretManagerService,
)


class _NotFoundExc(Exception):
    pass


class _PermDeniedExc(Exception):
    pass


class _FakeGCloudCtx:
    """Install fake ``google.cloud.secretmanager`` + force
    ``google.api_core.exceptions`` to expose our sentinel exception
    classes, so SecretManagerService's lazy imports see them regardless
    of what previous tests left in ``sys.modules``.
    """

    def __init__(self, client):
        self.client = client
        self._patches: list = []
        self._saved: dict = {}

    def __enter__(self):
        import google.cloud as gcloud_pkg

        fake_sm_mod = types.ModuleType("google.cloud.secretmanager")
        fake_sm_mod.SecretManagerServiceClient = lambda: self.client  # type: ignore

        p1 = patch.dict(
            sys.modules,
            {"google.cloud.secretmanager": fake_sm_mod},
        )
        p2 = patch.object(gcloud_pkg, "secretmanager", fake_sm_mod, create=True)
        self._patches = [p1, p2]
        for p in self._patches:
            p.start()

        # Force the real google.api_core.exceptions module (if loaded) to
        # expose our sentinel classes as NotFound/PermissionDenied/Forbidden
        # so isinstance checks in SecretManagerService._map_exc match.
        try:
            from google.api_core import exceptions as gexc  # type: ignore
        except Exception:
            gexc_mod = types.ModuleType("google.api_core.exceptions")
            sys.modules["google.api_core.exceptions"] = gexc_mod
            gexc = gexc_mod
        for attr in ("NotFound", "PermissionDenied", "Forbidden"):
            self._saved[attr] = getattr(gexc, attr, None)
        gexc.NotFound = _NotFoundExc  # type: ignore[attr-defined]
        gexc.PermissionDenied = _PermDeniedExc  # type: ignore[attr-defined]
        gexc.Forbidden = _PermDeniedExc  # type: ignore[attr-defined]
        self._gexc = gexc
        return self

    def __exit__(self, *exc):
        for attr, val in self._saved.items():
            if val is None:
                try:
                    delattr(self._gexc, attr)
                except AttributeError:
                    pass
            else:
                setattr(self._gexc, attr, val)
        for p in reversed(self._patches):
            p.stop()
        return False


def _install_fake_gcloud(client):
    return _FakeGCloudCtx(client)


def _fake_client():
    client = MagicMock()
    # Default: get_secret raises NotFound (secret missing)
    client.get_secret.side_effect = _NotFoundExc("missing")
    # add_secret_version returns an object with .name
    resp = MagicMock()
    resp.name = "projects/p/secrets/gclaw-foo/versions/3"
    client.add_secret_version.return_value = resp
    return client


def test_normalize_name_adds_prefix():
    assert SecretManagerService.normalize_name("openai-key") == "gclaw-openai-key"


def test_normalize_name_keeps_prefix():
    assert (
        SecretManagerService.normalize_name("gclaw-openai-key")
        == "gclaw-openai-key"
    )


def test_normalize_name_lowercases_and_strips():
    assert (
        SecretManagerService.normalize_name("OpenAI_API KEY!")
        == "gclaw-openai-api-key"
    )


def test_normalize_name_rejects_empty():
    with pytest.raises(ValueError):
        SecretManagerService.normalize_name("")
    with pytest.raises(ValueError):
        SecretManagerService.normalize_name("   ")


def test_write_creates_secret_then_adds_version():
    client = _fake_client()
    svc = SecretManagerService(project="p")

    with _install_fake_gcloud(client):
        result = svc.write(name="openai-key", value="sk-abc")

    assert result["name"] == "gclaw-openai-key"
    assert result["path"] == "projects/p/secrets/gclaw-openai-key/versions/latest"
    assert result["created_secret"] is True
    assert result["version_id"] == "3"

    # create_secret invoked once with correct labels
    create_req = client.create_secret.call_args.kwargs["request"]
    assert create_req["parent"] == "projects/p"
    assert create_req["secret_id"] == "gclaw-openai-key"
    assert create_req["secret"]["labels"] == {
        "app": "gclaw",
        "kind": "api-key",
    }
    assert create_req["secret"]["replication"] == {"automatic": {}}

    # add_secret_version invoked with bytes payload
    ver_req = client.add_secret_version.call_args.kwargs["request"]
    assert ver_req["parent"] == "projects/p/secrets/gclaw-openai-key"
    assert ver_req["payload"]["data"] == b"sk-abc"


def test_write_skips_create_if_exists():
    client = _fake_client()
    # get_secret succeeds → secret exists
    client.get_secret.side_effect = None
    client.get_secret.return_value = MagicMock()

    svc = SecretManagerService(project="p")
    with _install_fake_gcloud(client):
        result = svc.write(name="openai-key", value="sk-abc")

    assert result["created_secret"] is False
    client.create_secret.assert_not_called()
    assert client.add_secret_version.called


def test_write_404_when_create_disabled_and_missing():
    client = _fake_client()  # get_secret raises NotFound
    svc = SecretManagerService(project="p")

    with _install_fake_gcloud(client):
        with pytest.raises(SecretManagerNotFoundError):
            svc.write(
                name="openai-key",
                value="sk",
                create_if_missing=False,
            )


def test_rotate_requires_existing_secret():
    client = _fake_client()  # get_secret raises NotFound
    svc = SecretManagerService(project="p")

    with _install_fake_gcloud(client):
        with pytest.raises(SecretManagerNotFoundError):
            svc.rotate(name="openai-key", value="sk-new")


def test_rotate_adds_version_only():
    client = _fake_client()
    client.get_secret.side_effect = None
    client.get_secret.return_value = MagicMock()

    svc = SecretManagerService(project="p")
    with _install_fake_gcloud(client):
        result = svc.rotate(name="openai-key", value="sk-new")

    client.create_secret.assert_not_called()
    assert result["name"] == "gclaw-openai-key"
    assert result["version_id"] == "3"


def test_permission_denied_on_write_surfaces_helpful_message():
    client = _fake_client()
    client.get_secret.side_effect = _PermDeniedExc("nope")
    svc = SecretManagerService(project="p")

    with _install_fake_gcloud(client):
        with pytest.raises(SecretManagerPermissionError) as exc:
            svc.write(name="openai-key", value="sk")

    assert "roles/secretmanager" in str(exc.value)


def test_list_filters_by_label_and_returns_metadata():
    client = _fake_client()

    sec = MagicMock()
    sec.name = "projects/p/secrets/gclaw-openai-key"
    other = MagicMock()
    other.name = "projects/p/secrets/gclaw-anthropic-key"
    client.list_secrets.return_value = [sec, other]

    ts = datetime(2026, 4, 14, tzinfo=timezone.utc)
    ver = MagicMock()
    ver.create_time = ts
    client.get_secret_version.return_value = ver

    svc = SecretManagerService(project="p")
    with _install_fake_gcloud(client):
        items = svc.list_gclaw_secrets()

    list_req = client.list_secrets.call_args.kwargs["request"]
    assert list_req["filter"] == "labels.app=gclaw"

    assert len(items) == 2
    assert items[0]["name"] == "gclaw-openai-key"
    assert (
        items[0]["path"]
        == "projects/p/secrets/gclaw-openai-key/versions/latest"
    )
    assert items[0]["latest_version_created_at"] == ts.isoformat()


def test_project_required():
    with pytest.raises(ValueError):
        SecretManagerService(project="")
