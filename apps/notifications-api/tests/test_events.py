import uuid

import pytest

from notifications_app.events import UnsupportedEventError, notification_from_event

EVENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
TENANT_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
RESOURCE_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")


def envelope(event_type: str = "document.available.v1") -> dict[str, object]:
    return {
        "id": str(EVENT_ID),
        "type": event_type,
        "tenant_id": str(TENANT_ID),
        "aggregate_id": str(RESOURCE_ID),
        "payload": {
            "recipient_user_id": str(USER_ID),
            "sensitive_title": "must never be copied",
        },
    }


def test_document_event_maps_to_controlled_template() -> None:
    value = notification_from_event(envelope())
    assert value.template_key == "document.available"
    assert value.recipient_user_id == USER_ID
    assert value.variables == {"resource_id": str(RESOURCE_ID), "action": "available"}
    assert "sensitive_title" not in value.variables


def test_contract_child_uses_child_resource_identifier() -> None:
    value = envelope("contracts.contract.payment-added.v1")
    payment_id = uuid.uuid4()
    payload = value["payload"]
    assert isinstance(payload, dict)
    payload["payment_id"] = str(payment_id)
    result = notification_from_event(value)
    assert result.resource_id == payment_id
    assert result.resource_type == "ContractPayment"


def test_event_requires_controlled_recipient() -> None:
    value = envelope()
    value["payload"] = {}
    with pytest.raises(UnsupportedEventError, match="recipient"):
        notification_from_event(value)


def test_unsubscribed_event_is_explicitly_rejected() -> None:
    with pytest.raises(UnsupportedEventError, match="not subscribed"):
        notification_from_event(envelope("unknown.event.v1"))


def test_event_id_is_the_deduplication_key() -> None:
    value = notification_from_event(envelope())
    assert value.event_id == EVENT_ID
    assert value.deduplication_key == f"event:{EVENT_ID}"
