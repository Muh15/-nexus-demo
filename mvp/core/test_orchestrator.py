from core.orchestrator import MissionOrchestrator
from core.planner import plan_action
from core.policy import evaluate_action
from main import reason
from core.context_builder import build_context


def bridge_reasoner(goal, constraints, context):
    decision = reason(goal, constraints, [])
    decision_dict = {
        "title": decision.title,
        "summary": decision.summary,
        "priority": decision.priority,
        "confidence": decision.confidence,
        "rationale": decision.rationale,
        "recommended_action": decision.recommended_action,
        "expected_impact": decision.expected_impact,
    }
    return decision_dict


def test_orchestrator_lifecycle_is_explicit():
    orchestrator = MissionOrchestrator(bridge_reasoner)
    mission = orchestrator.create(
        tenant_id="demo-tenant",
        goal="خفض تكلفة التشغيل 10%",
        constraints=["لا تكسر العقود"],
        records=[{"supplier": "ABC", "contract": "ABC-2026", "monthly_spend": 420000}],
        source="xlsx",
    )
    assert mission.stage == "understand"
    orchestrator.decide(mission)
    assert mission.stage == "decide"
    orchestrator.plan(mission, target="ABC")
    assert mission.stage == "action_planned"
    orchestrator.approve(mission)
    assert mission.stage == "approved"
    orchestrator.complete_demo_execution(mission)
    assert mission.stage == "executed"
    orchestrator.verify_demo(mission)
    assert mission.stage == "verified"
    assert mission.verification["status"] == "verified"
    assert len(mission.audit) >= 6


def test_repository_boundary_is_tenant_scoped():
    from core.repository import InMemoryMissionRepository

    repo = InMemoryMissionRepository()
    a = MissionOrchestrator(bridge_reasoner).create(tenant_id="a", goal="هدف أول")
    b = MissionOrchestrator(bridge_reasoner).create(tenant_id="b", goal="هدف ثان")
    repo.save(a)
    repo.save(b)
    assert [m.tenant_id for m in repo.list_by_tenant("a")] == ["a"]
    assert repo.get(a.id) is a


def test_critical_action_cannot_be_approved_through_policy():
    policy = evaluate_action("transfer_money", amount=5000)
    assert policy.allowed is False
    assert policy.requires_approval is True
