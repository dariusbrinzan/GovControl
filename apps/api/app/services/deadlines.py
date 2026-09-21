from datetime import date
from enum import StrEnum

from app.models.legal import ObligationStatus


class DeadlineState(StrEnum):
    NONE = "NONE"
    UPCOMING = "UPCOMING"
    DUE_TODAY = "DUE_TODAY"
    OVERDUE = "OVERDUE"


def deadline_state(due_date: date | None, status: ObligationStatus, today: date) -> DeadlineState:
    if due_date is None or status in {ObligationStatus.COMPLETED, ObligationStatus.CANCELLED}:
        return DeadlineState.NONE
    if due_date < today:
        return DeadlineState.OVERDUE
    if due_date == today:
        return DeadlineState.DUE_TODAY
    return DeadlineState.UPCOMING


def overdue_days(due_date: date | None, status: ObligationStatus, today: date) -> int:
    if deadline_state(due_date, status, today) != DeadlineState.OVERDUE or due_date is None:
        return 0
    return (today - due_date).days
