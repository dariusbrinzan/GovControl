import uuid
from io import BytesIO

import boto3  # type: ignore[import-untyped]
import pytest
from moto import mock_aws

from documents_app.storage import S3Storage, StorageError


@mock_aws
def test_s3_storage_stream_round_trip_and_generated_key() -> None:
    storage = S3Storage.__new__(S3Storage)
    storage.bucket = "documents-test"
    storage._bucket_ready = False
    storage.client = boto3.client("s3", region_name="us-east-1")
    tenant_id, document_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    key = storage.upload(
        tenant_id, document_id, version_id, BytesIO(b"document content"), "text/plain"
    )

    assert key == f"{tenant_id}/{document_id}/{version_id}"
    assert b"".join(storage.iter_bytes(key, chunk_size=4)) == b"document content"
    target = BytesIO()
    storage.download_to(key, target)
    assert target.read() == b"document content"
    storage.delete(key)


@pytest.mark.parametrize("key", ["../secret", "/absolute/path", "tenant/document", "a/b/c"])
def test_storage_rejects_caller_controlled_keys(key: str) -> None:
    with pytest.raises(StorageError):
        S3Storage.validate_key(key)


def test_storage_maps_object_store_outage_to_storage_error() -> None:
    storage = S3Storage.__new__(S3Storage)
    storage.bucket = "documents-test"
    storage._bucket_ready = True
    storage.client = type(
        "UnavailableClient",
        (),
        {"upload_fileobj": lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline"))},
    )()

    with pytest.raises(StorageError, match="could not be stored"):
        storage.upload(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            BytesIO(b"document"),
            "text/plain",
        )
