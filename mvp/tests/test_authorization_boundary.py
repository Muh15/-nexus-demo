from core.action_executor import ActionExecutor, ActionResult
from core.planner import ActionPlan
from core.policy import ActionPolicy, ActionRisk


def _plan() -> ActionPlan:
    return ActionPlan(
        action_type="draft_email",
        description="Create a draft",
        policy=ActionPolicy(risk=ActionRisk.LOW, requires_approval=True, allowed=True, reason="allowed"),
        payload={
            "target": "finance@example.com",
            "body": {"subject": "Review"},
            "tenant_id": "tenant-a",
            "approval_required": True,
            "approved": True,
            "action_fingerprint": "",
            "approved_fingerprint": "",
            "approved_by_subject": "approver-1",
        },
    )


def test_separation_of_duties_blocks_same_principal(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_SEPARATION_OF_DUTIES", "true")
    executor = ActionExecutor({"draft_email": lambda plan: ActionResult("draft_email", "completed")})
    result = executor.execute(_plan(), tenant_id="tenant-a", actor_role="operator", actor_subject="approver-1")
    assert result.status == "blocked"
    assert "different principal" in result.message


def test_separation_of_duties_allows_distinct_principal(monkeypatch):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_SEPARATION_OF_DUTIES", "true")
    plan = _plan()
    from core.planner import action_fingerprint
    fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
    plan.payload["action_fingerprint"] = fingerprint
    plan.payload["approved_fingerprint"] = fingerprint
    executor = ActionExecutor({"draft_email": lambda plan: ActionResult("draft_email", "completed")})
    result = executor.execute(plan, tenant_id="tenant-a", actor_role="operator", actor_subject="executor-2")
    assert result.status == "completed"
