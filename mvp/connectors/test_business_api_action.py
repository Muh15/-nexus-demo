from __future__ import annotations

import json

import httpx
import pytest

from .business_api_action import BusinessActionConfig, BusinessActionConnector


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


def test_action_rejects_unsupported_method():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="POST and PATCH"):
        connector.execute("DELETE", "/contacts/42", {}, "EXE-123")


def test_action_retries_transient_status(monkeypatch):
    calls = []

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
    connector = BusinessActionConnector(
        BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), max_retries=2, retry_backoff_seconds=0)
    )
    result = connector.execute("POST", "/sync", {"id": 1}, "EXE-RETRY")

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert len(calls) == 2
    assert calls[0][2]["headers"]["Idempotency-Key"] == "EXE-RETRY"


def test_action_enforces_request_limit():
    connector = BusinessActionConnector(
        BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"}), max_request_bytes=10)
    )
    with pytest.raises(ValueError, match="request exceeds"):
        connector.execute("POST", "/sync", {"payload": "too large"}, "EXE-LIMIT")


def test_action_requires_execution_id():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="execution_id"):
        connector.execute("POST", "/sync", {}, "")
