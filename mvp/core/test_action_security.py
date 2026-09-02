from __future__ import annotations

from core.action_executor import ActionExecutor, ActionResult
from core.planner import action_fingerprint, plan_action


def _handler(plan):
    return ActionResult(plan.action_type, "completed", {"ok": True})


def test_action_fingerprint_is_stable_and_payload_bound():
    first = action_fingerprint("update_crm", "customer-1", {"status": "approved", "value": 10})
    second = action_fingerprint("UPDATE_CRM", "customer-1", {"value": 10, "status": "approved"})
    changed = action_fingerprint("update_crm", "customer-1", {"status": "approved", "value": 11})
    assert first == second
    assert first != changed


def test_approval_is_bound_to_exact_action_payload():
    plan = plan_action("Update customer", target="customer-1", action_type="update_crm", body={"status": "approved"})
    approved = plan.__class__(plan.action_type, plan.description, plan.policy, {**plan.payload, "approved": True, "approved_fingerprint": plan.payload["action_fingerprint"]})
    result = ActionExecutor({"update_crm": _handler}).execute(approved)
    assert result.status == "completed"


def test_changed_payload_invalidates_approval():
    plan = plan_action("Update customer", target="customer-1", action_type="update_crm", body={"status": "approved"})
    approved = plan.__class__(plan.action_type, plan.description, plan.policy, {**plan.payload, "approved": True, "approved_fingerprint": plan.payload["action_fingerprint"], "body": {"status": "rejected"}})
    result = ActionExecutor({"update_crm": _handler}).execute(approved)
    assert result.status == "blocked"
    assert "payload changed" in result.message
