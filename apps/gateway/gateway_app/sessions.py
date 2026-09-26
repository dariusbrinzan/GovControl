import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from fastapi import Response

from gateway_app.config import Settings
from gateway_app.models import SessionRecord, UserContext


class RedisSessionClient(Protocol):
    async def set(self, name: str, value: str, *, ex: int | timedelta | None = None) -> object: ...

    async def get(self, name: str) -> str | bytes | None: ...

    async def delete(self, *names: str) -> object: ...

    async def expire(self, name: str, time: int | timedelta) -> object: ...


class SessionStore:
    """Redis-backed server-side sessions with opaque, signed browser handles."""

    key_prefix = "govcontrol:gateway:session:"

    def __init__(self, client: RedisSessionClient, settings: Settings):
        self.client = client
        self.settings = settings

    def _secret(self) -> bytes:
        if self.settings.session_signing_secret is None:
            raise RuntimeError("Session signing is not configured.")
        return self.settings.session_signing_secret.get_secret_value().encode()

    def _signature(self, session_id: str) -> str:
        digest = hmac.new(self._secret(), session_id.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def encode_cookie(self, session_id: str) -> str:
        return f"{session_id}.{self._signature(session_id)}"

    def decode_cookie(self, cookie: str | None) -> str | None:
        if not cookie or "." not in cookie:
            return None
        session_id, signature = cookie.rsplit(".", 1)
        if not session_id or not secrets.compare_digest(signature, self._signature(session_id)):
            return None
        return session_id

    async def create(
        self,
        user: UserContext,
        auth_method: Literal["local", "oidc"],
        *,
        oidc_issuer: str | None = None,
        oidc_subject: str | None = None,
    ) -> SessionRecord:
        now = datetime.now(UTC)
        record = SessionRecord(
            id=secrets.token_urlsafe(32),
            user=user,
            auth_method=auth_method,
            created_at=now,
            rotated_at=now,
            expires_at=now + timedelta(seconds=self.settings.session_ttl_seconds),
            csrf_token=secrets.token_urlsafe(32),
            oidc_issuer=oidc_issuer,
            oidc_subject=oidc_subject,
        )
        await self._write(record)
        return record

    async def _write(self, record: SessionRecord) -> None:
        await self.client.set(
            f"{self.key_prefix}{record.id}",
            record.model_dump_json(),
            ex=self.settings.session_ttl_seconds,
        )

    async def resolve(self, cookie: str | None) -> SessionRecord | None:
        session_id = self.decode_cookie(cookie)
        if session_id is None:
            return None
        raw = await self.client.get(f"{self.key_prefix}{session_id}")
        if raw is None:
            return None
        record = SessionRecord.model_validate_json(raw)
        if record.expires_at <= datetime.now(UTC):
            await self.destroy(record.id)
            return None
        await self.client.expire(
            f"{self.key_prefix}{session_id}", self.settings.session_ttl_seconds
        )
        return record

    def rotation_due(self, record: SessionRecord) -> bool:
        age = datetime.now(UTC) - record.rotated_at
        return age.total_seconds() >= self.settings.session_rotation_seconds

    async def rotate(self, record: SessionRecord) -> SessionRecord:
        rotated = record.model_copy(
            update={
                "id": secrets.token_urlsafe(32),
                "rotated_at": datetime.now(UTC),
                "csrf_token": secrets.token_urlsafe(32),
            }
        )
        await self._write(rotated)
        await self.destroy(record.id)
        return rotated

    async def destroy(self, session_id: str) -> None:
        await self.client.delete(f"{self.key_prefix}{session_id}")

    def set_cookie(self, response: Response, record: SessionRecord) -> None:
        response.set_cookie(
            self.settings.session_cookie_name,
            self.encode_cookie(record.id),
            max_age=self.settings.session_ttl_seconds,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite=self.settings.cookie_samesite,
            domain=self.settings.cookie_domain,
            path="/",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            self.settings.session_cookie_name,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite=self.settings.cookie_samesite,
            domain=self.settings.cookie_domain,
            path="/",
        )
