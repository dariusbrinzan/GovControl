import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.models.department import Department
from app.models.document import Document
from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    EnforcementStatus,
    LegalCase,
    LegalCaseStatus,
    LegalObligation,
    ObligationStatus,
    ObligationStatusHistory,
    ObligationType,
    PenaltyRule,
)
from app.models.notification import Notification, NotificationStatus
from app.models.rbac import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services.storage import LocalStorage

DEMO_NAMESPACE = uuid.UUID("56ee218c-f78f-4b3e-b8a5-6599111ed247")


def demo_id(key: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, key)


def shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def month_timestamp(today: date, months_ago: int, day: int = 6) -> datetime:
    first = shift_month(today.replace(day=1), -months_ago)
    safe_day = min(day, 28)
    return datetime(first.year, first.month, safe_day, 9, 0, tzinfo=UTC)


async def upsert[ModelT](
    session: AsyncSession, model: type[ModelT], key: str, values: dict[str, Any]
) -> ModelT:
    item_id = demo_id(key)
    item = await session.get(model, item_id)
    if item is None:
        item = model(id=item_id, **values)  # type: ignore[call-arg]
        session.add(item)
    else:
        for field, value in values.items():
            setattr(item, field, value)
    return item


async def seed_demo_legal_data(
    session: AsyncSession,
    tenant: Tenant,
    administrator: User,
    roles: dict[str, Role],
) -> None:
    """Populate a stable, idempotent and visually useful GovLegal demo dataset."""
    today = date.today()

    department_definitions = (
        ("juridic", "Direcția Juridică", "DJ"),
        ("patrimoniu", "Direcția Patrimoniu", "DP"),
        ("achizitii", "Serviciul Achiziții Publice", "SAP"),
        ("urbanism", "Direcția Urbanism", "DU"),
    )
    departments: dict[str, Department] = {}
    for key, name, code in department_definitions:
        departments[key] = await upsert(
            session,
            Department,
            f"department:{key}",
            {"tenant_id": tenant.id, "name": name, "code": code},
        )

    user_definitions = (
        (
            "director",
            "director.juridic@govcontrol.local",
            "Elena Ionescu",
            "juridic",
            "legal_director",
        ),
        (
            "officer-1",
            "andrei.popescu@govcontrol.local",
            "Andrei Popescu",
            "juridic",
            "legal_officer",
        ),
        ("officer-2", "maria.stan@govcontrol.local", "Maria Stan", "patrimoniu", "legal_officer"),
        (
            "officer-3",
            "radu.dumitru@govcontrol.local",
            "Radu Dumitru",
            "achizitii",
            "legal_officer",
        ),
        ("auditor", "auditor@govcontrol.local", "Ioana Marinescu", "juridic", "auditor"),
    )
    users: dict[str, User] = {"admin": administrator}
    administrator.department_id = departments["juridic"].id
    for key, email, display_name, department_key, role_key in user_definitions:
        user = await upsert(
            session,
            User,
            f"user:{key}",
            {
                "tenant_id": tenant.id,
                "department_id": departments[department_key].id,
                "email": email,
                "display_name": display_name,
                "is_active": True,
            },
        )
        users[key] = user
        role = roles[role_key]
        if await session.get(UserRole, (user.id, role.id)) is None:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    case_definitions = (
        (
            "case-1",
            "GC-1452/3/2026",
            "Tribunalul București",
            "Contestație privind executarea contractului de lucrări publice",
            10,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-2",
            "GC-8821/2/2025",
            "Curtea de Apel București",
            "Litigiu patrimonial privind recuperarea unui imobil",
            8,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-3",
            "GC-3176/4/2025",
            "Judecătoria Sectorului 1",
            "Acțiune în pretenții pentru servicii neachitate",
            6,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-4",
            "GC-4410/3/2025",
            "Tribunalul București",
            "Anulare act administrativ în materia urbanismului",
            5,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-5",
            "GC-902/2/2025",
            "Curtea de Apel București",
            "Recurs privind o procedură de achiziție publică",
            4,
            LegalCaseStatus.CLOSED,
        ),
        (
            "case-6",
            "GC-7288/3/2024",
            "Tribunalul București",
            "Obligație de emitere a unui act administrativ",
            3,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-7",
            "GC-1204/299/2026",
            "Judecătoria Sectorului 1",
            "Plângere contravențională și cheltuieli de judecată",
            1,
            LegalCaseStatus.OPEN,
        ),
        (
            "case-8",
            "GC-551/2/2026",
            "Curtea de Apel București",
            "Suspendarea executării unei dispoziții administrative",
            0,
            LegalCaseStatus.OPEN,
        ),
    )
    cases: dict[str, LegalCase] = {}
    decisions: dict[str, CourtDecision] = {}
    for index, (key, number, court, subject, months_ago, case_status) in enumerate(
        case_definitions, 1
    ):
        created_at = month_timestamp(today, months_ago, 3 + index)
        current_case = await upsert(
            session,
            LegalCase,
            key,
            {
                "tenant_id": tenant.id,
                "case_number": number,
                "court": court,
                "subject": subject,
                "filing_date": created_at.date() - timedelta(days=12),
                "status": case_status,
                "external_reference": f"REG-JUR-{today.year}-{index:03d}",
                "created_at": created_at,
                "updated_at": created_at + timedelta(days=4),
            },
        )
        cases[key] = current_case
        decision_date = min(today - timedelta(days=2), created_at.date() + timedelta(days=24))
        decision = await upsert(
            session,
            CourtDecision,
            f"decision-{index}",
            {
                "tenant_id": tenant.id,
                "case_id": current_case.id,
                "decision_number": f"HC-{120 + index}/{decision_date.year}",
                "decision_date": decision_date,
                "final_date": decision_date + timedelta(days=15) if index % 3 else None,
                "decision_type": ("Sentință civilă" if index % 2 else "Decizie civilă"),
                "summary": (
                    f"Hotărâre demo pentru dosarul {number}. Instituția urmărește "
                    "măsurile dispuse și termenele de conformare."
                ),
                "created_at": datetime.combine(decision_date, datetime.min.time(), UTC),
            },
        )
        decisions[f"decision-{index}"] = decision

    obligation_definitions = (
        (
            "ob-01",
            1,
            ObligationType.PAY,
            "Achitarea cheltuielilor de judecată stabilite prin hotărâre",
            "patrimoniu",
            "officer-2",
            -12,
            ObligationStatus.OVERDUE,
            10,
        ),
        (
            "ob-02",
            2,
            ObligationType.DO,
            "Predarea imobilului și actualizarea inventarului domeniului public",
            "patrimoniu",
            "officer-2",
            -46,
            ObligationStatus.OVERDUE,
            8,
        ),
        (
            "ob-03",
            3,
            ObligationType.PAY,
            "Recuperarea debitului principal și a dobânzii legale",
            "juridic",
            "admin",
            -4,
            ObligationStatus.OVERDUE,
            6,
        ),
        (
            "ob-04",
            4,
            ObligationType.ISSUE_DOCUMENT,
            "Emiterea certificatului de urbanism conform dispozitivului",
            "urbanism",
            "admin",
            -125,
            ObligationStatus.OVERDUE,
            5,
        ),
        (
            "ob-05",
            5,
            ObligationType.DO,
            "Reevaluarea ofertelor din procedura de achiziție contestată",
            "achizitii",
            "officer-3",
            2,
            ObligationStatus.AT_RISK,
            4,
        ),
        (
            "ob-06",
            6,
            ObligationType.RESOLVE_REQUEST,
            "Soluționarea cererii administrative și comunicarea răspunsului",
            "juridic",
            "officer-1",
            6,
            ObligationStatus.AT_RISK,
            3,
        ),
        (
            "ob-07",
            7,
            ObligationType.PAY,
            "Plata cheltuielilor judiciare și transmiterea dovezii",
            "juridic",
            "director",
            14,
            ObligationStatus.AT_RISK,
            1,
        ),
        (
            "ob-08",
            8,
            ObligationType.REFRAIN,
            "Suspendarea efectelor dispoziției până la soluționarea fondului",
            "juridic",
            "officer-1",
            0,
            ObligationStatus.IN_PROGRESS,
            0,
        ),
        (
            "ob-09",
            1,
            ObligationType.DO,
            "Întocmirea notei de conformare contractuală",
            "achizitii",
            "officer-3",
            5,
            ObligationStatus.IN_PROGRESS,
            9,
        ),
        (
            "ob-10",
            2,
            ObligationType.ISSUE_DOCUMENT,
            "Actualizarea documentației cadastrale pentru imobil",
            "patrimoniu",
            "officer-2",
            20,
            ObligationStatus.IN_PROGRESS,
            7,
        ),
        (
            "ob-11",
            3,
            ObligationType.DO,
            "Transmiterea titlului executoriu către compartimentul financiar",
            "juridic",
            "officer-1",
            40,
            ObligationStatus.IN_PROGRESS,
            6,
        ),
        (
            "ob-12",
            4,
            ObligationType.RESOLVE_REQUEST,
            "Reanalizarea documentației depuse de solicitant",
            "urbanism",
            "director",
            7,
            ObligationStatus.OPEN,
            4,
        ),
        (
            "ob-13",
            5,
            ObligationType.DO,
            "Publicarea măsurilor de remediere în platforma de achiziții",
            "achizitii",
            "officer-3",
            15,
            ObligationStatus.OPEN,
            3,
        ),
        (
            "ob-14",
            6,
            ObligationType.ISSUE_DOCUMENT,
            "Emiterea dispoziției de punere în executare",
            "juridic",
            "director",
            60,
            ObligationStatus.OPEN,
            2,
        ),
        (
            "ob-15",
            7,
            ObligationType.PAY,
            "Restituirea taxei judiciare achitate necuvenit",
            "juridic",
            "officer-1",
            -30,
            ObligationStatus.COMPLETED,
            11,
        ),
        (
            "ob-16",
            8,
            ObligationType.DO,
            "Comunicarea hotărârii către toate structurile responsabile",
            "juridic",
            "director",
            -18,
            ObligationStatus.COMPLETED,
            9,
        ),
        (
            "ob-17",
            1,
            ObligationType.DO,
            "Remedierea clauzelor contractuale constatate neconforme",
            "achizitii",
            "officer-3",
            -70,
            ObligationStatus.COMPLETED,
            7,
        ),
        (
            "ob-18",
            2,
            ObligationType.OTHER,
            "Actualizarea evidenței tehnico-operative a patrimoniului",
            "patrimoniu",
            "officer-2",
            -8,
            ObligationStatus.COMPLETED,
            5,
        ),
        (
            "ob-19",
            3,
            ObligationType.PAY,
            "Plată suspendată în urma îndreptării erorii materiale",
            "juridic",
            "officer-1",
            None,
            ObligationStatus.CANCELLED,
            2,
        ),
        (
            "ob-20",
            4,
            ObligationType.OTHER,
            "Analiza efectelor hotărârii asupra regulamentului local",
            "urbanism",
            "director",
            None,
            ObligationStatus.DRAFT,
            0,
        ),
    )
    obligations: dict[str, LegalObligation] = {}
    for index, (
        key,
        decision_index,
        kind,
        description,
        department_key,
        user_key,
        due_offset,
        obligation_status,
        months_ago,
    ) in enumerate(obligation_definitions, 1):
        created_at = month_timestamp(today, months_ago, 8 + (index % 12))
        due_date = today + timedelta(days=due_offset) if due_offset is not None else None
        completion_date = (
            min(today - timedelta(days=1), due_date or today - timedelta(days=1))
            if obligation_status == ObligationStatus.COMPLETED
            else None
        )
        obligation = await upsert(
            session,
            LegalObligation,
            key,
            {
                "tenant_id": tenant.id,
                "court_decision_id": decisions[f"decision-{decision_index}"].id,
                "obligation_type": kind,
                "description": description,
                "responsible_department_id": departments[department_key].id,
                "responsible_user_id": users[user_key].id,
                "due_date": due_date,
                "status": obligation_status,
                "completion_date": completion_date,
                "created_at": created_at,
                "updated_at": datetime.now(UTC),
            },
        )
        obligations[key] = obligation
        terminal_at = (
            datetime.combine(completion_date, datetime.min.time(), UTC) if completion_date else None
        )
        history = await upsert(
            session,
            ObligationStatusHistory,
            f"history:{key}",
            {
                "tenant_id": tenant.id,
                "obligation_id": obligation.id,
                "old_status": ObligationStatus.IN_PROGRESS
                if terminal_at
                else ObligationStatus.DRAFT,
                "new_status": obligation_status,
                "actor_user_id": administrator.id,
                "changed_at": terminal_at or created_at + timedelta(days=2),
            },
        )
        session.add(history)

    enforcement_definitions = (
        (
            "enf-1",
            "ob-01",
            "EX-441/2026",
            "BEJ Georgescu și Asociații",
            -38,
            EnforcementStatus.OPEN,
        ),
        (
            "enf-2",
            "ob-02",
            "EX-188/2026",
            "Compartiment Executări Silite",
            -72,
            EnforcementStatus.OPEN,
        ),
        ("enf-3", "ob-03", "EX-512/2026", "BEJ Radu Mihai", -21, EnforcementStatus.OPEN),
        ("enf-4", "ob-04", "EX-902/2025", "Direcția Juridică", -140, EnforcementStatus.SUSPENDED),
        ("enf-5", "ob-15", "EX-077/2026", "Compartiment Financiar", -55, EnforcementStatus.CLOSED),
    )
    enforcements: dict[str, EnforcementProceeding] = {}
    for (
        key,
        obligation_key,
        number,
        officer,
        start_offset,
        enforcement_status,
    ) in enforcement_definitions:
        enforcements[key] = await upsert(
            session,
            EnforcementProceeding,
            key,
            {
                "tenant_id": tenant.id,
                "obligation_id": obligations[obligation_key].id,
                "file_number": number,
                "enforcement_officer": officer,
                "start_date": today + timedelta(days=start_offset),
                "status": enforcement_status,
            },
        )

    penalty_definitions = (
        ("pen-1", "ob-01", "DAILY_AMOUNT", Decimal("150.00"), None, None, -12),
        ("pen-2", "ob-02", "DAILY_AMOUNT", Decimal("250.00"), None, None, -46),
        ("pen-3", "ob-03", "PERCENTAGE_OF_BASE", None, Decimal("0.1000"), Decimal("85000.00"), -20),
        ("pen-4", "ob-04", "DAILY_AMOUNT", Decimal("100.00"), None, None, -125),
        (
            "pen-5",
            "ob-05",
            "PERCENTAGE_OF_BASE",
            None,
            Decimal("0.0500"),
            Decimal("240000.00"),
            -10,
        ),
        ("pen-6", "ob-06", "DAILY_AMOUNT", Decimal("75.00"), None, None, -8),
    )
    for (
        key,
        obligation_key,
        calculation_type,
        daily_amount,
        percentage,
        base_value,
        start_offset,
    ) in penalty_definitions:
        await upsert(
            session,
            PenaltyRule,
            key,
            {
                "tenant_id": tenant.id,
                "obligation_id": obligations[obligation_key].id,
                "calculation_type": calculation_type,
                "daily_amount": daily_amount,
                "percentage": percentage,
                "base_value": base_value,
                "start_date": today + timedelta(days=start_offset),
                "end_date": None,
            },
        )

    notification_items = (
        (
            "notification:overdue-1",
            "ob-01",
            "Termen depășit",
            "Obligația de plată necesită intervenție imediată.",
            NotificationStatus.UNREAD,
        ),
        (
            "notification:overdue-2",
            "ob-02",
            "Restanță critică",
            "Predarea imobilului este întârziată cu peste 30 de zile.",
            NotificationStatus.UNREAD,
        ),
        (
            "notification:today",
            "ob-08",
            "Termen scadent astăzi",
            "Verifică măsurile de suspendare înainte de finalul zilei.",
            NotificationStatus.UNREAD,
        ),
        (
            "notification:upcoming",
            "ob-05",
            "Termen în următoarele 7 zile",
            "Reevaluarea ofertelor trebuie finalizată în curând.",
            NotificationStatus.UNREAD,
        ),
        (
            "notification:completed",
            "ob-15",
            "Obligație finalizată",
            "Dovada restituirii taxei a fost înregistrată.",
            NotificationStatus.READ,
        ),
    )
    for index, (key, obligation_key, title, body, notification_status) in enumerate(
        notification_items
    ):
        obligation = obligations[obligation_key]
        await upsert(
            session,
            Notification,
            key,
            {
                "tenant_id": tenant.id,
                "recipient_user_id": administrator.id,
                "entity_type": "LegalObligation",
                "entity_id": obligation.id,
                "notification_type": "DEMO_DEADLINE",
                "title": title,
                "body": body,
                "due_date": obligation.due_date,
                "status": notification_status,
                "deduplication_key": key,
                "read_at": datetime.now(UTC) - timedelta(days=1)
                if notification_status == NotificationStatus.READ
                else None,
                "created_at": datetime.now(UTC) - timedelta(hours=index * 5),
            },
        )

    await session.flush()
    storage = LocalStorage(get_settings().document_storage_path)
    document_definitions = (
        (
            "doc-1",
            "LegalCase",
            cases["case-1"].id,
            "CERERE_CHEMARE",
            "cerere-chemare-judecata.txt",
            "Cerere de chemare în judecată – exemplar demonstrativ GovControl.",
        ),
        (
            "doc-2",
            "CourtDecision",
            decisions["decision-2"].id,
            "HOTARARE",
            "decizie-civila-demo.txt",
            "Decizie civilă – conținut demonstrativ pentru fluxul GovLegal.",
        ),
        (
            "doc-3",
            "LegalObligation",
            obligations["ob-01"].id,
            "SUPPORTING_DOCUMENT",
            "nota-plata-cheltuieli.txt",
            "Notă internă privind plata cheltuielilor de judecată.",
        ),
        (
            "doc-4",
            "LegalObligation",
            obligations["ob-05"].id,
            "SUPPORTING_DOCUMENT",
            "plan-masuri-remediere.txt",
            "Plan de măsuri pentru reevaluarea ofertelor.",
        ),
        (
            "doc-5",
            "EnforcementProceeding",
            enforcements["enf-1"].id,
            "EXECUTION_NOTICE",
            "somatie-executare-demo.txt",
            "Somație demonstrativă aferentă dosarului de executare.",
        ),
    )
    for index, (key, entity_type, entity_id, category, filename, text) in enumerate(
        document_definitions
    ):
        content = text.encode("utf-8")
        document = await upsert(
            session,
            Document,
            key,
            {
                "tenant_id": tenant.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "category": category,
                "original_filename": filename,
                "content_type": "text/plain; charset=utf-8",
                "size_bytes": len(content),
                "checksum_sha256": hashlib.sha256(content).hexdigest(),
                "storage_key": f"{tenant.id}/{demo_id(key)}",
                "uploaded_by_user_id": administrator.id,
                "created_at": datetime.now(UTC) - timedelta(days=index + 1),
            },
        )
        storage.write(str(tenant.id), str(document.id), content)

    audit_entities: list[tuple[str, str, uuid.UUID]] = []
    audit_entities.extend(
        (f"audit:case:{key}", "LegalCase", item.id) for key, item in cases.items()
    )
    audit_entities.extend(
        (f"audit:obligation:{key}", "LegalObligation", item.id) for key, item in obligations.items()
    )
    audit_entities.extend(
        (f"audit:enforcement:{key}", "EnforcementProceeding", item.id)
        for key, item in enforcements.items()
    )
    for index, (key, entity_type, entity_id) in enumerate(audit_entities):
        await upsert(
            session,
            AuditEvent,
            key,
            {
                "tenant_id": tenant.id,
                "actor_user_id": administrator.id,
                "action": "CREATED" if index % 4 else "STATUS_CHANGED",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_value": None,
                "new_value": {"source": "development-demo", "verified": True},
                "request_id": None,
                "created_at": datetime.now(UTC) - timedelta(hours=index * 3),
            },
        )
