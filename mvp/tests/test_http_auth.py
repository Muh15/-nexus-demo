from __future__ import annotations

from fastapi import HTTPException

from core.auth import ActorRole, Principal
from main import principal_context


def test_oidc_http_boundary_accepts_standard_bearer(monkeypatch):
    class FakeProvider:
        def authenticate(self, credential):
            assert credential == "signed-token"
            return Principal("user-1", "tenant-7", ActorRole.OPERATOR)

    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "oidc")
    monkeypatch.setattr("main.build_principal_provider", lambda: FakeProvider())
    principal = principal_context(None, "Bearer signed-token", None, None)
    assert principal == Principal("user-1", "tenant-7", ActorRole.OPERATOR)


def test_oidc_http_boundary_rejects_non_bearer(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "oidc")
    with __import__("pytest").raises(HTTPException) as exc:
        principal_context(None, "Basic credentials", None, None)
    assert exc.value.status_code == 401


def test_oidc_http_boundary_cannot_override_tenant(monkeypatch):
    class FakeProvider:
        def authenticate(self, _credential):
            return Principal("user-1", "tenant-7", ActorRole.OPERATOR)

    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_AUTH_MODE", "oidc")
    monkeypatch.setattr("main.build_principal_provider", lambda: FakeProvider())
    with __import__("pytest").raises(HTTPException) as exc:
        principal_context(None, "Bearer signed-token", "tenant-8", None)
    assert exc.value.status_code == 403
