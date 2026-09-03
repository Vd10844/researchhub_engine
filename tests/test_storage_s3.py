"""S3 / storage backend tests with moto (validation-plan 1.2).

The offline suite uses fake/`MagicMock` storage, so the real ``S3Storage``
class (boto3 put/get/delete/exists) is never exercised. These tests run the
actual object-store backend against AWS-in-a-box (moto), proving the
upload→read-back round-trip works and that provenance (sha256) is stable
across a put/get cycle. The upload-failure→`failed` doc branch is already
covered at the adapter level in test_evidence_source.py; here we pin the
storage backend itself.
"""
from __future__ import annotations

import hashlib

import boto3
import pytest
from app.services import storage as storage_mod
from moto import mock_aws


@pytest.fixture
def s3_backend(monkeypatch):
    with mock_aws():
        bucket = "test-artifacts"
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        monkeypatch.setenv("QP_STORAGE_BACKEND", "s3")
        monkeypatch.setenv("QP_S3_BUCKET", bucket)
        monkeypatch.setenv("QP_S3_PREFIX", "quickplot")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
        s = storage_mod.S3Storage()
        s.bucket = bucket  # ensure the fixture bucket is used
        yield s


def test_put_get_roundtrip(s3_backend):
    key = "org/order/doc1.pdf"
    data = b"%PDF-1.4 fake pdf payload"
    s3_backend.put(key, data)
    assert s3_backend.get(key) == data
    assert s3_backend.exists(key) is True


def test_exists_false_for_missing_key(s3_backend):
    assert s3_backend.exists("org/order/does-not-exist.pdf") is False


def test_delete_removes_object(s3_backend):
    key = "org/order/gone.pdf"
    s3_backend.put(key, b"x")
    assert s3_backend.exists(key) is True
    s3_backend.delete(key)
    assert s3_backend.exists(key) is False


def test_copy_in_persists_bytes_and_size(s3_backend, tmp_path):
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"hello s3")
    key = "org/order/doc.pdf"
    size = s3_backend.copy_in(key, src)
    assert size == len(b"hello s3")
    assert s3_backend.get(key) == b"hello s3"


def test_sha256_is_stable_across_put_get(s3_backend):
    data = b"provenance-check-bytes"
    s3_backend.put("org/order/p.pdf", data)
    got = s3_backend.get("org/order/p.pdf")
    assert hashlib.sha256(got).hexdigest() == hashlib.sha256(data).hexdigest()


def test_prefix_is_applied_to_keys(s3_backend):
    key = "org/order/p.pdf"
    s3_backend.put(key, b"z")

    s3 = boto3.client("s3", region_name="us-east-1")
    # The prefixed key is what actually lands in the bucket.
    obj = s3.get_object(Bucket=s3_backend.bucket, Key="quickplot/org/order/p.pdf")
    assert obj["Body"].read() == b"z"
