from __future__ import annotations

import json
import socket

import httpx
import pytest

from .business_api_action import BusinessActionConfig, BusinessActionConnector


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    def resolve(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_action_sends_idempotency_and_auth(monkeypatch):
    captured = {}

    class MockClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return httpx.Response(200, json={"updated": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setenv("NEXUS_TEST_TOKEN", "secret")
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), "NEXUS_TEST_TOKEN"))
    result = connector.execute("PATCH", "/contacts/42", {"status": "review"}, "EXE-123")

    assert result["ok"] is True
    assert captured["headers"]["Idempotency-Key"] == "EXE-123"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert json.loads(captured["content"]) == {"status": "review"}


def test_action_rejects_unscoped_host():
    with pytest.raises(ValueError, match="allow-listed"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://evil.example", frozenset({"crm.example"})))


def test_action_rejects_private_literal_destination():
    with pytest.raises(ValueError, match="non-public"):
        BusinessActionConnector(BusinessActionConfig("crm", "http://127.0.0.1", frozenset({"127.0.0.1"})))


def test_action_rejects_private_dns_destination(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))])
    with pytest.raises(ValueError, match="non-public"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://crm.internal", frozenset({"crm.internal"})))


def test_action_allows_private_destination_only_when_explicitly_enabled():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.internal", frozenset({"crm.internal"}), allow_private_ips=True))
    assert connector.config.allow_private_ips is True


def test_action_rejects_credential_bearing_base_url():
    with pytest.raises(ValueError, match="credentials"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://user:secret@crm.example", frozenset({"crm.example"})))


def test_action_rejects_query_bearing_base_url():
    with pytest.raises(ValueError, match="query parameters"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example/api?token=secret", frozenset({"crm.example"})))


def test_action_rejects_query_bearing_endpoint():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="query parameters"):
        connector.execute("POST", "/sync?token=secret", {}, "EXE-QUERY")


def test_action_rejects_unsupported_method():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="POST and PATCH"):
        connector.execute("DELETE", "/contacts/42", {}, "EXE-123")


def test_action_retries_transient_status(monkeypatch):
    calls = []
    sleeps = []

    class MockClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            status = 503 if len(calls) == 1 else 200
            return httpx.Response(status, json={"ok": status == 200}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setattr("connectors.business_api_action.time.sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr("connectors.business_api_action.random.random", lambda: 0.0)
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), max_retries=2, retry_backoff_seconds=0.25, retry_backoff_max_seconds=2.0, retry_jitter_ratio=0.25))
    result = connector.execute("POST", "/sync", {"id": 1}, "EXE-RETRY")

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert len(calls) == 2
    assert sleeps == [0.25]
    assert calls[0][2]["headers"]["Idempotency-Key"] == "EXE-RETRY"


def test_action_honors_bounded_retry_after(monkeypatch):
    sleeps = []

    class MockClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            response = httpx.Response(429, json={"ok": False}, request=httpx.Request(method, url))
            response.headers["Retry-After"] = "5"
            return response

    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setattr("connectors.business_api_action.time.sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr("connectors.business_api_action.random.random", lambda: 0.0)
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), max_retries=1, retry_backoff_seconds=0.1, retry_backoff_max_seconds=1.0, retry_jitter_ratio=0.0))
    result = connector.execute("POST", "/sync", {"id": 1}, "EXE-RETRY-AFTER")

    assert result["ok"] is False
    assert result["attempts"] == 2
    assert sleeps == [1.0]


def test_action_enforces_request_limit():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), max_request_bytes=10))
    with pytest.raises(ValueError, match="request exceeds"):
        connector.execute("POST", "/sync", {"payload": "too large"}, "EXE-LIMIT")


def test_action_rejects_invalid_retry_settings():
    with pytest.raises(ValueError, match="retry backoff/jitter"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), retry_backoff_max_seconds=0))


def test_action_requires_execution_id():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="execution_id"):
        connector.execute("POST", "/sync", {}, "")
