import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalCaseStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class ObligationType(StrEnum):
    DO = "DO"
    PAY = "PAY"
    REFRAIN = "REFRAIN"
    RESOLVE_REQUEST = "RESOLVE_REQUEST"
    ISSUE_DOCUMENT = "ISSUE_DOCUMENT"
    OTHER = "OTHER"


class ObligationStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class EnforcementStatus(StrEnum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class LegalCase(Base):
    __tablename__ = "legal_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_number", name="uq_legal_cases_tenant_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    case_number: Mapped[str] = mapped_column(String(100), nullable=False)
    court: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[LegalCaseStatus] = mapped_column(
        Enum(LegalCaseStatus, name="legal_case_status"),
        nullable=False,
        default=LegalCaseStatus.OPEN,
    )
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CourtDecision(Base):
    __tablename__ = "court_decisions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "case_id", "decision_number", name="uq_decisions_tenant_case_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_cases.id", ondelete="CASCADE"), index=True
    )
    decision_number: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    final_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_type: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LegalObligation(Base):
    __tablename__ = "legal_obligations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    court_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("court_decisions.id", ondelete="CASCADE"), index=True
    )
    obligation_type: Mapped[ObligationType] = mapped_column(
        Enum(ObligationType, name="obligation_type"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[ObligationStatus] = mapped_column(
        Enum(ObligationStatus, name="obligation_status"),
        nullable=False,
        default=ObligationStatus.DRAFT,
    )
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ObligationStatusHistory(Base):
    __tablename__ = "obligation_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_obligations.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[ObligationStatus | None] = mapped_column(
        Enum(ObligationStatus, name="obligation_status", create_type=False), nullable=True
    )
    new_status: Mapped[ObligationStatus] = mapped_column(
        Enum(ObligationStatus, name="obligation_status", create_type=False), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EnforcementProceeding(Base):
    __tablename__ = "enforcement_proceedings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "file_number", name="uq_enforcement_tenant_file"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_obligations.id", ondelete="CASCADE"), index=True
    )
    file_number: Mapped[str] = mapped_column(String(100), nullable=False)
    enforcement_officer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[EnforcementStatus] = mapped_column(
        Enum(EnforcementStatus, name="enforcement_status"),
        nullable=False,
        default=EnforcementStatus.OPEN,
    )


class PenaltyRule(Base):
    __tablename__ = "penalty_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_obligations.id", ondelete="CASCADE"), index=True
    )
    calculation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    daily_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    base_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
