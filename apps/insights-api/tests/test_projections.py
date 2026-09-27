import uuid
from datetime import UTC, datetime

from insights_app.projections import controlled_projection
from insights_app.schemas import EventEnvelope


def envelope(**payload: object) -> EventEnvelope:
    return EventEnvelope(
        id=uuid.uuid4(),
        type="contracts.contract.created.v1",
        tenant_id=uuid.uuid4(),
        aggregate_type="contract",
        aggregate_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        payload=payload,
    )


def test_projection_accepts_only_controlled_metadata() -> None:
    event = envelope(
        identifier="CTR-2026-1",
        display_label="Contract public metadata",
        status="ACTIVE",
        amount="123.45",
        currency="ron",
        document_content="must never be copied",
        access_token="secret",
    )
    projection = controlled_projection(event)
    assert projection is not None
    assert projection["currency"] == "RON"
    assert str(projection["amount"]) == "123.45"
    assert "document_content" not in projection["attributes"]
    assert "access_token" not in projection["attributes"]
    assert projection["source_url"].startswith("/contracts/")


def test_unknown_event_is_recorded_but_not_projected() -> None:
    event = envelope(identifier="ignored")
    event.type = "external.unknown.v1"
    event.aggregate_type = "unknown"
    assert controlled_projection(event) is None


def test_invalid_currency_is_not_aggregated() -> None:
    projection = controlled_projection(envelope(amount="100", currency="EURO"))
    assert projection is not None
    assert projection["currency"] is None
