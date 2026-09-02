from fastapi.testclient import TestClient

import main
from core.mission_repository import SQLiteMissionRepository
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def test_mission_audit_records_authenticated_actor_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv(
        "NEXUS_API_KEYS",
        "operator-token=op-1:tenant-a:operator,approve-token=approver-1:tenant-a:approver",
    )
    original_repo = main.MISSION_REPOSITORY
    try:
        main.MISSION_REPOSITORY = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "audit.sqlite3"))

        created = client.post(
            "/api/missions",
            headers={"X-API-Key": "operator-token"},
            json={"goal": "Reduce operating cost by 10%"},
        )
        assert created.status_code == 201
        mission_id = created.json()["id"]

        created_auth = [event for event in created.json()["audit"] if event["stage"] == "auth"]
        assert created_auth[-1]["metadata"] == {
            "operation": "create_mission",
            "actor": {"subject": "op-1", "tenant_id": "tenant-a", "role": "operator"},
        }

        approved = client.post(
            f"/api/missions/{mission_id}/approve",
            headers={"X-API-Key": "approve-token"},
        )
        assert approved.status_code == 200

        persisted = client.get(
            f"/api/missions/{mission_id}",
            headers={"X-API-Key": "approve-token"},
        )
        assert persisted.status_code == 200
        auth_events = [event for event in persisted.json()["audit"] if event["stage"] == "auth"]
        assert auth_events[-1]["metadata"]["operation"] == "approve_mission"
        assert auth_events[-1]["metadata"]["actor"] == {
            "subject": "approver-1",
            "tenant_id": "tenant-a",
            "role": "approver",
        }
    finally:
        main.MISSION_REPOSITORY = original_repo
