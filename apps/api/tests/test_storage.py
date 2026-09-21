from pathlib import Path

from app.services.storage import LocalStorage


def test_local_storage_scopes_path_by_tenant() -> None:
    storage_path = LocalStorage(Path("uploads")).path_for("tenant-a", "document-a")
    assert storage_path == Path("uploads/tenant-a/document-a")
