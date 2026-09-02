from core.orchestrator import MissionOrchestrator, mission_from_snapshot
from core.reasoner import reason_from_evidence


def test_mission_snapshot_round_trip_preserves_executable_lifecycle():
    orchestrator = MissionOrchestrator(
        lambda goal, constraints, context: reason_from_evidence(goal, constraints, context).as_dict()
    )
    mission = orchestrator.create(
        tenant_id="tenant-a",
        goal="Reduce operating cost by 10% within 90 days",
        constraints=["Do not change quality"],
        records=[{"supplier": "ABC", "contract": "ABC-2026", "monthly_spend": 420000}],
        source="xlsx",
    )
    orchestrator.decide(mission)
    orchestrator.plan(mission, target="ABC")
    orchestrator.approve(mission)

    restored = mission_from_snapshot(mission.snapshot())

    assert restored.id == mission.id
    assert restored.tenant_id == mission.tenant_id
    assert restored.stage == "approved"
    assert restored.decision == mission.decision
    assert restored.action_plan is not None
    assert restored.action_plan.payload["approved"] is True

    orchestrator.execute(restored)
    assert restored.stage == "executed"
    assert restored.action_result is not None

    orchestrator.verify(restored)
    assert restored.stage == "verified"
    assert restored.verification is not None


def test_snapshot_rejects_missing_identity_fields():
    try:
        mission_from_snapshot({"goal": "x"})
    except ValueError as exc:
        assert "missing fields" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
