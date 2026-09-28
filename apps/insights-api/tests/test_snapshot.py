import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from insights_app.snapshot import ProjectionSnapshot


def record(module: str = "contracts") -> dict[str, object]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "module": module,
        "resource_type": "contract",
        "source_id": str(uuid.uuid4()),
        "identifier": "CTR-1",
        "source_url": f"/contracts/{uuid.uuid4()}",
        "source_version": 1,
        "source_event_at": datetime.now(UTC).isoformat(),
    }


def test_snapshot_validates_count_and_ownership() -> None:
    snapshot = ProjectionSnapshot.model_validate(
        {
            "schema_version": 1,
            "source": "contracts",
            "exported_at": datetime.now(UTC),
            "count": 1,
            "records": [record()],
        }
    )
    assert snapshot.count == 1
    with pytest.raises(ValidationError, match="another source"):
        ProjectionSnapshot.model_validate(
            {
                "schema_version": 1,
                "source": "contracts",
                "exported_at": datetime.now(UTC),
                "count": 1,
                "records": [record("legal")],
            }
        )


def test_snapshot_rejects_unexpected_sensitive_fields() -> None:
    value = record()
    value["document_content"] = "secret"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ProjectionSnapshot.model_validate(
            {
                "schema_version": 1,
                "source": "contracts",
                "exported_at": datetime.now(UTC),
                "count": 1,
                "records": [value],
            }
        )
