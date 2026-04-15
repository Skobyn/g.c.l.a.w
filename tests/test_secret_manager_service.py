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
    resp.name = "projects/p/secrets/watson-foo/versions/3"
    client.add_secret_version.return_value = resp
    return client


def test_normalize_name_adds_prefix():
    assert SecretManagerService.normalize_name("openai-key") == "watson-openai-key"


def test_normalize_name_keeps_prefix():
    assert (
        SecretManagerService.normalize_name("watson-openai-key")
        == "watson-openai-key"
    )


def test_normalize_name_lowercases_and_strips():
    assert (
        SecretManagerService.normalize_name("OpenAI_API KEY!")
        == "watson-openai-api-key"
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

    assert result["name"] == "watson-openai-key"
    assert result["path"] == "projects/p/secrets/watson-openai-key/versions/latest"
    assert result["created_secret"] is True
    assert result["version_id"] == "3"

    # create_secret invoked once with correct labels
    create_req = client.create_secret.call_args.kwargs["request"]
    assert create_req["parent"] == "projects/p"
    assert create_req["secret_id"] == "watson-openai-key"
    assert create_req["secret"]["labels"] == {
        "app": "watson",
        "kind": "api-key",
    }
    assert create_req["secret"]["replication"] == {"automatic": {}}

    # add_secret_version invoked with bytes payload
    ver_req = client.add_secret_version.call_args.kwargs["request"]
    assert ver_req["parent"] == "projects/p/secrets/watson-openai-key"
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
    assert result["name"] == "watson-openai-key"
    assert result["version_id"] == "3"


def test_permission_denied_on_write_surfaces_helpful_message():
    client = _fake_client()
    client.get_secret.side_effect = _PermDeniedExc("nope")
    svc = SecretManagerService(project="p")

    with _install_fake_gcloud(client):
        with pytest.raises(SecretManagerPermissionError) as exc:
            svc.write(name="openai-key", value="sk")

    assert "roles/secretmanager" in str(exc.value)


def test_list_returns_watson_prefixed_and_labeled_secrets():
    """list_gclaw_secrets unions labelled secrets with anything
    prefixed `watson-` — so shared watson secrets created outside
    GClaw still show up in the admin list."""
    client = _fake_client()

    # matches via name prefix
    prefixed = MagicMock()
    prefixed.name = "projects/p/secrets/watson-openai-key"
    prefixed.labels = {}

    # matches via label
    labelled = MagicMock()
    labelled.name = "projects/p/secrets/some-random-name"
    labelled.labels = {"app": "watson", "kind": "api-key"}

    # excluded — neither prefix nor our label
    unrelated = MagicMock()
    unrelated.name = "projects/p/secrets/unrelated-thing"
    unrelated.labels = {"app": "other-tool"}

    client.list_secrets.return_value = [prefixed, labelled, unrelated]

    ts = datetime(2026, 4, 14, tzinfo=timezone.utc)
    ver = MagicMock()
    ver.create_time = ts
    client.get_secret_version.return_value = ver

    svc = SecretManagerService(project="p")
    with _install_fake_gcloud(client):
        items = svc.list_gclaw_secrets()

    # No server-side filter — we page all secrets and filter client-side.
    list_req = client.list_secrets.call_args.kwargs["request"]
    assert "filter" not in list_req

    names = {i["name"] for i in items}
    assert names == {"watson-openai-key", "some-random-name"}
    openai = next(i for i in items if i["name"] == "watson-openai-key")
    assert (
        openai["path"]
        == "projects/p/secrets/watson-openai-key/versions/latest"
    )
    assert openai["latest_version_created_at"] == ts.isoformat()


def test_project_required():
    with pytest.raises(ValueError):
        SecretManagerService(project="")
