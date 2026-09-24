import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Join

from app.models.department import Department
from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    EnforcementStatus,
    LegalCase,
    LegalObligation,
    ObligationStatus,
    ObligationStatusHistory,
    PenaltyRule,
)
from app.models.user import User


@dataclass(frozen=True)
class AnalyticsQuery:
    tenant_id: uuid.UUID
    date_from: date
    date_to: date
    as_of_date: date
    department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    court: str | None = None
    status: ObligationStatus | None = None


class AnalyticsRepository:
    """Tenant-scoped aggregate queries used by the GovLegal reporting dashboard."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def courts(self, tenant_id: uuid.UUID) -> list[str]:
        values = await self.session.scalars(
            select(LegalCase.court)
            .where(LegalCase.tenant_id == tenant_id)
            .distinct()
            .order_by(LegalCase.court)
        )
        return list(values)

    @staticmethod
    def _obligation_filters(
        query: AnalyticsQuery, *, include_period: bool = True
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [LegalObligation.tenant_id == query.tenant_id]
        if include_period:
            filters.extend(
                [
                    cast(LegalObligation.created_at, Date) >= query.date_from,
                    cast(LegalObligation.created_at, Date) <= query.date_to,
                ]
            )
        if query.department_id is not None:
            filters.append(LegalObligation.responsible_department_id == query.department_id)
        if query.responsible_user_id is not None:
            filters.append(LegalObligation.responsible_user_id == query.responsible_user_id)
        if query.court is not None:
            filters.append(LegalCase.court.ilike(f"%{query.court}%"))
        if query.status is not None:
            filters.append(LegalObligation.status == query.status)
        return filters

    @staticmethod
    def _active_expression() -> ColumnElement[bool]:
        return LegalObligation.status.not_in(
            [ObligationStatus.COMPLETED, ObligationStatus.CANCELLED]
        )

    @staticmethod
    def _obligation_join() -> Join:
        return LegalObligation.__table__.join(
            CourtDecision.__table__,
            and_(
                CourtDecision.id == LegalObligation.court_decision_id,
                CourtDecision.tenant_id == LegalObligation.tenant_id,
            ),
        ).join(
            LegalCase.__table__,
            and_(
                LegalCase.id == CourtDecision.case_id,
                LegalCase.tenant_id == LegalObligation.tenant_id,
            ),
        )

    async def obligation_kpis(self, query: AnalyticsQuery) -> dict[str, int | float]:
        active = self._active_expression()
        overdue = (
            active
            & LegalObligation.due_date.is_not(None)
            & (LegalObligation.due_date < query.as_of_date)
        )
        due_soon = (
            active
            & LegalObligation.due_date.is_not(None)
            & (LegalObligation.due_date >= query.as_of_date)
            & (LegalObligation.due_date <= query.as_of_date + timedelta(days=7))
        )
        row = (
            await self.session.execute(
                select(
                    func.count().filter(active),
                    func.count().filter(overdue),
                    func.count().filter(due_soon),
                    func.count().filter(LegalObligation.status == ObligationStatus.COMPLETED),
                    func.count(),
                )
                .select_from(self._obligation_join())
                .where(*self._obligation_filters(query))
            )
        ).one()
        completed = int(row[3])
        total = int(row[4])
        return {
            "active_obligations": int(row[0]),
            "overdue_obligations": int(row[1]),
            "due_within_seven_days": int(row[2]),
            "completion_rate": round((completed / total) * 100, 1) if total else 0.0,
        }

    async def active_enforcements(self, query: AnalyticsQuery) -> int:
        count = await self.session.scalar(
            select(func.count(EnforcementProceeding.id))
            .select_from(EnforcementProceeding)
            .join(
                LegalObligation,
                and_(
                    LegalObligation.id == EnforcementProceeding.obligation_id,
                    LegalObligation.tenant_id == EnforcementProceeding.tenant_id,
                ),
            )
            .join(CourtDecision, CourtDecision.id == LegalObligation.court_decision_id)
            .join(LegalCase, LegalCase.id == CourtDecision.case_id)
            .where(
                EnforcementProceeding.tenant_id == query.tenant_id,
                EnforcementProceeding.status != EnforcementStatus.CLOSED,
                *self._obligation_filters(query),
            )
        )
        return int(count or 0)

    @staticmethod
    def _penalty_amount(as_of_date: date) -> ColumnElement[Decimal]:
        effective_end = func.least(func.coalesce(PenaltyRule.end_date, as_of_date), as_of_date)
        days = func.greatest(effective_end - PenaltyRule.start_date, 0)
        return case(
            (
                PenaltyRule.calculation_type == "DAILY_AMOUNT",
                func.coalesce(PenaltyRule.daily_amount, 0) * days,
            ),
            else_=(
                func.coalesce(PenaltyRule.percentage, 0)
                / 100
                * func.coalesce(PenaltyRule.base_value, 0)
                * days
            ),
        )

    async def financial_exposure(self, query: AnalyticsQuery) -> Decimal:
        amount = await self.session.scalar(
            select(func.coalesce(func.sum(self._penalty_amount(query.as_of_date)), 0))
            .select_from(PenaltyRule)
            .join(LegalObligation, LegalObligation.id == PenaltyRule.obligation_id)
            .join(CourtDecision, CourtDecision.id == LegalObligation.court_decision_id)
            .join(LegalCase, LegalCase.id == CourtDecision.case_id)
            .where(
                PenaltyRule.tenant_id == query.tenant_id,
                PenaltyRule.start_date <= query.as_of_date,
                *self._obligation_filters(query),
            )
        )
        return Decimal(amount or 0).quantize(Decimal("0.01"))

    async def deadline_distribution(self, query: AnalyticsQuery) -> dict[str, int]:
        active = self._active_expression()
        today = query.as_of_date
        row = (
            await self.session.execute(
                select(
                    func.count().filter(active & (LegalObligation.due_date < today)),
                    func.count().filter(active & (LegalObligation.due_date == today)),
                    func.count().filter(
                        active
                        & (LegalObligation.due_date > today)
                        & (LegalObligation.due_date <= today + timedelta(days=7))
                    ),
                    func.count().filter(
                        active
                        & (LegalObligation.due_date > today + timedelta(days=7))
                        & (LegalObligation.due_date <= today + timedelta(days=30))
                    ),
                    func.count().filter(
                        active & (LegalObligation.due_date > today + timedelta(days=30))
                    ),
                    func.count().filter(active & LegalObligation.due_date.is_(None)),
                )
                .select_from(self._obligation_join())
                .where(*self._obligation_filters(query))
            )
        ).one()
        keys = ("overdue", "today", "next_7_days", "days_8_30", "after_30_days", "no_due_date")
        return {key: int(row[index]) for index, key in enumerate(keys)}

    async def overdue_ageing(self, query: AnalyticsQuery) -> dict[str, int]:
        active = self._active_expression()
        today = query.as_of_date
        overdue_days = today - LegalObligation.due_date
        row = (
            await self.session.execute(
                select(
                    func.count().filter(active & overdue_days.between(1, 7)),
                    func.count().filter(active & overdue_days.between(8, 30)),
                    func.count().filter(active & overdue_days.between(31, 90)),
                    func.count().filter(active & (overdue_days > 90)),
                )
                .select_from(self._obligation_join())
                .where(
                    LegalObligation.due_date.is_not(None),
                    LegalObligation.due_date < today,
                    *self._obligation_filters(query),
                )
            )
        ).one()
        keys = ("days_1_7", "days_8_30", "days_31_90", "over_90_days")
        return {key: int(row[index]) for index, key in enumerate(keys)}

    async def monthly_activity(
        self, query: AnalyticsQuery
    ) -> tuple[int, dict[date, int], dict[date, int]]:
        created_month = func.date_trunc(
            literal_column("'month'"), LegalObligation.created_at
        )
        terminal = (
            select(
                ObligationStatusHistory.obligation_id.label("obligation_id"),
                func.min(ObligationStatusHistory.changed_at).label("terminal_at"),
            )
            .where(
                ObligationStatusHistory.tenant_id == query.tenant_id,
                ObligationStatusHistory.new_status.in_(
                    [ObligationStatus.COMPLETED, ObligationStatus.CANCELLED]
                ),
            )
            .group_by(ObligationStatusHistory.obligation_id)
            .subquery()
        )
        period_start = datetime.combine(query.date_from, time.min)
        period_filters = self._obligation_filters(query, include_period=False)
        initial_active = await self.session.scalar(
            select(func.count(LegalObligation.id))
            .select_from(self._obligation_join().outerjoin(
                terminal, terminal.c.obligation_id == LegalObligation.id
            ))
            .where(
                LegalObligation.created_at < period_start,
                (terminal.c.terminal_at.is_(None) | (terminal.c.terminal_at >= period_start)),
                *period_filters,
            )
        )
        created_rows = await self.session.execute(
            select(
                cast(created_month, Date),
                func.count(LegalObligation.id),
            )
            .select_from(self._obligation_join())
            .where(*self._obligation_filters(query))
            .group_by(created_month)
            .order_by(created_month)
        )
        terminal_month = func.date_trunc(literal_column("'month'"), terminal.c.terminal_at)
        terminal_rows = await self.session.execute(
            select(
                cast(terminal_month, Date),
                func.count(LegalObligation.id),
            )
            .select_from(self._obligation_join().join(
                terminal, terminal.c.obligation_id == LegalObligation.id
            ))
            .where(
                cast(terminal.c.terminal_at, Date) >= query.date_from,
                cast(terminal.c.terminal_at, Date) <= query.date_to,
                *period_filters,
            )
            .group_by(terminal_month)
            .order_by(terminal_month)
        )
        return (
            int(initial_active or 0),
            {row[0]: int(row[1]) for row in created_rows if row[0] is not None},
            {row[0]: int(row[1]) for row in terminal_rows if row[0] is not None},
        )

    async def workload_by_department(
        self, query: AnalyticsQuery
    ) -> list[tuple[uuid.UUID | None, str, int, int, int]]:
        active = self._active_expression()
        overdue = active & (LegalObligation.due_date < query.as_of_date)
        rows = await self.session.execute(
            select(
                Department.id,
                func.coalesce(Department.name, "Nerepartizate"),
                func.count().filter(active),
                func.count().filter(overdue),
                func.count().filter(LegalObligation.status == ObligationStatus.COMPLETED),
            )
            .select_from(self._obligation_join().outerjoin(
                Department,
                and_(
                    Department.id == LegalObligation.responsible_department_id,
                    Department.tenant_id == LegalObligation.tenant_id,
                ),
            ))
            .where(*self._obligation_filters(query))
            .group_by(Department.id, Department.name)
            .order_by(func.count().filter(active).desc(), Department.name)
        )
        return [
            (row[0], str(row[1]), int(row[2]), int(row[3]), int(row[4])) for row in rows
        ]

    async def workload_by_user(
        self, query: AnalyticsQuery
    ) -> list[tuple[uuid.UUID | None, str, int, int, int]]:
        active = self._active_expression()
        overdue = active & (LegalObligation.due_date < query.as_of_date)
        rows = await self.session.execute(
            select(
                User.id,
                func.coalesce(User.display_name, "Nerepartizate"),
                func.count().filter(active),
                func.count().filter(overdue),
                func.count().filter(LegalObligation.status == ObligationStatus.COMPLETED),
            )
            .select_from(self._obligation_join().outerjoin(
                User,
                and_(
                    User.id == LegalObligation.responsible_user_id,
                    User.tenant_id == LegalObligation.tenant_id,
                ),
            ))
            .where(*self._obligation_filters(query))
            .group_by(User.id, User.display_name)
            .order_by(func.count().filter(active).desc(), User.display_name)
        )
        return [
            (row[0], str(row[1]), int(row[2]), int(row[3]), int(row[4])) for row in rows
        ]

    async def exposure_by_department(
        self, query: AnalyticsQuery
    ) -> list[tuple[uuid.UUID | None, str, Decimal, int]]:
        amount = self._penalty_amount(query.as_of_date)
        rows = await self.session.execute(
            select(
                Department.id,
                func.coalesce(Department.name, "Nerepartizate"),
                func.coalesce(func.sum(amount), 0),
                func.count(PenaltyRule.id),
            )
            .select_from(PenaltyRule)
            .join(LegalObligation, LegalObligation.id == PenaltyRule.obligation_id)
            .join(CourtDecision, CourtDecision.id == LegalObligation.court_decision_id)
            .join(LegalCase, LegalCase.id == CourtDecision.case_id)
            .outerjoin(
                Department,
                and_(
                    Department.id == LegalObligation.responsible_department_id,
                    Department.tenant_id == LegalObligation.tenant_id,
                ),
            )
            .where(
                PenaltyRule.tenant_id == query.tenant_id,
                PenaltyRule.start_date <= query.as_of_date,
                *self._obligation_filters(query),
            )
            .group_by(Department.id, Department.name)
            .order_by(func.sum(amount).desc(), Department.name)
        )
        return [
            (row[0], str(row[1]), Decimal(row[2]).quantize(Decimal("0.01")), int(row[3]))
            for row in rows
        ]

    async def enforcement_statuses(self, query: AnalyticsQuery) -> dict[str, int]:
        rows = await self.session.execute(
            select(EnforcementProceeding.status, func.count(EnforcementProceeding.id))
            .select_from(EnforcementProceeding)
            .join(LegalObligation, LegalObligation.id == EnforcementProceeding.obligation_id)
            .join(CourtDecision, CourtDecision.id == LegalObligation.court_decision_id)
            .join(LegalCase, LegalCase.id == CourtDecision.case_id)
            .where(
                EnforcementProceeding.tenant_id == query.tenant_id,
                *self._obligation_filters(query),
            )
            .group_by(EnforcementProceeding.status)
        )
        return {status.value: int(count) for status, count in rows}
