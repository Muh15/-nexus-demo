from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ActorRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: str
    role: ActorRole


class AuthenticationError(ValueError):
    """Raised when an API credential cannot be resolved to a principal."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def configured_principals() -> dict[str, Principal]:
    """Read server-side API credentials without exposing raw tokens.

    Format: NEXUS_API_KEYS="token=subject:tenant:role,token2=subject2:tenant2:role"
    Tokens stay in the environment; only SHA-256 digests are retained in the map.
    """
    raw = os.getenv("NEXUS_API_KEYS", "").strip()
    principals: dict[str, Principal] = {}
    if not raw:
        return principals
    for entry in raw.split(","):
        item = entry.strip()
        if not item or "=" not in item:
            continue
        token, identity = item.split("=", 1)
        parts = [part.strip() for part in identity.split(":")]
        if len(parts) != 3 or not all(parts):
            continue
        subject, tenant_id, role_text = parts
        try:
            role = ActorRole(role_text.lower())
        except ValueError:
            continue
        principals[_hash_token(token.strip())] = Principal(subject=subject, tenant_id=tenant_id, role=role)
    return principals


def authenticate_api_key(token: str, principals: Mapping[str, Principal] | None = None) -> Principal:
    """Resolve a bearer/API key to a server-defined principal."""
    if not token.strip():
        raise AuthenticationError("API key is required")
    lookup = principals if principals is not None else configured_principals()
    principal = lookup.get(_hash_token(token.strip()))
    if principal is None:
        raise AuthenticationError("Invalid API key")
    return principal
