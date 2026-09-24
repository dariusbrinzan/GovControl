import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import ObligationStatus
from app.repositories.analytics import AnalyticsQuery, AnalyticsRepository
from app.repositories.department import DepartmentRepository
from app.repositories.user import UserRepository
from app.schemas.analytics import (
    AnalyticsFilterOption,
    AnalyticsFilterOptionsResponse,
    AnalyticsFiltersResponse,
    AnalyticsPeriod,
    CountDataPoint,
    DashboardKpis,
    ExposureDataPoint,
    LegalAnalyticsDashboardResponse,
    MonthlyActivityPoint,
    WorkloadDataPoint,
)


class AnalyticsFilterError(Exception):
    pass


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


class AnalyticsService:
    MAX_PERIOD_DAYS = 731

    def __init__(self, session: AsyncSession) -> None:
        self.repository = AnalyticsRepository(session)
        self.departments = DepartmentRepository(session)
        self.users = UserRepository(session)

    async def filter_options(self, tenant_id: uuid.UUID) -> AnalyticsFilterOptionsResponse:
        departments = await self.departments.list_for_tenant(tenant_id)
        users = await self.users.list_for_tenant(tenant_id)
        courts = await self.repository.courts(tenant_id)
        status_labels = {
            ObligationStatus.DRAFT: "Ciornă",
            ObligationStatus.OPEN: "Deschisă",
            ObligationStatus.IN_PROGRESS: "În lucru",
            ObligationStatus.AT_RISK: "La risc",
            ObligationStatus.OVERDUE: "Depășită",
            ObligationStatus.COMPLETED: "Finalizată",
            ObligationStatus.CANCELLED: "Anulată",
        }
        return AnalyticsFilterOptionsResponse(
            departments=[
                AnalyticsFilterOption(id=item.id, value=str(item.id), label=item.name)
                for item in departments
            ],
            users=[
                AnalyticsFilterOption(
                    id=item.id,
                    department_id=item.department_id,
                    value=str(item.id),
                    label=item.display_name,
                )
                for item in users
                if item.is_active
            ],
            courts=[AnalyticsFilterOption(value=item, label=item) for item in courts],
            statuses=[
                AnalyticsFilterOption(value=item.value, label=status_labels[item])
                for item in ObligationStatus
            ],
        )

    async def dashboard(
        self,
        *,
        tenant_id: uuid.UUID,
        today: date,
        date_from: date | None = None,
        date_to: date | None = None,
        department_id: uuid.UUID | None = None,
        responsible_user_id: uuid.UUID | None = None,
        court: str | None = None,
        status: ObligationStatus | None = None,
    ) -> LegalAnalyticsDashboardResponse:
        effective_to = date_to or today
        effective_from = date_from or _shift_month(_month_start(effective_to), -11)
        if effective_from > effective_to:
            raise AnalyticsFilterError("Data de început nu poate fi după data de sfârșit.")
        if effective_to - effective_from > timedelta(days=self.MAX_PERIOD_DAYS):
            raise AnalyticsFilterError("Perioada de raportare nu poate depăși doi ani.")
        if department_id is not None:
            department = await self.departments.get_by_id_for_tenant(department_id, tenant_id)
            if department is None:
                raise AnalyticsFilterError(
                    "Departamentul nu este disponibil în instituția curentă."
                )
        if responsible_user_id is not None:
            user = await self.users.get_by_id_for_tenant(responsible_user_id, tenant_id)
            if user is None:
                raise AnalyticsFilterError(
                    "Responsabilul nu este disponibil în instituția curentă."
                )
            if department_id is not None and user.department_id != department_id:
                raise AnalyticsFilterError("Responsabilul nu aparține departamentului selectat.")

        normalized_court = court.strip() if court and court.strip() else None
        query = AnalyticsQuery(
            tenant_id=tenant_id,
            date_from=effective_from,
            date_to=effective_to,
            as_of_date=min(today, effective_to),
            department_id=department_id,
            responsible_user_id=responsible_user_id,
            court=normalized_court,
            status=status,
        )

        kpi_values = await self.repository.obligation_kpis(query)
        active_enforcements = await self.repository.active_enforcements(query)
        financial_exposure = await self.repository.financial_exposure(query)
        deadline_values = await self.repository.deadline_distribution(query)
        ageing_values = await self.repository.overdue_ageing(query)
        initial_active, created_by_month, terminal_by_month = (
            await self.repository.monthly_activity(query)
        )
        exposure_rows = await self.repository.exposure_by_department(query)
        department_rows = await self.repository.workload_by_department(query)
        user_rows = await self.repository.workload_by_user(query)
        enforcement_values = await self.repository.enforcement_statuses(query)

        return LegalAnalyticsDashboardResponse(
            generated_on=today,
            filters=AnalyticsFiltersResponse(
                period=AnalyticsPeriod(date_from=effective_from, date_to=effective_to),
                department_id=department_id,
                responsible_user_id=responsible_user_id,
                court=normalized_court,
                status=status,
            ),
            kpis=DashboardKpis(
                active_obligations=int(kpi_values["active_obligations"]),
                overdue_obligations=int(kpi_values["overdue_obligations"]),
                due_within_seven_days=int(kpi_values["due_within_seven_days"]),
                active_enforcements=active_enforcements,
                financial_exposure=financial_exposure,
                completion_rate=float(kpi_values["completion_rate"]),
            ),
            deadline_distribution=self._count_points(
                deadline_values,
                (
                    ("overdue", "Depășite"),
                    ("today", "Scadente astăzi"),
                    ("next_7_days", "În următoarele 7 zile"),
                    ("days_8_30", "În 8–30 zile"),
                    ("after_30_days", "Peste 30 zile"),
                    ("no_due_date", "Fără termen"),
                ),
            ),
            overdue_ageing=self._count_points(
                ageing_values,
                (
                    ("days_1_7", "1–7 zile"),
                    ("days_8_30", "8–30 zile"),
                    ("days_31_90", "31–90 zile"),
                    ("over_90_days", "Peste 90 zile"),
                ),
            ),
            monthly_activity=self._monthly_points(
                effective_from,
                effective_to,
                initial_active,
                created_by_month,
                terminal_by_month,
            ),
            exposure_by_department=[
                ExposureDataPoint(id=item_id, label=label, amount=amount, rules=rules)
                for item_id, label, amount, rules in exposure_rows
            ],
            workload_by_department=self._workload_points(department_rows),
            workload_by_user=self._workload_points(user_rows),
            enforcement_statuses=self._count_points(
                enforcement_values,
                (("OPEN", "Deschise"), ("SUSPENDED", "Suspendate"), ("CLOSED", "Închise")),
            ),
        )

    @staticmethod
    def _count_points(
        values: dict[str, int], labels: tuple[tuple[str, str], ...]
    ) -> list[CountDataPoint]:
        return [
            CountDataPoint(key=key, label=label, value=values.get(key, 0))
            for key, label in labels
        ]

    @staticmethod
    def _workload_points(
        rows: list[tuple[uuid.UUID | None, str, int, int, int]],
    ) -> list[WorkloadDataPoint]:
        return [
            WorkloadDataPoint(
                id=item_id,
                label=label,
                active=active,
                overdue=overdue,
                completed=completed,
            )
            for item_id, label, active, overdue, completed in rows
        ]

    @staticmethod
    def _monthly_points(
        date_from: date,
        date_to: date,
        initial_active: int,
        created_by_month: dict[date, int],
        terminal_by_month: dict[date, int],
    ) -> list[MonthlyActivityPoint]:
        points: list[MonthlyActivityPoint] = []
        active = initial_active
        current_month = _month_start(date_from)
        final_month = _month_start(date_to)
        while current_month <= final_month:
            created = created_by_month.get(current_month, 0)
            completed = terminal_by_month.get(current_month, 0)
            active = max(0, active + created - completed)
            points.append(
                MonthlyActivityPoint(
                    month=current_month,
                    created=created,
                    completed=completed,
                    active_at_end=active,
                )
            )
            current_month = _shift_month(current_month, 1)
        return points
