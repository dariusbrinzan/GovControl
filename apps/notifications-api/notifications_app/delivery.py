import logging
import asyncio
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from notifications_app.config import Settings
from notifications_app.models import Channel, Notification

logger = logging.getLogger("govnotifications.delivery")


class DeliveryAdapter(ABC):
    @abstractmethod
    async def deliver(self, notification: Notification, recipient_address: str | None) -> None:
        raise NotImplementedError


class InAppAdapter(DeliveryAdapter):
    async def deliver(self, notification: Notification, recipient_address: str | None) -> None:
        return None


class LocalEmailAdapter(DeliveryAdapter):
    """Development sink: log metadata only and never send a real message."""

    async def deliver(self, notification: Notification, recipient_address: str | None) -> None:
        logger.info(
            "local_email_delivered notification_id=%s category=%s",
            notification.id,
            notification.category,
        )


class SMTPEmailAdapter(DeliveryAdapter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def deliver(self, notification: Notification, recipient_address: str | None) -> None:
        if recipient_address is None:
            raise RuntimeError("RECIPIENT_UNAVAILABLE")
        await asyncio.to_thread(self._send, notification, recipient_address)

    def _send(self, notification: Notification, recipient_address: str) -> None:
        settings = self.settings
        if not all(
            (
                settings.smtp_host,
                settings.smtp_username,
                settings.smtp_password,
                settings.smtp_from_address,
            )
        ):
            raise RuntimeError("SMTP_NOT_CONFIGURED")
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = settings.smtp_from_address
        message["To"] = recipient_address
        message.set_content(notification.body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls()
            client.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value(),
            )
            client.send_message(message)


class DisabledWebhookAdapter(DeliveryAdapter):
    async def deliver(self, notification: Notification, recipient_address: str | None) -> None:
        raise RuntimeError("WEBHOOK_DISABLED")


def configured_adapters(settings: Settings) -> dict[Channel, DeliveryAdapter]:
    adapters: dict[Channel, DeliveryAdapter] = {Channel.IN_APP: InAppAdapter()}
    if settings.email_enabled and settings.email_adapter == "local":
        adapters[Channel.EMAIL] = LocalEmailAdapter()
    elif settings.email_enabled and settings.email_adapter == "smtp":
        adapters[Channel.EMAIL] = SMTPEmailAdapter(settings)
    return adapters
