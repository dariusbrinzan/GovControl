import uuid

import pytest
from pydantic import ValidationError

from insights_app.models import SavedReport
from insights_app.schemas import ReportCreate, UserContext
from insights_app.service import report_visible


def user(tenant_id: uuid.UUID, user_id: uuid.UUID, *roles: str) -> UserContext:
    return UserContext(
        id=user_id,
        tenant_id=tenant_id,
        email="officer@example.test",
        display_name="Officer",
        roles=list(roles),
        permissions=["insights.report"],
    )


def test_report_definition_rejects_arbitrary_columns_and_filters() -> None:
    with pytest.raises(ValidationError, match="allowlist"):
        ReportCreate(name="Unsafe", resource_type="case", columns=["password_hash"])
    with pytest.raises(ValidationError, match="unsupported fields"):
        ReportCreate(
            name="Unsafe SQL",
            resource_type="case",
            columns=["status"],
            filters={"sql": "DROP TABLE projection_resources"},
        )


def test_report_filters_are_typed_and_date_range_is_validated() -> None:
    department_id = uuid.uuid4()
    report = ReportCreate(
        name="Due cases",
        resource_type="case",
        columns=["identifier", "due_at"],
        filters={
            "module": "legal",
            "department_id": department_id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )
    assert report.filters["department_id"] == str(department_id)
    assert report.filters["date_from"] == "2026-01-01"

    with pytest.raises(ValidationError, match="unsupported module"):
        ReportCreate(
            name="Invalid module",
            resource_type="case",
            columns=["status"],
            filters={"module": "unknown"},
        )
    with pytest.raises(ValidationError, match="date_from must precede date_to"):
        ReportCreate(
            name="Invalid interval",
            resource_type="case",
            columns=["status"],
            filters={"date_from": "2026-02-01", "date_to": "2026-01-01"},
        )


def test_report_visibility_is_tenant_and_owner_scoped() -> None:
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    report = SavedReport(
        tenant_id=tenant_id,
        owner_user_id=owner_id,
        name="Cases",
        resource_type="case",
        filters={},
        columns=["status"],
        sort=[],
        shared_with_roles=["auditor"],
    )
    assert report_visible(report, user(tenant_id, owner_id))
    assert report_visible(report, user(tenant_id, uuid.uuid4(), "auditor"))
    assert not report_visible(report, user(uuid.uuid4(), owner_id, "auditor"))
    assert not report_visible(report, user(tenant_id, uuid.uuid4(), "legal_officer"))
