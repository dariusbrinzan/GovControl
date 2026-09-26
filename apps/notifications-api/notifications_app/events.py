import uuid
from dataclasses import dataclass
from typing import Any

from notifications_app.schemas import InternalNotificationCreate


class UnsupportedEventError(ValueError):
    pass


@dataclass(frozen=True)
class EventRule:
    template_key: str
    resource_type: str


EVENT_RULES: dict[str, EventRule] = {
    "contracts.contract.created.v1": EventRule("contract.activity", "Contract"),
    "contracts.contract.updated.v1": EventRule("contract.activity", "Contract"),
    "contracts.contract.status-changed.v1": EventRule("contract.activity", "Contract"),
    "contracts.contract.milestone-added.v1": EventRule("contract.milestone", "ContractMilestone"),
    "contracts.contract.milestone-status-changed.v1": EventRule(
        "contract.milestone", "ContractMilestone"
    ),
    "contracts.contract.obligation-added.v1": EventRule(
        "contract.obligation", "ContractObligation"
    ),
    "contracts.contract.obligation-status-changed.v1": EventRule(
        "contract.obligation", "ContractObligation"
    ),
    "contracts.contract.payment-added.v1": EventRule("contract.payment", "ContractPayment"),
    "contracts.contract.payment-status-changed.v1": EventRule(
        "contract.payment", "ContractPayment"
    ),
    "contracts.reminder.milestone-due.v1": EventRule(
        "contract.milestone", "ContractMilestone"
    ),
    "contracts.reminder.obligation-due.v1": EventRule(
        "contract.obligation", "ContractObligation"
    ),
    "contracts.reminder.payment-due.v1": EventRule("contract.payment", "ContractPayment"),
    "document.uploaded.v1": EventRule("document.uploaded", "Document"),
    "document.version_created.v1": EventRule("document.uploaded", "Document"),
    "document.available.v1": EventRule("document.available", "Document"),
    "document.rejected.v1": EventRule("document.rejected", "Document"),
    "document.archived.v1": EventRule("document.archived", "Document"),
    "document.restored.v1": EventRule("document.available", "Document"),
    "legal.deadline.due-soon.v1": EventRule("legal.deadline", "LegalObligation"),
    "legal.deadline.overdue.v1": EventRule("legal.overdue", "LegalObligation"),
    "legal.enforcement.updated.v1": EventRule("legal.enforcement", "EnforcementProceeding"),
    "legal.penalty.exposure.v1": EventRule("legal.penalty", "PenaltyExposure"),
    "administrative.event.v1": EventRule("administrative.event", "AdministrativeEvent"),
    "security.event.v1": EventRule("security.event", "SecurityEvent"),
}


def notification_from_event(envelope: dict[str, Any]) -> InternalNotificationCreate:
    try:
        event_id = uuid.UUID(str(envelope["id"]))
        event_type = str(envelope["type"])
        tenant_id = uuid.UUID(str(envelope["tenant_id"]))
        aggregate_id = uuid.UUID(str(envelope["aggregate_id"]))
        payload = envelope.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("payload")
    except (KeyError, TypeError, ValueError) as exc:
        raise UnsupportedEventError("Invalid event envelope.") from exc
    rule = EVENT_RULES.get(event_type)
    if rule is None:
        raise UnsupportedEventError("Event type is not subscribed.")
    recipient_value = payload.get("recipient_user_id") or payload.get("actor_user_id")
    if recipient_value is None:
        raise UnsupportedEventError("Event has no controlled recipient identifier.")
    try:
        recipient_id = uuid.UUID(str(recipient_value))
    except ValueError as exc:
        raise UnsupportedEventError("Event recipient is invalid.") from exc
    resource_value = payload.get(
        {
            "ContractMilestone": "milestone_id",
            "ContractObligation": "obligation_id",
            "ContractPayment": "payment_id",
        }.get(rule.resource_type, "")
    )
    resource_id = aggregate_id
    if resource_value:
        try:
            resource_id = uuid.UUID(str(resource_value))
        except ValueError as exc:
            raise UnsupportedEventError("Event resource identifier is invalid.") from exc
    action = event_type.removesuffix(".v1").split(".")[-1].replace("-", " ")
    variables = {"resource_id": str(resource_id), "action": action}
    if event_type.startswith("contracts."):
        resource_url = f"/contracts/{aggregate_id}"
    elif event_type.startswith("document."):
        resource_url = f"/legal/documents/{aggregate_id}"
    elif rule.resource_type == "LegalObligation":
        resource_url = f"/legal/obligations/{aggregate_id}"
    elif rule.resource_type == "EnforcementProceeding":
        resource_url = "/legal/enforcements"
    elif rule.resource_type == "PenaltyExposure":
        resource_url = "/legal/penalties"
    else:
        resource_url = None
    return InternalNotificationCreate(
        event_id=event_id,
        event_type=event_type,
        tenant_id=tenant_id,
        recipient_user_id=recipient_id,
        resource_type=rule.resource_type,
        resource_id=resource_id,
        resource_url=resource_url,
        template_key=rule.template_key,
        variables=variables,
        deduplication_key=f"event:{event_id}",
    )
