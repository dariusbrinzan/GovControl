from pathlib import Path

import pytest

from insights_app.storage import LocalExportStorage


@pytest.mark.asyncio
async def test_local_storage_round_trip_and_path_confinement(tmp_path: Path) -> None:
    storage = LocalExportStorage(tmp_path)
    await storage.put("tenant/user/export.csv", b"content", "text/csv")
    assert await storage.get("tenant/user/export.csv") == b"content"
    with pytest.raises(ValueError, match="invalid storage key"):
        await storage.get("../outside")
    await storage.delete("tenant/user/export.csv")
    with pytest.raises(FileNotFoundError):
        await storage.get("tenant/user/export.csv")
