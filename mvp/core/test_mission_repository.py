import pytest

from core.mission_repository import SQLiteMissionRepository
from core.orchestrator import MissionOrchestrator
from core.reasoner import reason_from_evidence
from core.sqlite_store import SQLiteMissionStore


def test_sqlite_mission_repository_round_trips_native_state(tmp_path):
    repository = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "missions.sqlite3"))
    orchestrator = MissionOrchestrator(
        lambda goal, constraints, context: reason_from_evidence(goal, constraints, context).as_dict()
    )
    mission = orchestrator.create(
        tenant_id="tenant-a",
        goal="Reduce operating cost by 10%",
        records=[{"supplier": "ABC", "monthly_spend": 420000}],
        source="erp",
    )
    orchestrator.decide(mission)
    orchestrator.plan(mission, target="ABC")
    orchestrator.approve(mission)

    repository.save(mission, updated_at="2026-09-02T00:00:00+00:00")
    restored = repository.get("tenant-a", mission.id)

    assert restored is not None
    assert restored.id == mission.id
    assert restored.tenant_id == "tenant-a"
    assert restored.stage == "approved"
    assert restored.action_plan is not None

    assert repository.get("tenant-b", mission.id) is None
    assert repository.list_by_tenant("tenant-a")[0].id == mission.id


def test_mission_tenant_cannot_be_rebound(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.sqlite3")
    store.save("mission-1", {"tenant_id": "tenant-a"}, "2026-09-02T00:00:00+00:00", tenant_id="tenant-a")

    with pytest.raises(ValueError, match="tenant cannot be changed"):
        store.save("mission-1", {"tenant_id": "tenant-b"}, "2026-09-02T00:01:00+00:00", tenant_id="tenant-b")

    assert store.get("mission-1", tenant_id="tenant-a") == {"tenant_id": "tenant-a"}
    assert store.get("mission-1", tenant_id="tenant-b") is None


def test_mission_events_cannot_cross_tenants(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.sqlite3")
    store.save("mission-1", {"tenant_id": "tenant-a"}, "2026-09-02T00:00:00+00:00", tenant_id="tenant-a")

    assert store.append_event(
        mission_id="mission-1",
        tenant_id="tenant-a",
        event={"stage": "created"},
        recorded_at="2026-09-02T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="event tenant does not match"):
        store.append_event(
            mission_id="mission-1",
            tenant_id="tenant-b",
            event={"stage": "attacker"},
            recorded_at="2026-09-02T00:01:00+00:00",
        )

    assert store.list_events("mission-1", tenant_id="tenant-a")
    assert store.list_events("mission-1", tenant_id="tenant-b") == []
