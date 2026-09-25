import os
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings


class StorageError(Exception):
    """A storage operation could not be completed."""


class DocumentStorage(Protocol):
    def write(self, tenant_id: str, document_id: str, content: bytes) -> str: ...

    def read_bytes(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...

    def check(self) -> None: ...


class LocalStorage:
    """Filesystem adapter for direct development and isolated tests."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, tenant_id: str, document_id: str) -> Path:
        return self.root / tenant_id / document_id

    def write(self, tenant_id: str, document_id: str, content: bytes) -> str:
        path = self.path_for(tenant_id, document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path.relative_to(self.root))

    def read(self, storage_key: str) -> Path:
        root = self.root.resolve()
        path = (root / storage_key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def read_bytes(self, storage_key: str) -> bytes:
        return self.read(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        try:
            self.read(storage_key).unlink()
        except FileNotFoundError:
            return

    def check(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Local document storage is unavailable.") from exc
        if not self.root.is_dir() or not os.access(self.root, os.R_OK | os.W_OK):
            raise StorageError("Local document storage is unavailable.")


class S3Storage:
    """S3-compatible document storage with tenant-scoped object keys."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self.bucket = bucket
        self._bucket_ready = False
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @staticmethod
    def key_for(tenant_id: str, document_id: str) -> str:
        return f"{tenant_id}/{document_id}"

    @staticmethod
    def _validated_key(storage_key: str) -> str:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or ".." in key.parts or len(key.parts) != 2:
            raise StorageError("Invalid document storage key.")
        return str(key)

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code not in {403, 404}:
                raise StorageError("Object storage is unavailable.") from exc
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as create_exc:
                error_code = create_exc.response.get("Error", {}).get("Code")
                if error_code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise StorageError(
                        "Object storage bucket could not be created."
                    ) from create_exc
            except BotoCoreError as create_exc:
                raise StorageError("Object storage bucket could not be created.") from create_exc
        except BotoCoreError as exc:
            raise StorageError("Object storage is unavailable.") from exc
        self._bucket_ready = True

    def write(self, tenant_id: str, document_id: str, content: bytes) -> str:
        key = self.key_for(tenant_id, document_id)
        self._ensure_bucket()
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content)
        except BotoCoreError as exc:
            raise StorageError("Document could not be stored.") from exc
        return key

    def read_bytes(self, storage_key: str) -> bytes:
        key = self._validated_key(storage_key)
        self._ensure_bucket()
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return bytes(response["Body"].read())
        except BotoCoreError as exc:
            raise StorageError("Document could not be read.") from exc

    def delete(self, storage_key: str) -> None:
        key = self._validated_key(storage_key)
        self._ensure_bucket()
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except BotoCoreError as exc:
            raise StorageError("Document could not be deleted.") from exc

    def check(self) -> None:
        self._ensure_bucket()


@lru_cache
def configured_storage(
    backend: str,
    local_path: str,
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    region: str,
) -> DocumentStorage:
    if backend == "s3":
        return S3Storage(
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            region=region,
        )
    return LocalStorage(Path(local_path))


def storage_from_settings(settings: Settings) -> DocumentStorage:
    return configured_storage(
        settings.document_storage_backend,
        str(settings.document_storage_path),
        settings.s3_endpoint_url,
        settings.s3_access_key.get_secret_value(),
        settings.s3_secret_key.get_secret_value(),
        settings.s3_bucket,
        settings.s3_region,
    )
