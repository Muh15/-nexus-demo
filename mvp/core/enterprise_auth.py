from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import jwt
from jwt import PyJWKClient

from .auth import ActorRole, AuthenticationError, Principal, authenticate_api_key


class PrincipalProvider(Protocol):
    def authenticate(self, credential: str) -> Principal: ...


@dataclass(frozen=True, slots=True)
class ApiKeyProvider:
    principals: Mapping[str, Principal] | None = None

    def authenticate(self, credential: str) -> Principal:
        return authenticate_api_key(credential, self.principals)


@dataclass(frozen=True, slots=True)
class OIDCConfig:
    issuer: str
    audience: str
    jwks_url: str
    algorithms: tuple[str, ...] = ("RS256",)


_ALLOWED_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})


class OIDCJWTProvider:
    """Validate an OIDC/JWT bearer credential against an issuer's JWKS."""

    def __init__(self, config: OIDCConfig) -> None:
        if not config.issuer.strip() or not config.audience.strip() or not config.jwks_url.strip():
            raise ValueError("OIDC issuer, audience and JWKS URL are required")
        if not config.jwks_url.startswith("https://"):
            raise ValueError("OIDC JWKS URL must use HTTPS")
        if not config.algorithms:
            raise ValueError("at least one JWT algorithm is required")
        normalized = tuple(item.strip().upper() for item in config.algorithms if item.strip())
        if not normalized or any(item not in _ALLOWED_JWT_ALGORITHMS for item in normalized):
            raise ValueError("OIDC JWT algorithms must be approved asymmetric algorithms")
        self._config = OIDCConfig(config.issuer.strip(), config.audience.strip(), config.jwks_url.strip(), normalized)
        self._jwk_client = PyJWKClient(self._config.jwks_url, cache_jwk_set=True, lifespan=300)

    def authenticate(self, credential: str) -> Principal:
        token = credential.strip()
        if not token:
            raise AuthenticationError("Bearer token is required")
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token).key
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key,
                algorithms=list(self._config.algorithms),
                audience=self._config.audience,
                issuer=self._config.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired bearer token") from exc

        subject = str(claims.get("sub", "")).strip()
        tenant_id = str(claims.get(os.getenv("NEXUS_OIDC_TENANT_CLAIM", "tenant_id"), "")).strip()
        role_text = str(claims.get(os.getenv("NEXUS_OIDC_ROLE_CLAIM", "role"), "")).strip().lower()
        if not subject or not tenant_id:
            raise AuthenticationError("Bearer token is missing required principal claims")
        try:
            role = ActorRole(role_text)
        except ValueError as exc:
            raise AuthenticationError("Bearer token contains an invalid principal role") from exc
        return Principal(subject=subject, tenant_id=tenant_id, role=role)


def build_principal_provider() -> PrincipalProvider:
    """Build the configured enterprise authentication provider."""
    mode = os.getenv("NEXUS_AUTH_MODE", "api_key").strip().lower()
    if mode == "api_key":
        return ApiKeyProvider()
    if mode != "oidc":
        raise ValueError("NEXUS_AUTH_MODE must be 'api_key' or 'oidc'")
    return OIDCJWTProvider(
        OIDCConfig(
            issuer=os.getenv("NEXUS_OIDC_ISSUER", ""),
            audience=os.getenv("NEXUS_OIDC_AUDIENCE", ""),
            jwks_url=os.getenv("NEXUS_OIDC_JWKS_URL", ""),
            algorithms=tuple(item.strip() for item in os.getenv("NEXUS_OIDC_ALGORITHMS", "RS256").split(",") if item.strip()),
        )
    )
