from core.auth import ActorRole, AuthenticationError, Principal, authenticate_api_key, configured_principals


def test_authenticate_api_key_resolves_server_defined_principal():
    principals = {
        "hashed": Principal(subject="alice", tenant_id="tenant-a", role=ActorRole.APPROVER),
    }

    import hashlib

    token = "secret-token"
    lookup = {hashlib.sha256(token.encode()).hexdigest(): principals["hashed"]}
    principal = authenticate_api_key(token, lookup)

    assert principal.subject == "alice"
    assert principal.tenant_id == "tenant-a"
    assert principal.role is ActorRole.APPROVER


def test_authenticate_api_key_rejects_unknown_credential():
    try:
        authenticate_api_key("nope", {})
    except AuthenticationError as exc:
        assert "Invalid API key" in str(exc)
    else:
        raise AssertionError("Expected AuthenticationError")


def test_configured_principals_ignores_invalid_entries(monkeypatch):
    monkeypatch.setenv(
        "NEXUS_API_KEYS",
        "good=alice:tenant-a:approver,bad-role=bob:tenant-b:superuser,broken-entry,no-role=c:tenant-c",
    )
    principals = configured_principals()
    assert len(principals) == 1
    principal = next(iter(principals.values()))
    assert principal.subject == "alice"
    assert principal.tenant_id == "tenant-a"
    assert principal.role is ActorRole.APPROVER
