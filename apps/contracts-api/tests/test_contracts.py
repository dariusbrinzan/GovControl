import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from contracts_app.config import Settings
from contracts_app.models import (
    ContractStatus,
    MilestoneStatus,
    ObligationStatus,
    OutboxEvent,
    PaymentStatus,
)
from contracts_app.observability import request_id_from_header
from contracts_app.schemas import ContractCreate
from contracts_app.service import (
    ALLOWED_TRANSITIONS,
    MILESTONE_TRANSITIONS,
    OBLIGATION_TRANSITIONS,
    PAYMENT_TRANSITIONS,
)
from contracts_app.worker import event_envelope


def valid_contract() -> ContractCreate:
    return ContractCreate(
        contract_number="CTR-001",
        title="Servicii de mentenanță",
        value=Decimal("125000.00"),
        currency="ron",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )


def test_contract_normalizes_currency() -> None:
    assert valid_contract().currency == "RON"


def test_contract_rejects_invalid_period() -> None:
    with pytest.raises(ValidationError):
        ContractCreate(
            contract_number="CTR-002",
            title="Invalid",
            value=Decimal("1"),
            start_date=date(2026, 12, 31),
            end_date=date(2026, 1, 1),
        )


def test_terminal_contract_states_cannot_transition() -> None:
    assert ALLOWED_TRANSITIONS[ContractStatus.COMPLETED] == set()
    assert ALLOWED_TRANSITIONS[ContractStatus.TERMINATED] == set()
    assert ContractStatus.ACTIVE in ALLOWED_TRANSITIONS[ContractStatus.IN_REVIEW]


def test_related_workflow_transitions_are_terminal_after_completion() -> None:
    assert MILESTONE_TRANSITIONS[MilestoneStatus.COMPLETED] == set()
    assert OBLIGATION_TRANSITIONS[ObligationStatus.COMPLETED] == set()
    assert PAYMENT_TRANSITIONS[PaymentStatus.PAID] == set()
    assert PaymentStatus.PAID in PAYMENT_TRANSITIONS[PaymentStatus.APPROVED]


def test_outbox_envelope_contains_idempotency_and_tenant_context() -> None:
    event = OutboxEvent(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        event_type="contracts.contract.created.v1",
        aggregate_type="Contract",
        aggregate_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        payload={"contract_number": "CTR-001"},
        created_at=datetime(2026, 9, 25, tzinfo=UTC),
    )
    envelope = event_envelope(event)
    assert envelope["id"] == "00000000-0000-0000-0000-000000000001"
    assert envelope["tenant_id"] == "00000000-0000-0000-0000-000000000002"
    assert envelope["type"].endswith(".v1")


def test_production_requires_internal_service_secret() -> None:
    with pytest.raises(ValidationError, match="INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            contracts_database_url="postgresql+asyncpg://user:password@localhost:5432/test",
            internal_service_token=None,
        )


def test_request_id_accepts_uuid_and_replaces_invalid_value() -> None:
    request_id = "41ded179-322f-4382-9073-75f1610774e5"

    assert str(request_id_from_header(request_id)) == request_id
    assert str(request_id_from_header("not-a-uuid")) != "not-a-uuid"
