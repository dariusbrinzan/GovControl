import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import urlencode

import httpx
import jwt

from gateway_app.config import Settings
from gateway_app.models import OIDCIdentity


class OIDCError(Exception):
    """Safe authentication failure without provider secrets or token contents."""


class RedisOIDCClient(Protocol):
    async def set(self, name: str, value: str, *, ex: int | None = None) -> object: ...

    async def getdel(self, name: str) -> str | bytes | None: ...


@dataclass(frozen=True)
class PreAuthRecord:
    nonce: str
    verifier: str


class OIDCClient:
    preauth_prefix = "govcontrol:gateway:oidc:"

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        redis_client: RedisOIDCClient,
        settings: Settings,
    ) -> None:
        self.http = http_client
        self.redis = redis_client
        self.settings = settings
        self._metadata: dict[str, Any] | None = None
        self._metadata_expires_at = 0.0
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    @property
    def issuer(self) -> str:
        if self.settings.oidc_issuer is None:
            raise OIDCError("OIDC is not configured.")
        return self.settings.oidc_issuer.rstrip("/")

    async def metadata(self) -> dict[str, Any]:
        if self._metadata is not None and self._metadata_expires_at > time.monotonic():
            return self._metadata
        try:
            response = await self.http.get(
                f"{self.issuer}/.well-known/openid-configuration"
            )
            response.raise_for_status()
            metadata = cast("dict[str, Any]", response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("OIDC discovery is unavailable.") from exc
        if metadata.get("issuer", "").rstrip("/") != self.issuer:
            raise OIDCError("OIDC discovery returned an unexpected issuer.")
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not isinstance(metadata.get(field), str):
                raise OIDCError("OIDC discovery is incomplete.")
            if self.settings.app_env == "production" and not metadata[field].startswith(
                "https://"
            ):
                raise OIDCError("OIDC discovery endpoint must use HTTPS.")
        self._metadata = metadata
        self._metadata_expires_at = time.monotonic() + 300
        return metadata

    async def begin(self) -> str:
        metadata = await self.metadata()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        await self.redis.set(
            f"{self.preauth_prefix}{state}",
            json.dumps({"nonce": nonce, "verifier": verifier}),
            ex=self.settings.oidc_preauth_ttl_seconds,
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.oidc_client_id,
                "redirect_uri": self.settings.redirect_uri,
                "scope": self.settings.oidc_scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    async def complete(self, *, state: str, code: str) -> OIDCIdentity:
        raw = await self.redis.getdel(f"{self.preauth_prefix}{state}")
        if raw is None:
            raise OIDCError("OIDC state is invalid or expired.")
        try:
            preauth_data = json.loads(raw)
            preauth = PreAuthRecord(
                nonce=preauth_data["nonce"], verifier=preauth_data["verifier"]
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise OIDCError("OIDC state is invalid or expired.") from exc

        metadata = await self.metadata()
        token_form = {
            "grant_type": "authorization_code",
            "client_id": self.settings.oidc_client_id,
            "code": code,
            "redirect_uri": self.settings.redirect_uri,
            "code_verifier": preauth.verifier,
        }
        if self.settings.oidc_client_secret is not None:
            client_secret = self.settings.oidc_client_secret.get_secret_value()
            if client_secret:
                token_form["client_secret"] = client_secret
        try:
            response = await self.http.post(metadata["token_endpoint"], data=token_form)
            response.raise_for_status()
            id_token = response.json()["id_token"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise OIDCError("OIDC code exchange failed.") from exc
        return await self.validate_id_token(id_token, expected_nonce=preauth.nonce)

    async def jwks(self) -> dict[str, Any]:
        if self._jwks is not None and self._jwks_expires_at > time.monotonic():
            return self._jwks
        metadata = await self.metadata()
        try:
            response = await self.http.get(metadata["jwks_uri"])
            response.raise_for_status()
            jwks = cast("dict[str, Any]", response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCError("OIDC signing keys are unavailable.") from exc
        if not isinstance(jwks.get("keys"), list):
            raise OIDCError("OIDC signing keys are invalid.")
        self._jwks = jwks
        self._jwks_expires_at = time.monotonic() + 300
        return jwks

    async def validate_id_token(self, id_token: str, *, expected_nonce: str) -> OIDCIdentity:
        try:
            header = jwt.get_unverified_header(id_token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise OIDCError("OIDC token algorithm is not allowed.")
            jwks = await self.jwks()
            key_data = next(
                key for key in jwks["keys"] if key.get("kid") == header["kid"]
            )
            key = jwt.PyJWK.from_dict(key_data, algorithm="RS256").key
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.settings.oidc_client_id,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce", "email"]},
            )
        except OIDCError:
            raise
        except (jwt.InvalidTokenError, KeyError, StopIteration, TypeError, ValueError) as exc:
            raise OIDCError("OIDC identity token is invalid.") from exc
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not secrets.compare_digest(nonce, expected_nonce):
            raise OIDCError("OIDC nonce is invalid.")
        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1:
            authorized_party = claims.get("azp")
            if authorized_party != self.settings.oidc_client_id:
                raise OIDCError("OIDC authorized party is invalid.")
        email_verified = claims.get("email_verified") is True
        return OIDCIdentity(
            issuer=self.issuer,
            subject=claims["sub"],
            email=claims["email"],
            email_verified=email_verified,
            display_name=claims.get("name"),
        )
