from pydantic import BaseModel


class LegalDashboardResponse(BaseModel):
    open_obligations: int
    overdue_obligations: int
    due_within_seven_days: int
    overdue_days_total: int
