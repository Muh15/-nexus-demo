from core.mission_repository import SQLiteMissionRepository
from core.orchestrator import MissionState
from core.sqlite_store import SQLiteMissionStore


def test_mission_history_is_append_only_and_deduplicated(tmp_path):
    repository = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "history.sqlite3"))
    mission = MissionState(id="NXS-HISTORY", tenant_id="tenant-a", goal="Reduce cost")
    mission.log("observe", "started")
    repository.save(mission, updated_at="2026-09-03T00:00:00+00:00")
    mission.log("decide", "decision ready")
    repository.save(mission, updated_at="2026-09-03T00:01:00+00:00")
    repository.save(mission, updated_at="2026-09-03T00:02:00+00:00")

    events = repository.history("tenant-a", "NXS-HISTORY")
    assert [item["event"]["stage"] for item in events] == ["observe", "decide"]
    assert len(events) == 2
    assert events[0]["tenant_id"] == "tenant-a"


def test_mission_history_is_tenant_scoped(tmp_path):
    repository = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "history-tenant.sqlite3"))
    mission = MissionState(id="NXS-SHARED", tenant_id="tenant-a", goal="Reduce cost")
    mission.log("observe", "tenant-a event")
    repository.save(mission, updated_at="2026-09-03T00:00:00+00:00")

    assert repository.history("tenant-a", "NXS-SHARED")
    assert repository.history("tenant-b", "NXS-SHARED") == []
