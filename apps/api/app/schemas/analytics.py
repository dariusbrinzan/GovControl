import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.legal import ObligationStatus


class AnalyticsPeriod(BaseModel):
    date_from: date
    date_to: date


class AnalyticsFiltersResponse(BaseModel):
    period: AnalyticsPeriod
    department_id: uuid.UUID | None
    responsible_user_id: uuid.UUID | None
    court: str | None
    status: ObligationStatus | None


class DashboardKpis(BaseModel):
    active_obligations: int
    overdue_obligations: int
    due_within_seven_days: int
    active_enforcements: int
    financial_exposure: Decimal
    completion_rate: float


class CountDataPoint(BaseModel):
    key: str
    label: str
    value: int


class MonthlyActivityPoint(BaseModel):
    month: date
    created: int
    completed: int
    active_at_end: int


class WorkloadDataPoint(BaseModel):
    id: uuid.UUID | None
    label: str
    active: int
    overdue: int
    completed: int


class ExposureDataPoint(BaseModel):
    id: uuid.UUID | None
    label: str
    amount: Decimal
    rules: int


class AnalyticsFilterOption(BaseModel):
    id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    label: str
    value: str


class AnalyticsFilterOptionsResponse(BaseModel):
    departments: list[AnalyticsFilterOption]
    users: list[AnalyticsFilterOption]
    courts: list[AnalyticsFilterOption]
    statuses: list[AnalyticsFilterOption]


class LegalAnalyticsDashboardResponse(BaseModel):
    generated_on: date
    filters: AnalyticsFiltersResponse
    kpis: DashboardKpis
    deadline_distribution: list[CountDataPoint]
    overdue_ageing: list[CountDataPoint]
    monthly_activity: list[MonthlyActivityPoint]
    exposure_by_department: list[ExposureDataPoint]
    workload_by_department: list[WorkloadDataPoint]
    workload_by_user: list[WorkloadDataPoint]
    enforcement_statuses: list[CountDataPoint]
