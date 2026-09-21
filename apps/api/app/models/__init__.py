"""Database models registered with the GovControl ORM metadata."""

from app.models.audit import AuditEvent
from app.models.department import Department
from app.models.legal import CourtDecision, LegalCase, LegalObligation, ObligationStatusHistory
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.tenant import Tenant
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Department",
    "CourtDecision",
    "LegalCase",
    "LegalObligation",
    "ObligationStatusHistory",
    "Permission",
    "Role",
    "RolePermission",
    "Tenant",
    "User",
    "UserRole",
]
