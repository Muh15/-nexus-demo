from __future__ import annotations

import os

import jwt
import pytest

from core.auth import ActorRole, AuthenticationError, Principal
from core.enterprise_auth import ApiKeyProvider, OIDCConfig, OIDCJWTProvider, build_principal_provider


def test_api_key_provider_preserves_server_principal():
    provider = ApiKeyProvider({"digest": Principal("svc-1", "tenant-1", ActorRole.OPERATOR)})
    # Use a fake mapping directly so the test does not need a real secret.
    assert provider.principals["digest"].tenant_id == "tenant-1"


def test_oidc_config_requires_https_jwks():
    with pytest.raises(ValueError, match="HTTPS"):
        OIDCJWTProvider(OIDCConfig("https://issuer", "nexus", "http://issuer/jwks"))


def test_oidc_rejects_missing_required_principal_claims(monkeypatch):
    class FakeJWK:
        key = "secret"

    class FakeClient:
        def __init__(self, _url, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return FakeJWK()

    monkeypatch.setattr("core.enterprise_auth.PyJWKClient", FakeClient)
    monkeypatch.setattr("core.enterprise_auth.jwt.decode", lambda *args, **kwargs: {"sub": "user-1", "exp": 9999999999, "iat": 1})
    provider = OIDCJWTProvider(OIDCConfig("https://issuer", "nexus", "https://issuer/jwks"))
    with pytest.raises(AuthenticationError, match="required principal claims"):
        provider.authenticate("token")


def test_oidc_maps_verified_claims_to_principal(monkeypatch):
    class FakeJWK:
        key = "secret"

    class FakeClient:
        def __init__(self, _url, **_kwargs):
            pass

        def get_signing_key_from_jwt(self, _token):
            return FakeJWK()

    monkeypatch.setattr("core.enterprise_auth.PyJWKClient", FakeClient)
    monkeypatch.setattr(
        "core.enterprise_auth.jwt.decode",
        lambda *args, **kwargs: {"sub": "user-1", "tenant_id": "tenant-7", "role": "approver", "exp": 9999999999, "iat": 1},
    )
    provider = OIDCJWTProvider(OIDCConfig("https://issuer", "nexus", "https://issuer/jwks"))
    principal = provider.authenticate("token")
    assert principal == Principal("user-1", "tenant-7", ActorRole.APPROVER)


def test_oidc_mode_fails_closed_when_configuration_is_missing(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_MODE", "oidc")
    monkeypatch.delenv("NEXUS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("NEXUS_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("NEXUS_OIDC_JWKS_URL", raising=False)
    with pytest.raises(ValueError, match="issuer, audience and JWKS URL"):
        build_principal_provider()
