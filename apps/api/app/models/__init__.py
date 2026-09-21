"""Database models registered with the GovControl ORM metadata."""

from app.models.audit import AuditEvent
from app.models.department import Department
from app.models.document import Document
from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    LegalCase,
    LegalObligation,
    ObligationStatusHistory,
    PenaltyRule,
)
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Department",
    "Document",
    "CourtDecision",
    "EnforcementProceeding",
    "LegalCase",
    "LegalObligation",
    "ObligationStatusHistory",
    "PenaltyRule",
    "Permission",
    "Role",
    "RolePermission",
    "Tenant",
    "User",
    "UserRole",
]
