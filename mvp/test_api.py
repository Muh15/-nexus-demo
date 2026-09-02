from fastapi.testclient import TestClient

import main
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def _isolated_store(tmp_path, name):
    original_store = main.MISSION_STORE
    original_cache = main.MISSIONS
    main.MISSION_STORE = SQLiteMissionStore(tmp_path / name)
    main.MISSIONS = {}
    return original_store, original_cache


def _restore(original_store, original_cache):
    main.MISSION_STORE = original_store
    main.MISSIONS = original_cache


def _create_mission():
    response = client.post(
        "/api/missions",
        json={"goal": "Reduce operating cost by 10% within 90 days"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_api_mission_persists_across_cache_reset(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "api.sqlite3")
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
        _restore(original_store, original_cache)


def test_api_rejects_execute_before_approval(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "blocked.sqlite3")
    try:
        mission_id = _create_mission()
        blocked = client.post(f"/api/missions/{mission_id}/execute")
        assert blocked.status_code == 409
    finally:
        _restore(original_store, original_cache)


def test_api_execution_is_idempotent(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "idempotent.sqlite3")
    try:
        mission_id = _create_mission()
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
        _restore(original_store, original_cache)


def test_api_approval_and_verification_are_idempotent(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "idempotent_verify.sqlite3")
    try:
        mission_id = _create_mission()
        first_approval = client.post(f"/api/missions/{mission_id}/approve")
        second_approval = client.post(f"/api/missions/{mission_id}/approve")
        assert first_approval.status_code == 200
        assert second_approval.status_code == 200
        assert second_approval.json()["status"] == "approved"

        executed = client.post(f"/api/missions/{mission_id}/execute")
        assert executed.status_code == 200
        first_verify = client.post(f"/api/missions/{mission_id}/verify")
        second_verify = client.post(f"/api/missions/{mission_id}/verify")
        assert first_verify.status_code == 200
        assert second_verify.status_code == 200
        first_payload = first_verify.json()
        second_payload = second_verify.json()
        assert first_payload["verification"]["execution_id"] == second_payload["verification"]["execution_id"]
        assert first_payload["verification"]["verified_at"] == second_payload["verification"]["verified_at"]
    finally:
        _restore(original_store, original_cache)


def test_api_rejects_verify_before_execute(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "verify_blocked.sqlite3")
    try:
        mission_id = _create_mission()
        blocked = client.post(f"/api/missions/{mission_id}/verify")
        assert blocked.status_code == 409
    finally:
        _restore(original_store, original_cache)


def test_api_returns_404_for_unknown_mission(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "missing.sqlite3")
    try:
        assert client.get("/api/missions/NXS-DOES-NOT-EXIST").status_code == 404
        assert client.post("/api/missions/NXS-DOES-NOT-EXIST/approve").status_code == 404
    finally:
        _restore(original_store, original_cache)


def test_api_rejects_invalid_file_ingestion(tmp_path):
    original_store, original_cache = _isolated_store(tmp_path, "ingest.sqlite3")
    try:
        response = client.post(
            "/api/ingest/file",
            json={"filename": "broken.csv", "content": "this is not a valid table"},
        )
        assert response.status_code == 400
    finally:
        _restore(original_store, original_cache)
