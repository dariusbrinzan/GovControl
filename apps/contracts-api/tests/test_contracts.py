from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from contracts_app.models import ContractStatus
from contracts_app.schemas import ContractCreate
from contracts_app.service import ALLOWED_TRANSITIONS


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
