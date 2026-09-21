from pathlib import Path

from app.services.storage import LocalStorage


def test_local_storage_scopes_path_by_tenant() -> None:
    storage_path = LocalStorage(Path("uploads")).path_for("tenant-a", "document-a")
    assert storage_path == Path("uploads/tenant-a/document-a")


def test_local_storage_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    key = storage.write("tenant-a", "document-a", b"document content")

    assert storage.read(key).read_bytes() == b"document content"

    storage.delete(key)
    assert not (tmp_path / key).exists()
