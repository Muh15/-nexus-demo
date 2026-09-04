from __future__ import annotations

import httpx

from connectors.business_api_action import BusinessActionConnector
from core.planner import action_fingerprint, plan_action
from core.runtime import _real_action_handler


def test_real_action_handler_redacts_sensitive_fields_and_configured_token(monkeypatch):
    monkeypatch.setenv("CRM_TOKEN", "super-secret-token")
    connector = BusinessActionConnector(
        __import__("connectors.business_api_action", fromlist=["BusinessActionConfig"]).BusinessActionConfig(
            name="crm",
            base_url="https://crm.example.test",
            allowed_hosts=frozenset({"crm.example.test"}),
            token_env="CRM_TOKEN",
        )
    )

    class MockClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "token": "super-secret-token",
                    "nested": {"password": "secret-password"},
                    "echo": "received super-secret-token",
                },
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(httpx, "Client", MockClient)
    handler = _real_action_handler(connector, "/api/opportunities/42", "PATCH")
    plan = plan_action(
        "Update CRM",
        target="opportunity-42",
        action_type="update_crm",
        body={"stage": "negotiation", "api_token": "super-secret-token", "password": "secret-password"},
    )
    fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
    plan = type(plan)(plan.action_type, plan.description, plan.policy, {**plan.payload, "approved": True, "approved_fingerprint": fingerprint})

    result = handler(type("ExecutablePlan", (), {"action_type": plan.action_type, "payload": {**plan.payload, "execution_id": "EXE-REDAC"}})())

    serialized = repr(result.output)
    assert "super-secret-token" not in serialized
    assert "secret-password" not in serialized
    assert result.output["request_body"]["api_token"] == "[REDACTED]"
    assert result.output["request_body"]["password"] == "[REDACTED]"
    assert result.output["body"]["token"] == "[REDACTED]"
    assert result.output["body"]["nested"]["password"] == "[REDACTED]"
