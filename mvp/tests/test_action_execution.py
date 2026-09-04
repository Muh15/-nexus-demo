from core.action_executor import ActionExecutor, ActionResult
from core.planner import ActionPlan, action_fingerprint
from core.policy import ActionPolicy, ActionRisk


def _approved_plan() -> ActionPlan:
    target = "crm:contact:42"
    body = {"status": "review"}
    fingerprint = action_fingerprint("update_crm", target, body)
    return ActionPlan(
        action_type="update_crm",
        description="Update CRM contact",
        policy=ActionPolicy(risk=ActionRisk.HIGH, requires_approval=True, allowed=True, reason="allowed"),
        payload={
            "target": target,
            "body": body,
            "tenant_id": "tenant-a",
            "approval_required": True,
            "approved": True,
            "action_fingerprint": fingerprint,
            "approved_fingerprint": fingerprint,
            "approved_by_subject": "approver-1",
        },
    )


def test_policy_required_approval_cannot_be_disabled_in_payload():
    plan = _approved_plan()
    plan.payload["approval_required"] = False
    calls = []
    executor = ActionExecutor({
        "update_crm": lambda plan: calls.append(plan) or ActionResult("update_crm", "completed")
    })

    result = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="executor-2")

    assert result.status == "blocked"
    assert "Approval" in result.message
    assert calls == []


def test_approved_fingerprint_must_match_exact_payload():
    plan = _approved_plan()
    plan.payload["body"] = {"status": "approved"}
    executor = ActionExecutor({"update_crm": lambda plan: ActionResult("update_crm", "completed")})

    result = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="executor-2")

    assert result.status == "blocked"
    assert "fingerprint" in result.message


def test_executor_propagates_stable_execution_id_to_handler():
    plan = _approved_plan()
    seen = []
    executor = ActionExecutor({
        "update_crm": lambda executable_plan: seen.append(executable_plan.payload["execution_id"]) or ActionResult("update_crm", "completed")
    })

    first = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="executor-2")
    second = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="executor-2")

    assert first.status == "completed"
    assert second.status == "completed"
    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert all(item.startswith("EXE-") for item in seen)
