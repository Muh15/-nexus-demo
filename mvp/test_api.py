from fastapi.testclient import TestClient

import main
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def test_api_mission_persists_across_cache_reset(tmp_path):
    original_store = main.MISSION_STORE
    original_cache = main.MISSIONS
    main.MISSION_STORE = SQLiteMissionStore(tmp_path / "api.sqlite3")
    main.MISSIONS = {}
    try:
        response = client.post(
            "/api/missions",
            json={
                "goal": "Reduce operating cost by 10% within 90 days",
                "constraints": ["Do not change quality"],
            },
        )
        assert response.status_code == 201
        mission = response.json()
        mission_id = mission["id"]
        assert mission["status"] == "awaiting_approval"
        assert mission["decision"]["evidence_count"] > 0

        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        executed = client.post(f"/api/missions/{mission_id}/execute")
        assert executed.status_code == 200
        executed_payload = executed.json()
        assert executed_payload["status"] == "executed"
        executed_at = executed_payload["action"]["executed_at"]
        execution_id = executed_payload["action"]["execution_id"]
        assert executed_payload["action"]["output"]["sent"] is False

        verified = client.post(f"/api/missions/{mission_id}/verify")
        assert verified.status_code == 200
        verified_payload = verified.json()
        assert verified_payload["status"] == "verified"
        assert verified_payload["verification"]["status"] == "verified"
        assert verified_payload["verification"]["execution_id"] == execution_id
        assert verified_payload["action"]["executed_at"] == executed_at

        main.MISSIONS = {}
        loaded = client.get(f"/api/missions/{mission_id}")
        assert loaded.status_code == 200
        payload = loaded.json()
        assert payload["id"] == mission_id
        assert payload["status"] == "verified"
        assert payload["verification"]["status"] == "verified"
        assert payload["action"]["execution_id"] == execution_id
    finally:
        main.MISSION_STORE = original_store
        main.MISSIONS = original_cache


def test_api_rejects_execute_before_approval(tmp_path):
    original_store = main.MISSION_STORE
    original_cache = main.MISSIONS
    main.MISSION_STORE = SQLiteMissionStore(tmp_path / "blocked.sqlite3")
    main.MISSIONS = {}
    try:
        response = client.post(
            "/api/missions",
            json={"goal": "Reduce operating cost by 10% within 90 days"},
        )
        mission_id = response.json()["id"]
        blocked = client.post(f"/api/missions/{mission_id}/execute")
        assert blocked.status_code == 409
    finally:
        main.MISSION_STORE = original_store
        main.MISSIONS = original_cache


def test_api_execution_is_idempotent(tmp_path):
    original_store = main.MISSION_STORE
    original_cache = main.MISSIONS
    main.MISSION_STORE = SQLiteMissionStore(tmp_path / "idempotent.sqlite3")
    main.MISSIONS = {}
    try:
        response = client.post(
            "/api/missions",
            json={"goal": "Reduce operating cost by 10% within 90 days"},
        )
        assert response.status_code == 201
        mission_id = response.json()["id"]
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200

        first = client.post(f"/api/missions/{mission_id}/execute")
        second = client.post(f"/api/missions/{mission_id}/execute")
        assert first.status_code == 200
        assert second.status_code == 200
        first_payload = first.json()
        second_payload = second.json()
        assert first_payload["action"]["execution_id"] == second_payload["action"]["execution_id"]
        assert first_payload["action"]["executed_at"] == second_payload["action"]["executed_at"]
    finally:
        main.MISSION_STORE = original_store
        main.MISSIONS = original_cache
