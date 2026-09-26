import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import fakeredis.aioredis
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from gateway_app.config import Settings
from gateway_app.oidc import OIDCClient, OIDCError


def oidc_settings() -> Settings:
    return Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example.test",
        oidc_client_id="govcontrol",
    )


def signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()

    def encoded(value: int) -> str:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return private_key, {
        "kty": "RSA",
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
        "n": encoded(numbers.n),
        "e": encoded(numbers.e),
    }


def token(
    private_key: rsa.RSAPrivateKey,
    *,
    issuer: str = "https://identity.example.test",
    audience: str = "govcontrol",
    nonce: str = "expected-nonce",
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": "oidc-user",
            "email": "admin@example.com",
            "email_verified": True,
            "name": "OIDC Admin",
            "nonce": nonce,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


@pytest.mark.asyncio
async def test_authorization_code_flow_uses_pkce_and_one_time_state() -> None:
    private_key, jwk = signing_material()
    observed_verifier = ""
    nonce_for_token = ""

    async def provider(request: httpx.Request) -> httpx.Response:
        nonlocal observed_verifier
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "https://identity.example.test",
                    "authorization_endpoint": "https://identity.example.test/authorize",
                    "token_endpoint": "https://identity.example.test/token",
                    "jwks_uri": "https://identity.example.test/jwks",
                },
            )
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            observed_verifier = form["code_verifier"][0]
            return httpx.Response(
                200, json={"id_token": token(private_key, nonce=nonce_for_token)}
            )
        return httpx.Response(404)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client = OIDCClient(http, redis, oidc_settings())
        authorization_url = await client.begin()
        query = parse_qs(urlparse(authorization_url).query)
        assert query["code_challenge_method"] == ["S256"]
        state = query["state"][0]
        raw = json.loads(await redis.get(f"govcontrol:gateway:oidc:{state}"))
        nonce_for_token = raw["nonce"]
        identity = await client.complete(state=state, code="authorization-code")
        assert identity.subject == "oidc-user"
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(observed_verifier.encode()).digest()
        ).decode().rstrip("=")
        assert query["code_challenge"] == [expected_challenge]
        with pytest.raises(OIDCError, match="state"):
            await client.complete(state=state, code="replay")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("issuer", "audience", "nonce"),
    [
        ("https://evil.example.test", "govcontrol", "expected-nonce"),
        ("https://identity.example.test", "other-client", "expected-nonce"),
        ("https://identity.example.test", "govcontrol", "wrong-nonce"),
    ],
)
async def test_id_token_rejects_wrong_issuer_audience_or_nonce(
    issuer: str, audience: str, nonce: str
) -> None:
    private_key, jwk = signing_material()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with httpx.AsyncClient() as http:
        client = OIDCClient(http, redis, oidc_settings())
        client._jwks = {"keys": [jwk]}
        client._jwks_expires_at = float("inf")
        with pytest.raises(OIDCError):
            await client.validate_id_token(
                token(private_key, issuer=issuer, audience=audience, nonce=nonce),
                expected_nonce="expected-nonce",
            )
