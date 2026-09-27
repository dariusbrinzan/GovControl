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
