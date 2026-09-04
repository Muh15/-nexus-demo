from __future__ import annotations

from core.action_executor import ActionExecutor, ActionResult
from core.planner import action_fingerprint, plan_action
from core.sqlite_store import SQLiteMissionStore


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


def test_durable_execution_id_is_replayed_without_reinvoking_handler(tmp_path):
    store = SQLiteMissionStore(tmp_path / "nexus.sqlite3")
    calls = []

    def counting_handler(plan):
        calls.append(plan.payload["execution_id"])
        return ActionResult(plan.action_type, "completed", {"ok": True, "calls": len(calls)})

    executor = ActionExecutor({"update_crm": counting_handler}, execution_store=store)
    plan = plan_action("Update customer", target="customer-1", action_type="update_crm", body={"status": "approved"})
    fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
    approved = plan.__class__(
        plan.action_type,
        plan.description,
        plan.policy,
        {**plan.payload, "approved": True, "approved_fingerprint": fingerprint, "execution_id": "EXE-REPLAY-001"},
    )

    first = executor.execute(approved)
    second = executor.execute(approved)

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.execution_id == first.execution_id == "EXE-REPLAY-001"
    assert second.output == first.output
    assert calls == ["EXE-REPLAY-001"]


def test_execution_id_cannot_be_rebound_to_changed_action(tmp_path):
    store = SQLiteMissionStore(tmp_path / "nexus.sqlite3")
    executor = ActionExecutor({"update_crm": _handler}, execution_store=store)

    first_plan = plan_action("Update customer", target="customer-1", action_type="update_crm", body={"status": "approved"})
    first_fingerprint = action_fingerprint(first_plan.action_type, first_plan.payload.get("target"), dict(first_plan.payload.get("body", {})))
    first = first_plan.__class__(
        first_plan.action_type,
        first_plan.description,
        first_plan.policy,
        {**first_plan.payload, "approved": True, "approved_fingerprint": first_fingerprint, "execution_id": "EXE-CONFLICT-001"},
    )
    assert executor.execute(first).status == "completed"

    changed_plan = plan_action("Update customer", target="customer-1", action_type="update_crm", body={"status": "rejected"})
    changed_fingerprint = action_fingerprint(changed_plan.action_type, changed_plan.payload.get("target"), dict(changed_plan.payload.get("body", {})))
    changed = changed_plan.__class__(
        changed_plan.action_type,
        changed_plan.description,
        changed_plan.policy,
        {**changed_plan.payload, "approved": True, "approved_fingerprint": changed_fingerprint, "execution_id": "EXE-CONFLICT-001"},
    )
    result = executor.execute(changed)
    assert result.status == "blocked"
    assert "different action or tenant" in result.message
