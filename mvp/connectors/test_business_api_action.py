from __future__ import annotations

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
    assert captured["json"] == {"status": "review"}


def test_action_rejects_unscoped_host():
    with pytest.raises(ValueError, match="allow-listed"):
        BusinessActionConnector(BusinessActionConfig("crm", "https://evil.example", frozenset({"crm.example"})))


def test_action_rejects_unsupported_method():
    connector = BusinessActionConnector(BusinessActionConfig("crm", "https://crm.example", frozenset({"crm.example"})))
    with pytest.raises(ValueError, match="POST and PATCH"):
        connector.execute("DELETE", "/contacts/42", {}, "EXE-123")
