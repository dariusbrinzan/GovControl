import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select

from contracts_app.config import get_settings
from contracts_app.database import session_factory
from contracts_app.models import (
    Contract,
    ContractAmendment,
    ContractMilestone,
    ContractObligation,
    ContractParty,
    ContractPartyLink,
    ContractPayment,
    ContractStatus,
    MilestoneStatus,
    ObligationStatus,
    PaymentStatus,
)
from contracts_app.schemas import UserContext

SEED_NAMESPACE = uuid.UUID("499d3b54-8c36-4aeb-a6a9-c88466200616")


def stable_id(name: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, name)


async def platform_identity() -> UserContext:
    settings = get_settings()
    if settings.dev_auth_token is None:
        raise RuntimeError("DEV_AUTH_TOKEN is required to seed GovContracts.")
    headers = {"Authorization": f"Bearer {settings.dev_auth_token.get_secret_value()}"}
    auth_path = "/auth/me"
    if settings.internal_service_token is not None:
        auth_path = "/internal/auth/context"
        headers["X-Service-Token"] = settings.internal_service_token.get_secret_value()
    async with httpx.AsyncClient(timeout=settings.platform_request_timeout_seconds) as client:
        response = await client.get(
            f"{settings.platform_api_url.rstrip('/')}{auth_path}",
            headers=headers,
        )
    response.raise_for_status()
    return UserContext.model_validate(response.json())


async def seed_contract_document(contract_id: uuid.UUID) -> None:
    settings = get_settings()
    if settings.dev_auth_token is None:
        raise RuntimeError("DEV_AUTH_TOKEN is required to seed GovContracts documents.")
    headers = {"Authorization": f"Bearer {settings.dev_auth_token.get_secret_value()}"}
    base_url = settings.platform_api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.platform_request_timeout_seconds) as client:
        response = await client.get(
            f"{base_url}/documents",
            params={"entity_type": "Contract", "entity_id": str(contract_id)},
            headers=headers,
        )
        response.raise_for_status()
        if any(item["original_filename"] == "govcontracts-demo.txt" for item in response.json()):
            return
        response = await client.post(
            f"{base_url}/documents",
            headers=headers,
            data={
                "entity_type": "Contract",
                "entity_id": str(contract_id),
                "category": "CONTRACT_DOCUMENT",
            },
            files={
                "file": (
                    "govcontracts-demo.txt",
                    b"Document demonstrativ asociat contractului CTR-DEMO-001.\n",
                    "text/plain",
                )
            },
        )
        response.raise_for_status()


async def seed_contracts() -> None:
    identity = await platform_identity()
    today = date.today()
    definitions = (
        (
            "CTR-DEMO-001",
            "Mentenanță platformă digitală",
            "185000.00",
            -60,
            20,
            ContractStatus.ACTIVE,
        ),
        ("CTR-DEMO-002", "Furnizare echipamente IT", "420000.00", 15, 210, ContractStatus.DRAFT),
        (
            "CTR-DEMO-003",
            "Servicii arhivare electronică",
            "96000.00",
            -180,
            90,
            ContractStatus.SUSPENDED,
        ),
        (
            "CTR-DEMO-004",
            "Consultanță proceduri interne",
            "74000.00",
            -360,
            -15,
            ContractStatus.COMPLETED,
        ),
        (
            "CTR-DEMO-005",
            "Modernizare infrastructură rețea",
            "630000.00",
            -30,
            330,
            ContractStatus.ACTIVE,
        ),
        (
            "CTR-DEMO-006",
            "Licențe și suport securitate",
            "210000.00",
            30,
            395,
            ContractStatus.IN_REVIEW,
        ),
    )
    async with session_factory() as session, session.begin():
        for number, title, value, start_offset, end_offset, status in definitions:
            item_id = stable_id(number)
            item = await session.get(Contract, item_id)
            values = {
                "tenant_id": identity.tenant_id,
                "contract_number": number,
                "title": title,
                "description": "Înregistrare demonstrativă GovContracts.",
                "value": Decimal(value),
                "currency": "RON",
                "signed_date": today + timedelta(days=min(start_offset - 5, -1)),
                "start_date": today + timedelta(days=start_offset),
                "end_date": today + timedelta(days=end_offset),
                "status": status,
                "created_by": identity.id,
            }
            if item is None:
                session.add(Contract(id=item_id, **values))
            else:
                for field, field_value in values.items():
                    setattr(item, field, field_value)

        contract_id = stable_id("CTR-DEMO-001")
        party_id = stable_id("CTR-DEMO-001-party")
        if await session.get(ContractParty, party_id) is None:
            session.add(
                ContractParty(
                    id=party_id,
                    tenant_id=identity.tenant_id,
                    name="Servicii Digitale Demonstrative SRL",
                    registration_number="RO-DEMO-1001",
                    party_type="SUPPLIER",
                    email="contracte@example.test",
                )
            )
            session.add(
                ContractPartyLink(
                    tenant_id=identity.tenant_id,
                    contract_id=contract_id,
                    party_id=party_id,
                    role="CONTRACTOR",
                )
            )

        nested_records = (
            ContractAmendment(
                id=stable_id("CTR-DEMO-001-amendment"),
                tenant_id=identity.tenant_id,
                contract_id=contract_id,
                amendment_number="AA-DEMO-001",
                signed_date=today - timedelta(days=10),
                description="Actualizarea nivelului de servicii.",
            ),
            ContractMilestone(
                id=stable_id("CTR-DEMO-001-milestone"),
                tenant_id=identity.tenant_id,
                contract_id=contract_id,
                title="Raport lunar de disponibilitate",
                due_date=today + timedelta(days=5),
                status=MilestoneStatus.IN_PROGRESS,
            ),
            ContractObligation(
                id=stable_id("CTR-DEMO-001-obligation"),
                tenant_id=identity.tenant_id,
                contract_id=contract_id,
                description="Transmiterea raportului de mentenanță.",
                due_date=today + timedelta(days=7),
                status=ObligationStatus.OPEN,
            ),
            ContractPayment(
                id=stable_id("CTR-DEMO-001-payment"),
                tenant_id=identity.tenant_id,
                contract_id=contract_id,
                amount=Decimal("25000.00"),
                currency="RON",
                due_date=today + timedelta(days=12),
                status=PaymentStatus.APPROVED,
                reference="Tranșă servicii curente",
            ),
        )
        for record in nested_records:
            model = type(record)
            if await session.scalar(select(model.id).where(model.id == record.id)) is None:
                session.add(record)
    await seed_contract_document(contract_id)


def main() -> None:
    asyncio.run(seed_contracts())


if __name__ == "__main__":
    main()
