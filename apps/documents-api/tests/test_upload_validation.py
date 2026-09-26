import asyncio
import hashlib
from io import BytesIO
from typing import Any, cast

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from documents_app.config import Settings
from documents_app.service import normalize_filename, spool_upload


def settings(max_size: int = 1024) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:password@localhost/test",
        max_upload_size_bytes=max_size,
        upload_chunk_size_bytes=64 * 1024,
    )


def upload(filename: str, content: bytes, content_type: str = "text/plain") -> UploadFile:
    return UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_filename_rejects_path_traversal_and_disallowed_extension() -> None:
    with pytest.raises(HTTPException) as traversal:
        normalize_filename("../secret.txt", frozenset({".txt"}))
    assert traversal.value.status_code == 422
    with pytest.raises(HTTPException) as extension:
        normalize_filename("payload.exe", frozenset({".txt"}))
    assert extension.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_is_spooled_and_checksum_is_computed() -> None:
    content = b"verified document bytes"
    target, size, checksum, original, safe, content_type = await spool_upload(
        upload("decizie.txt", content), settings()
    )
    try:
        assert target.read() == content
        assert size == len(content)
        assert checksum == hashlib.sha256(content).hexdigest()
        assert original == safe == "decizie.txt"
        assert content_type == "text/plain"
    finally:
        target.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate", "expected_status"),
    [
        (upload("empty.txt", b""), 422),
        (upload("large.txt", b"12345"), 413),
        (upload("image.txt", b"data", "application/x-msdownload"), 415),
    ],
)
async def test_upload_rejects_empty_oversize_and_invalid_mime(
    candidate: UploadFile, expected_status: int
) -> None:
    with pytest.raises(HTTPException) as exception_info:
        await spool_upload(candidate, settings(max_size=4))
    assert exception_info.value.status_code == expected_status


@pytest.mark.asyncio
async def test_near_limit_upload_rolls_to_disk_instead_of_retaining_all_bytes() -> None:
    content = b"a" * (3 * 1024 * 1024)
    target, size, checksum, *_ = await spool_upload(
        upload("near-limit.txt", content), settings(max_size=3 * 1024 * 1024)
    )
    try:
        assert size == len(content)
        assert checksum == hashlib.sha256(content).hexdigest()
        assert cast(Any, target)._rolled is True
    finally:
        target.close()


@pytest.mark.asyncio
async def test_concurrent_stream_spooling_keeps_uploads_isolated() -> None:
    contents = [f"parallel-document-{index}".encode() * 4096 for index in range(8)]
    results = await asyncio.gather(
        *(
            spool_upload(upload(f"parallel-{index}.txt", content), settings(512 * 1024))
            for index, content in enumerate(contents)
        )
    )
    try:
        assert [result[2] for result in results] == [
            hashlib.sha256(content).hexdigest() for content in contents
        ]
    finally:
        for result in results:
            result[0].close()
