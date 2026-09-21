from datetime import date

from app.models.legal import ObligationStatus
from app.services.deadlines import DeadlineState, deadline_state, overdue_days


def test_active_past_due_obligation_is_overdue() -> None:
    today = date(2026, 9, 21)
    assert deadline_state(date(2026, 9, 18), ObligationStatus.OPEN, today) == DeadlineState.OVERDUE
    assert overdue_days(date(2026, 9, 18), ObligationStatus.OPEN, today) == 3


def test_completed_obligation_is_not_overdue() -> None:
    assert (
        deadline_state(date(2026, 9, 18), ObligationStatus.COMPLETED, date(2026, 9, 21))
        == DeadlineState.NONE
    )
