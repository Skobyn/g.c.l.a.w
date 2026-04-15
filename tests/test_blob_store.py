"""Tests for BlobStore — uses mocks on google.cloud.storage.Client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gclaw.shared_context.blob_store import BlobStore, _ext_from_mime


def test_ext_from_mime():
    assert _ext_from_mime("image/png") == ".png"
    assert _ext_from_mime("image/jpeg") == ".jpg"
    assert _ext_from_mime("text/markdown") == ".md"
    assert _ext_from_mime("text/plain") == ".txt"
    assert _ext_from_mime("application/json") == ".json"
    assert _ext_from_mime("weird/type") == ".bin"
    assert _ext_from_mime(None) == ".bin"


def test_upload_writes_correct_name_format():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    # reload succeeds → ensure_bucket does not try to create
    mock_bucket.reload.return_value = None
    mock_client.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="test-bucket")
        url = store.upload(
            namespace="feeds",
            entry_id="ctx_abc",
            data=b"hello",
            mime="text/markdown",
        )

    assert url.startswith("gs://test-bucket/feeds/")
    assert url.endswith("/ctx_abc.md")
    # Name passed to bucket.blob(name) must match the returned URL
    name_arg = mock_bucket.blob.call_args[0][0]
    assert url == f"gs://test-bucket/{name_arg}"
    mock_blob.upload_from_string.assert_called_once_with(b"hello", content_type="text/markdown")


def test_signed_url_validates_prefix():
    with patch("gclaw.shared_context.blob_store.storage.Client", MagicMock()):
        store = BlobStore(project="p", bucket_name="my-bucket")
    with pytest.raises(ValueError):
        store.signed_url("gs://other-bucket/foo")


def test_signed_url_happy_path():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.example/foo"
    mock_bucket.blob.return_value = mock_blob

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="my-bucket")
        url = store.signed_url("gs://my-bucket/a/b.md", minutes=5)

    assert url == "https://signed.example/foo"
    mock_bucket.blob.assert_called_with("a/b.md")


def test_ensure_bucket_idempotent():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.reload.return_value = None
    mock_client.bucket.return_value = mock_bucket

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="b")
        store.ensure_bucket()
        store.ensure_bucket()
        store.ensure_bucket()

    # reload only called once — subsequent ensure_bucket calls are no-ops.
    assert mock_bucket.reload.call_count == 1


def test_ensure_bucket_creates_when_missing():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.reload.side_effect = Exception("not found")
    mock_client.bucket.return_value = mock_bucket
    created = MagicMock()
    mock_client.create_bucket.return_value = created

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="b")
        store.ensure_bucket()

    mock_client.create_bucket.assert_called_once_with("b", location="us-central1")
    created.add_lifecycle_delete_rule.assert_called_once_with(age=30)
    created.patch.assert_called_once()


def test_ensure_bucket_tolerates_create_failure():
    """When create_bucket blows up (e.g. missing storage.admin), we must
    not crash — the next write surfaces a clear error instead."""
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.reload.side_effect = Exception("not found")
    mock_client.bucket.return_value = mock_bucket
    mock_client.create_bucket.side_effect = Exception("permission denied")

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="b")
        store.ensure_bucket()  # should not raise


def test_delete_validates_prefix():
    with patch("gclaw.shared_context.blob_store.storage.Client", MagicMock()):
        store = BlobStore(project="p", bucket_name="b")
    with pytest.raises(ValueError):
        store.delete("gs://other/file")


def test_namespace_with_slash_is_sanitized():
    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_bucket = MagicMock()
    mock_bucket.reload.return_value = None
    mock_client.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    with patch("gclaw.shared_context.blob_store.storage.Client", mock_client_cls):
        store = BlobStore(project="p", bucket_name="b")
        url = store.upload(
            namespace="research/scott",
            entry_id="ctx_x",
            data=b"data",
            mime="text/plain",
        )

    # Namespace slash must be normalised so the storage prefix has
    # exactly three components: <ns>/<date>/<id>.ext
    name = mock_bucket.blob.call_args[0][0]
    assert name.startswith("research_scott/")
    assert url.endswith("/ctx_x.txt")
