import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from openpyxl import load_workbook

from insights_app.exports import cleanup_expired_exports, render_csv, render_xlsx, safe_cell
from insights_app.models import AuditEvent, ExportArtifact


def test_spreadsheet_formula_injection_is_neutralized() -> None:
    for value in ("=1+1", "+SUM(A1:A2)", "-2+3", "@cmd", "  =hidden"):
        assert str(safe_cell(value)).startswith("'")
    assert safe_cell("ordinary text") == "ordinary text"


def test_csv_and_xlsx_exports_are_valid() -> None:
    rows = [["CASE-1", "=1+1"]]
    csv_bytes = render_csv(["identifier", "display_label"], rows)
    parsed = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert parsed[1] == ["CASE-1", "'=1+1"]

    workbook = load_workbook(io.BytesIO(render_xlsx(["identifier", "display_label"], rows)))
    assert workbook.active["B2"].value == "'=1+1"


@pytest.mark.asyncio
async def test_expired_export_removes_object_and_records_audit() -> None:
    artifact = ExportArtifact(
        tenant_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        format="csv",
        status="SUCCEEDED",
        storage_key="tenant/user/export.csv",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    class ScalarResult:
        def all(self) -> list[ExportArtifact]:
            return [artifact]

    class Session:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.deleted: list[object] = []
            self.committed = False

        async def scalars(self, statement: object) -> ScalarResult:
            del statement
            return ScalarResult()

        def add(self, value: object) -> None:
            self.added.append(value)

        async def delete(self, value: object) -> None:
            self.deleted.append(value)

        async def commit(self) -> None:
            self.committed = True

    class Storage:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete(self, key: str) -> None:
            self.deleted.append(key)

    session = Session()
    storage = Storage()
    count = await cleanup_expired_exports(session, storage, datetime.now(UTC))  # type: ignore[arg-type]

    assert count == 1
    assert storage.deleted == ["tenant/user/export.csv"]
    assert session.deleted == [artifact]
    assert session.committed
    assert any(isinstance(item, AuditEvent) for item in session.added)
