from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.services.storage import LocalStorage, S3Storage, StorageError


def test_local_storage_scopes_path_by_tenant() -> None:
    storage_path = LocalStorage(Path("uploads")).path_for("tenant-a", "document-a")
    assert storage_path == Path("uploads/tenant-a/document-a")


def test_local_storage_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = storage.write("tenant-a", "document-a", b"document content")

    assert storage.read(key).read_bytes() == b"document content"

    storage.delete(key)
    assert not (tmp_path / key).exists()


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class FakeS3Client:
    def __init__(self) -> None:
        self.bucket_exists = False
        self.objects: dict[str, bytes] = {}

    def head_bucket(self, **_: Any) -> None:
        if not self.bucket_exists:
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadBucket",
            )

    def create_bucket(self, **_: Any) -> None:
        self.bucket_exists = True

    def put_object(self, *, Key: str, Body: bytes, **_: Any) -> None:
        self.objects[Key] = Body

    def get_object(self, *, Key: str, **_: Any) -> dict[str, FakeBody]:
        return {"Body": FakeBody(self.objects[Key])}

    def delete_object(self, *, Key: str, **_: Any) -> None:
        self.objects.pop(Key, None)


def test_s3_storage_round_trip_creates_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeS3Client()
    monkeypatch.setattr("app.services.storage.boto3.client", lambda *args, **kwargs: client)
    storage = S3Storage(
        endpoint_url="http://object-storage:8333",
        access_key="test",
        secret_key="test",
        bucket="documents",
        region="us-east-1",
    )

    key = storage.write("tenant-a", "document-a", b"document content")

    assert key == "tenant-a/document-a"
    assert storage.read_bytes(key) == b"document content"
    storage.delete(key)
    assert client.objects == {}


def test_s3_storage_rejects_unsafe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.storage.boto3.client", lambda *args, **kwargs: FakeS3Client()
    )
    storage = S3Storage(
        endpoint_url="http://object-storage:8333",
        access_key="test",
        secret_key="test",
        bucket="documents",
        region="us-east-1",
    )

    with pytest.raises(StorageError):
        storage.read_bytes("../another-tenant/document-a")


def test_s3_storage_translates_endpoint_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeS3Client()

    def unavailable(**_: Any) -> None:
        raise EndpointConnectionError(endpoint_url="http://object-storage:8333")

    client.head_bucket = unavailable  # type: ignore[method-assign]
    monkeypatch.setattr("app.services.storage.boto3.client", lambda *args, **kwargs: client)
    storage = S3Storage(
        endpoint_url="http://object-storage:8333",
        access_key="test",
        secret_key="test",
        bucket="documents",
        region="us-east-1",
    )

    with pytest.raises(StorageError):
        storage.write("tenant-a", "document-a", b"document content")
