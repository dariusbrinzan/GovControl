import uuid
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import IO, Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from documents_app.config import Settings


class StorageError(Exception):
    pass


class S3Storage:
    """Process-scoped S3 client; object keys are generated only from server UUIDs."""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self._bucket_ready = False
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                max_pool_connections=32,
                connect_timeout=5,
                read_timeout=60,
            ),
        )

    @staticmethod
    def key_for(tenant_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID) -> str:
        return f"{tenant_id}/{document_id}/{version_id}"

    @staticmethod
    def validate_key(storage_key: str) -> str:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or ".." in key.parts or len(key.parts) != 3:
            raise StorageError("Invalid object key.")
        try:
            for part in key.parts:
                uuid.UUID(part)
        except ValueError as exc:
            raise StorageError("Invalid object key.") from exc
        return str(key)

    def check(self) -> None:
        self._ensure_bucket()
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Object storage is unavailable.") from exc

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
                code = create_exc.response.get("Error", {}).get("Code")
                if code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise StorageError(
                        "Object storage bucket could not be created."
                    ) from create_exc
            except BotoCoreError as create_exc:
                raise StorageError("Object storage bucket could not be created.") from create_exc
        except BotoCoreError as exc:
            raise StorageError("Object storage is unavailable.") from exc
        self._bucket_ready = True

    def upload(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        source: IO[bytes],
        content_type: str,
    ) -> str:
        self._ensure_bucket()
        key = self.key_for(tenant_id, document_id, version_id)
        source.seek(0)
        try:
            self.client.upload_fileobj(
                source,
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("Document could not be stored.") from exc
        return key

    def iter_bytes(self, storage_key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        key = self.validate_key(storage_key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                yield from body.iter_chunks(chunk_size=chunk_size)
            finally:
                body.close()
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("Document could not be read.") from exc

    def download_to(self, storage_key: str, target: IO[bytes]) -> None:
        key = self.validate_key(storage_key)
        target.seek(0)
        target.truncate(0)
        try:
            self.client.download_fileobj(self.bucket, key, target)
            target.seek(0)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("Document could not be read.") from exc

    def delete(self, storage_key: str) -> None:
        key = self.validate_key(storage_key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Document could not be deleted.") from exc
