from datetime import date
from decimal import Decimal

from app.services.penalties import PenaltyCalculationType, calculate_penalty_exposure


def test_daily_penalty_exposure_is_derived_from_days() -> None:
    result = calculate_penalty_exposure(
        calculation_type=PenaltyCalculationType.DAILY_AMOUNT,
        start_date=date(2026, 1, 1),
        as_of_date=date(2026, 1, 6),
        daily_amount=Decimal("500"),
    )
    assert result == Decimal("2500")


def test_penalty_does_not_extend_past_end_date() -> None:
    result = calculate_penalty_exposure(
        calculation_type=PenaltyCalculationType.DAILY_AMOUNT,
        start_date=date(2026, 1, 1),
        as_of_date=date(2026, 1, 20),
        end_date=date(2026, 1, 4),
        daily_amount=Decimal("10"),
    )
    assert result == Decimal("30")
