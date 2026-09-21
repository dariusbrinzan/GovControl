from dataclasses import dataclass
from enum import StrEnum


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


@dataclass(frozen=True)
class NotificationMessage:
    recipient: str
    subject: str
    body: str
    channel: NotificationChannel


class NotificationProvider:
    async def send(self, message: NotificationMessage) -> None:
        raise NotImplementedError


class InMemoryNotificationProvider(NotificationProvider):
    """Development provider used until an external delivery channel is configured."""

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    async def send(self, message: NotificationMessage) -> None:
        self.messages.append(message)
