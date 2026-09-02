from fastapi.testclient import TestClient

import main
from core.mission_repository import SQLiteMissionRepository
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def test_strict_auth_derives_tenant_and_role_from_server_config(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_API_KEYS", "approve-token=alice:tenant-secure:approver,view-token=bob:tenant-secure:viewer")
    original_repo = main.MISSION_REPOSITORY
    try:
        main.MISSION_REPOSITORY = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "secure.sqlite3"))
        no_key = client.get("/api/context")
        assert no_key.status_code == 401

        response = client.get("/api/context", headers={"X-API-Key": "view-token"})
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "tenant-secure"

        spoof = client.get(
            "/api/context",
            headers={"X-API-Key": "view-token", "X-Tenant-ID": "other-tenant"},
        )
        assert spoof.status_code == 403
    finally:
        main.MISSION_REPOSITORY = original_repo


def test_strict_auth_role_cannot_be_spoofed(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("NEXUS_API_KEYS", "view-token=bob:tenant-secure:viewer,approve-token=alice:tenant-secure:approver")
    original_repo = main.MISSION_REPOSITORY
    try:
        main.MISSION_REPOSITORY = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / "secure-role.sqlite3"))
        mission = client.post(
            "/api/missions",
            headers={"X-API-Key": "approve-token"},
            json={"goal": "Reduce operating cost by 10%"},
        )
        assert mission.status_code == 201
        mission_id = mission.json()["id"]

        spoofed = client.post(
            f"/api/missions/{mission_id}/approve",
            headers={"X-API-Key": "view-token", "X-Actor-Role": "approver"},
        )
        assert spoofed.status_code == 403

        approved = client.post(
            f"/api/missions/{mission_id}/approve",
            headers={"X-API-Key": "approve-token"},
        )
        assert approved.status_code == 200
    finally:
        main.MISSION_REPOSITORY = original_repo
