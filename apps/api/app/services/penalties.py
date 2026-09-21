from datetime import date
from decimal import Decimal
from enum import StrEnum


class PenaltyCalculationType(StrEnum):
    DAILY_AMOUNT = "DAILY_AMOUNT"
    PERCENTAGE_OF_BASE = "PERCENTAGE_OF_BASE"


def calculate_penalty_exposure(
    *,
    calculation_type: PenaltyCalculationType,
    start_date: date,
    as_of_date: date,
    daily_amount: Decimal | None = None,
    percentage: Decimal | None = None,
    base_value: Decimal | None = None,
    end_date: date | None = None,
) -> Decimal:
    """Calculate exposure from a rule; never persist this derived amount as source data."""
    effective_end = min(as_of_date, end_date) if end_date is not None else as_of_date
    days = max(0, (effective_end - start_date).days)
    if calculation_type == PenaltyCalculationType.DAILY_AMOUNT:
        if daily_amount is None:
            raise ValueError("daily_amount is required")
        return daily_amount * days
    if percentage is None or base_value is None:
        raise ValueError("percentage and base_value are required")
    return (percentage / Decimal("100")) * base_value * days
