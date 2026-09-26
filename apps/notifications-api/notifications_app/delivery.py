import asyncio
import logging
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
        host = settings.smtp_host
        username = settings.smtp_username
        password = settings.smtp_password
        from_address = settings.smtp_from_address
        if not all((host, username, password, from_address)):
            raise RuntimeError("SMTP_NOT_CONFIGURED")
        assert host is not None
        assert username is not None
        assert password is not None
        assert from_address is not None
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = from_address
        message["To"] = recipient_address
        message.set_content(notification.body)
        with smtplib.SMTP(host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_use_tls:
                client.starttls()
            client.login(
                username,
                password.get_secret_value(),
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
